"""
End-to-end tests for migrator/run_spark.py, run the way you run it by hand:
`python migrator/run_spark.py sale <job file>` in a folder that has snapshots/sale/before/.

Each test builds a tiny before/ snapshot (tests/snapshot_builder.py, through the real
run_legacy.snapshot()), runs run_spark.py in a temporary folder, and reads what it wrote.
Every run starts Spark, so each test takes 10-20 seconds.

The expected values in TestTheSaleTranslation were worked out by hand from
legacy_jobs/wwi/MigrateStagedSaleData.sql for this tiny input. They're a smoke test,
not a replacement for the real answer key from SQL Server.
"""
import datetime as dt
import textwrap
from decimal import Decimal as D
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import diff
from conftest import REPO, needs_spark, run_spark_cli
from snapshot_builder import sale_tables, write_snapshot

pytestmark = [pytest.mark.spark, needs_spark]

SALE_JOB = REPO / "jobs_pyspark" / "sale.py"
NOOP_JOB = REPO / "jobs_pyspark" / "noop.py"


def make_workdir(tmp_path, tables=None):
    write_snapshot(tmp_path / "snapshots/sale/before", tables or sale_tables())
    return tmp_path


def spark_rows(workdir, table):
    return pq.read_table(Path(workdir) / f"snapshots/sale/spark/{table}.parquet").to_pylist()


def explain(proc):
    """Last lines of run_spark's output, for assertion messages."""
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    return "\n".join(lines[-15:])


def write_job(tmp_path, name, code):
    path = tmp_path / name
    path.write_text(textwrap.dedent(code))
    return path


# ---------------------------------------------------------------- works today

def test_noop_round_trip_changes_nothing(tmp_path):
    """Reading before/ into Spark and writing it back must not change a single value."""
    work = make_workdir(tmp_path)
    proc = run_spark_cli(work, NOOP_JOB)
    assert proc.returncode == 0, explain(proc)
    for f in sorted((work / "snapshots/sale/before").glob("*.parquet")):
        before = diff.load(f)
        spark = diff.load(work / "snapshots/sale/spark" / f.name)
        assert diff.reconcile(before, spark)["status"] == "pass", f.stem


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    """One run of sale.py on the tiny snapshot, shared by the tests below."""
    work = make_workdir(tmp_path_factory.mktemp("sale"))
    proc = run_spark_cli(work, SALE_JOB)
    assert proc.returncode == 0, explain(proc)
    return work


class TestTheSaleTranslation:
    """jobs_pyspark/sale.py on the tiny snapshot, checked against hand-worked T-SQL results."""

    def test_staging_gets_dimension_keys(self, work):
        got = {(r["Sale Staging Key"], r["City Key"], r["Customer Key"], r["Bill To Customer Key"],
                r["Stock Item Key"], r["Salesperson Key"]) for r in spark_rows(work, "Integration.Sale_Staging")}
        assert got == {(1, 5, 7, 7, 8, 4), (2, 5, 7, 7, 9, 4)}

    def test_fact_sale_replaces_reloaded_invoice(self, work):
        rows = spark_rows(work, "Fact.Sale")
        assert sorted(r["Description"] for r in rows) == [
            "Chocolate frogs 250g", "Old line of invoice 99", "USB rocket launcher"]
        new = [r for r in rows if r["WWI Invoice ID"] == 100]
        assert {r["Lineage Key"] for r in new} == {2}
        assert {r["Stock Item Key"] for r in new} == {8, 9}

    def test_lineage_row_is_closed(self, work):
        rows = {r["Lineage Key"]: r for r in spark_rows(work, "Integration.Lineage")}
        assert rows[2]["Was Successful"] is True and rows[2]["Data Load Completed"] is not None
        assert rows[1]["Data Load Completed"] == dt.datetime(2016, 5, 6, 12, 5)

    def test_cutoff_moves_to_the_new_load(self, work):
        rows = {r["Table Name"]: r["Cutoff Time"] for r in spark_rows(work, "Integration.ETL Cutoff")}
        assert rows == {"Sale": dt.datetime(2016, 6, 6, 12, 31, 17),
                        "City": dt.datetime(2016, 5, 6, 12, 31, 17)}


# ---------------------------------------------------------------- bugs

