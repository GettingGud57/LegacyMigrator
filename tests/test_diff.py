"""
Tests for migrator/diff.py, the PASS/FAIL checker.

Two kinds of test live here:
  - "works" tests lock in behaviour that is already right. They pass today.
  - "bug" tests (marked @pytest.mark.bug) describe a finding from the review.
    They FAIL today and should pass once the bug is fixed.
    The finding number matches docs/reports/review.html and tests/README.md.

None of these need Spark. They run in about a second.
"""
import datetime as dt
import subprocess
import sys
from decimal import Decimal as D

import pyarrow as pa
import pytest

import diff
from conftest import REPO, verdict_for_files, write_parquet


def status(rows_a, rows_b, **kwargs):
    return diff.reconcile(rows_a, rows_b, **kwargs)["status"]


ROWS = [
    {"id": 1, "name": "Anna", "price": D("4.10"), "day": dt.date(2016, 6, 1)},
    {"id": 2, "name": "Ben", "price": D("25.00"), "day": dt.date(2016, 6, 2)},
    {"id": 3, "name": None, "price": None, "day": None},
]


def copy_rows(rows):
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- works today

class TestWhatAlreadyWorks:
    def test_identical_tables_pass(self):
        assert status(ROWS, copy_rows(ROWS)) == "pass"

    def test_row_order_does_not_matter(self):
        assert status(ROWS, list(reversed(copy_rows(ROWS)))) == "pass"

    def test_one_changed_cell_fails(self):
        b = copy_rows(ROWS)
        b[1]["price"] = D("25.01")
        assert status(ROWS, b) == "fail"

    def test_missing_row_fails(self):
        assert status(ROWS, copy_rows(ROWS)[:2]) == "fail"

    def test_extra_row_fails(self):
        b = copy_rows(ROWS) + [{"id": 4, "name": "Cara", "price": D("1.00"), "day": None}]
        assert status(ROWS, b) == "fail"

    def test_duplicated_row_fails(self):
        # Same set of distinct rows, but one appears twice. A set compare would miss this.
        b = copy_rows(ROWS) + [dict(ROWS[0])]
        assert status(ROWS, b) == "fail"

    def test_swapped_values_between_rows_fail(self):
        # Every column still holds the same values, just on the wrong rows.
        b = copy_rows(ROWS)
        b[0]["name"], b[1]["name"] = b[1]["name"], b[0]["name"]
        assert status(ROWS, b) == "fail"

    def test_extra_column_fails(self):
        b = [dict(r, extra=1) for r in ROWS]
        assert status(ROWS, b) == "fail"

    def test_missing_column_fails(self):
        b = [{k: v for k, v in r.items() if k != "name"} for r in ROWS]
        assert status(ROWS, b) == "fail"

    def test_empty_vs_non_empty_fails(self):
        assert status(ROWS, []) == "fail"
        assert status([], ROWS) == "fail"

    @pytest.mark.parametrize("legacy, spark", [
        (None, 0),                         # NULL is not zero
        (None, ""),                        # NULL is not an empty string
        (None, float("nan")),              # SQL Server has no NaN; Spark can make one
        ("Cork", "Cork "),                 # trailing space
        ("Cork", "cork"),                  # case
        (D("0.10"), 0.1),                  # decimal vs a float that isn't exactly 0.1
        (dt.date(2016, 1, 1), dt.datetime(2016, 1, 1)),  # date vs midnight timestamp
    ])
    def test_values_that_look_alike_but_differ_fail(self, legacy, spark):
        assert status([{"id": 1, "v": legacy}], [{"id": 1, "v": spark}]) == "fail"

    def test_explanation_names_the_changed_cell(self):
        b = copy_rows(ROWS)
        b[1]["price"] = D("25.01")
        result = diff.reconcile(ROWS, b, key_cols=["id"])
        changed = result["explanation"]["changed"]
        assert changed == [{"key": (2,), "col": "price", "a": D("25.00"), "b": D("25.01")}]

    def test_ignored_column_is_not_compared(self):
        b = copy_rows(ROWS)
        b[0]["name"] = "Someone else"
        assert status(ROWS, b, ignore_cols=["name"]) == "pass"


# ---------------------------------------------------------------- bugs

