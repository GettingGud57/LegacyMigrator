"""
Tests for migrator/run_legacy.py's snapshot code, using a fake database cursor
(tests/snapshot_builder.py), so no SQL Server is needed.

Finding 8: run_legacy builds each Parquet column with pa.array(values), which makes
pyarrow GUESS the type from the values. The column's real SQL type is never used.
"""
import datetime as dt
from decimal import Decimal as D

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import run_legacy
from snapshot_builder import FakeCursor, sale_tables, write_snapshot


def schema_of(tmp_path, table_name, tables):
    write_snapshot(tmp_path, {table_name: tables[table_name]})
    return pq.read_schema(tmp_path / f"{table_name}.parquet")


# ---------------------------------------------------------------- works today

def test_year_9999_dates_survive(tmp_path):
    tables = sale_tables()
    write_snapshot(tmp_path, {"Dimension.City": tables["Dimension.City"]})
    rows = pq.read_table(tmp_path / "Dimension.City.parquet").to_pylist()
    assert rows[1]["Valid To"] == dt.datetime(9999, 12, 31, 23, 59, 59, 999999)


def test_decimals_stay_exact(tmp_path):
    tables = sale_tables()
    write_snapshot(tmp_path, {"Fact.Sale": tables["Fact.Sale"]})
    rows = pq.read_table(tmp_path / "Fact.Sale.parquet").to_pylist()
    assert rows[0]["Total Including Tax"] == D("21838.50")


def test_select_list_reads_spatial_columns_as_text():
    class Cur(FakeCursor):
        def fetchall(self):
            return [("City Key", "int"), ("Location", "geography")]

    cur = Cur({})
    cur.execute("SELECT c.name, t.name FROM sys.columns AS c WHERE x = ?", "Dimension.City")
    assert run_legacy.select_list(cur, "Dimension.City") == "[City Key], [Location].STAsText() AS [Location]"


# ---------------------------------------------------------------- bugs

@pytest.mark.bug
class TestFinding8_DeclaredTypesAreKept:
    """The Parquet type should come from the column's SQL type, not from whatever values it holds."""

    @pytest.mark.parametrize("column, expected", [
        ("Unit Price", pa.decimal128(18, 2)),   # guessed as decimal(6,2) from the values today
        ("Tax Rate", pa.decimal128(18, 3)),     # guessed as decimal(5,3)
        ("Quantity", pa.int32()),               # SQL int is 32-bit; guessed as int64
    ])
    def test_fact_sale_column_types(self, tmp_path, column, expected):
        schema = schema_of(tmp_path, "Fact.Sale", sale_tables())
        assert schema.field(column).type == expected

    def test_all_null_column_keeps_its_type(self, tmp_path):
        # Before the job runs, every staging City Key is NULL. Today the column's type becomes `null`,
        # which is why translate.py's prompt has to explain "type null" to the AI.
        schema = schema_of(tmp_path, "Integration.Sale_Staging", sale_tables())
        assert schema.field("City Key").type == pa.int32()

    def test_empty_table_keeps_its_types(self, tmp_path):
        # A day with no sales: staging is empty. Today every column becomes type `null`.
        tables = sale_tables()
        tables["Integration.Sale_Staging"] = {c: [] for c in tables["Integration.Sale_Staging"]}
        schema = schema_of(tmp_path, "Integration.Sale_Staging", tables)
        assert schema.field("Last Modified When").type == pa.timestamp("us")
        assert schema.field("Unit Price").type == pa.decimal128(18, 2)