@pytest.mark.bug
def test_finding4_failed_run_leaves_no_old_output(tmp_path):
    """
    Finding 4. If the job crashes, run_spark exits before it clears spark/, so the
    PREVIOUS run's output is still there. Running diff.py next compares that stale
    output and can print PASS for a translation that just crashed.
    """
    work = make_workdir(tmp_path)
    assert run_spark_cli(work, NOOP_JOB).returncode == 0  # a good run leaves spark/ behind
    broken = write_job(tmp_path, "broken.py", """
        def run(spark, tables):
            raise RuntimeError("the new translation crashes")
    """)
    proc = run_spark_cli(work, broken)
    assert proc.returncode != 0
    leftovers = sorted(p.name for p in (work / "snapshots/sale/spark").glob("*.parquet"))
    assert leftovers == [], f"old results still in spark/ after a failed run: {leftovers}"


@pytest.mark.bug
def test_finding6_job_cannot_copy_the_answer_key(tmp_path):
    """
    Finding 6. The generated job is ordinary Python run with full access to the repo.
    Nothing stops it from reading snapshots/<job>/after/ (the answer key) and returning it.
    This "translation" doesn't translate anything, and today it gets PASS.
    """
    tables = sale_tables()
    work = make_workdir(tmp_path, tables)
    tables["Fact.Sale"]["Quantity"] = [42, 42]  # an answer key no honest translation could guess
    write_snapshot(work / "snapshots/sale/after", tables)
    cheat = write_job(tmp_path, "cheat.py", """
        import glob, os

        def run(spark, tables):
            out = {}
            for path in glob.glob("snapshots/sale/after/*.parquet"):
                out[os.path.basename(path)[:-len(".parquet")]] = spark.read.parquet(path)
            return out
    """)
    proc = run_spark_cli(work, cheat)
    if proc.returncode != 0:
        return  # the harness stopped it: good
    verdict = diff.reconcile(diff.load(work / "snapshots/sale/after/Fact.Sale.parquet"),
                             diff.load(work / "snapshots/sale/spark/Fact.Sale.parquet"))["status"]
    assert verdict == "fail", "a job that copies after/ instead of translating got PASS"


@pytest.mark.bug
def test_finding9_result_does_not_depend_on_laptop_timezone(tmp_path):
    """
    Finding 9. sale.py collects Source System Cutoff Time into Python and puts it back with
    F.lit(). PySpark reads a plain Python datetime in the LAPTOP's timezone, so in Dublin
    in June the cutoff comes out an hour early. The same code passes on a UTC machine.
    """
    work = make_workdir(tmp_path)
    proc = run_spark_cli(work, SALE_JOB, extra_env={"TZ": "Europe/Dublin"})
    assert proc.returncode == 0, explain(proc)
    rows = {r["Table Name"]: r["Cutoff Time"] for r in spark_rows(work, "Integration.ETL Cutoff")}
    assert rows["Sale"] == dt.datetime(2016, 6, 6, 12, 31, 17)


@pytest.mark.bug
class TestFinding8_GuessedTypesBreakTheTranslation:
    """
    Finding 8, end to end. Because run_legacy guesses column types from the values,
    sale.py's cast to Fact.Sale's types uses a decimal precision that only fits the
    numbers that happen to be in the table. Data that's perfectly fine for SQL Server
    then crashes Spark. These should pass once run_legacy writes the declared SQL types.
    """

    def test_new_largest_price(self, tmp_path):
        tables = sale_tables()
        tables["Integration.Sale_Staging"]["Unit Price"] = [D("4.10"), D("12500.00")]  # fits decimal(18,2)
        work = make_workdir(tmp_path, tables)
        proc = run_spark_cli(work, SALE_JOB)
        assert proc.returncode == 0, explain(proc)
        prices = {r["Unit Price"] for r in spark_rows(work, "Fact.Sale")}
        assert D("12500.00") in prices

    def test_day_with_no_sales(self, tmp_path):
        tables = sale_tables()
        tables["Integration.Sale_Staging"] = {c: [] for c in tables["Integration.Sale_Staging"]}
        work = make_workdir(tmp_path, tables)
        proc = run_spark_cli(work, SALE_JOB)
        assert proc.returncode == 0, explain(proc)
        assert len(spark_rows(work, "Fact.Sale")) == 2  # nothing deleted, nothing inserted