@pytest.mark.bug
class TestFinding1_EveryTableIsCompared:
    """
    Finding 1. `python migrator/diff.py` only compares Integration.Sale_Staging.
    The Sale job also changes Fact.Sale, Integration.Lineage and Integration.ETL Cutoff.
    A translation that gets Fact.Sale completely wrong still prints PASS.
    """

    def _make_snapshots(self, root, fact_spark_rows):
        staging = pa.table({"Sale Staging Key": [1, 2], "City Key": [5, 5]})
        fact_after = pa.table({"Sale Key": [1, 2], "Quantity": [3, 1]})
        for stage in ("before", "after", "spark"):
            write_parquet(root / f"snapshots/sale/{stage}/Integration.Sale_Staging.parquet", staging)
        write_parquet(root / "snapshots/sale/before/Fact.Sale.parquet", fact_after)
        write_parquet(root / "snapshots/sale/after/Fact.Sale.parquet", fact_after)
        if fact_spark_rows is not None:
            write_parquet(root / "snapshots/sale/spark/Fact.Sale.parquet", pa.table(fact_spark_rows))

    def _run_diff(self, root):
        return subprocess.run([sys.executable, str(REPO / "migrator" / "diff.py"), "sale"],
                              cwd=root, capture_output=True, text=True)

    def test_wrong_fact_sale_is_reported(self, tmp_path):
        self._make_snapshots(tmp_path, {"Sale Key": [1, 2], "Quantity": [999, 999]})
        out = self._run_diff(tmp_path)
        said_fail = out.returncode != 0 or "FAIL" in out.stdout
        assert said_fail and "Fact.Sale" in out.stdout + out.stderr, (
            "Fact.Sale differs between after/ and spark/, but diff.py didn't report it:\n" + out.stdout)

    def test_missing_spark_output_is_reported(self, tmp_path):
        # spark/ has no Fact.Sale at all, e.g. run_spark crashed half way through
        self._make_snapshots(tmp_path, None)
        out = self._run_diff(tmp_path)
        said_fail = out.returncode != 0 or "FAIL" in out.stdout
        assert said_fail and "Fact.Sale" in out.stdout + out.stderr, (
            "spark/Fact.Sale.parquet is missing, but diff.py didn't notice:\n" + out.stdout)


@pytest.mark.bug
class TestFinding2_TypesAreCompared:
    """
    Finding 2. diff.load() turns every cell into a plain Python value, and Python says
    Decimal('1.10') == Decimal('1.100000'), 1 == 1.0 and True == 1. So a translation
    that changes a column's type still gets PASS, as long as the values look equal.
    """

    @pytest.mark.parametrize("legacy_type, spark_type, values", [
        (pa.decimal128(18, 2), pa.decimal128(38, 6), [D("1.10"), D("25.00")]),  # Spark decimal widening
        (pa.decimal128(18, 2), pa.float64(), [2.5, 25.0]),                      # decimal became double
        (pa.int32(), pa.float64(), [3.0, 1.0]),                                 # int became double
        (pa.int32(), pa.int64(), [3, 1]),                                       # int became bigint
        (pa.bool_(), pa.int64(), [True, False]),                                # bit became int
    ], ids=["decimal-widened", "decimal-to-double", "int-to-double", "int-to-bigint", "bit-to-int"])
    def test_type_drift_is_caught(self, tmp_path, legacy_type, spark_type, values):
        legacy_values = [D(str(v)) if pa.types.is_decimal(legacy_type) else v for v in values]
        if pa.types.is_integer(legacy_type):
            legacy_values = [int(v) for v in values]
        legacy = pa.table({"v": pa.array(legacy_values, legacy_type)})
        spark = pa.table({"v": pa.array(values, spark_type)})
        a = write_parquet(tmp_path / "after.parquet", legacy)
        b = write_parquet(tmp_path / "spark.parquet", spark)
        assert verdict_for_files(a, b) == "fail", f"{legacy_type} vs {spark_type} passed"


@pytest.mark.bug
class TestFinding3_IgnoredColumnsStillGetChecked:
    """
    Finding 3. Some columns can never match exactly (SYSDATETIME() timestamps, identity keys),
    so they'll have to go on the ignore list. But ignoring a column today means not looking
    at it at all: a translation that never fills it in also passes.
    """

    def test_never_filled_in_is_caught(self):
        legacy = [{"Lineage Key": 2, "Data Load Completed": dt.datetime(2026, 11, 4, 21, 0, 1)}]
        spark = [{"Lineage Key": 2, "Data Load Completed": None}]  # translation forgot the UPDATE
        assert status(legacy, spark, ignore_cols=["Data Load Completed"]) == "fail"

    def test_filled_in_with_a_different_time_still_passes(self):
        # This must keep passing after the fix: the time itself can't match between runs.
        legacy = [{"Lineage Key": 2, "Data Load Completed": dt.datetime(2026, 11, 4, 21, 0, 1)}]
        spark = [{"Lineage Key": 2, "Data Load Completed": dt.datetime(2026, 11, 4, 22, 13, 7)}]
        assert status(legacy, spark, ignore_cols=["Data Load Completed"]) == "pass"


@pytest.mark.bug
class TestFinding5_EmptyTables:
    """
    Finding 5. reconcile() learns the column names from the first row. An empty table
    has no first row, so two empty tables always pass, whatever their columns.
    """

    def test_empty_tables_with_different_columns_fail(self, tmp_path):
        a = write_parquet(tmp_path / "after.parquet",
                          pa.table({"City Key": pa.array([], pa.int32())}))
        b = write_parquet(tmp_path / "spark.parquet",
                          pa.table({"Wrong Column": pa.array([], pa.string())}))
        assert verdict_for_files(a, b) == "fail"


@pytest.mark.bug
class TestFinding12_ExplanationDoesNotCrash:
    """
    Finding 12. If the Spark output lost the key column, reconcile() correctly decides FAIL,
    then crashes with KeyError while building the explanation. The verdict never prints.
    """

    def test_missing_key_column_is_a_fail_not_a_crash(self):
        legacy = [{"Sale Staging Key": 1, "City Key": 5}]
        spark = [{"City Key": 5}]  # key column dropped
        result = diff.reconcile(legacy, spark, key_cols=["Sale Staging Key"])
        assert result["status"] == "fail"
