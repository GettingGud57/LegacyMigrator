"""
Build tiny snapshot folders shaped like the real WideWorldImporters ones,
without SQL Server.

How it works: FakeCursor pretends to be a pyodbc cursor. It knows each
table's declared SQL types (copied from the WWI warehouse) and its rows.
write_snapshot() hands it to the REAL migrator/run_legacy.snapshot(), so the
Parquet files come out exactly the way run_legacy would write them, quirks
included. When run_legacy.py gets fixed, these files change with it.

sale_tables() returns a small, hand-made copy of the 8 tables
Integration.MigrateStagedSaleData touches. Each test takes a fresh copy and
changes the one thing it is about.
"""
import datetime as dt
import re
from decimal import Decimal as D

import run_legacy  # the real one, from migrator/ (conftest.py puts it on the path)

END_OF_TIME = dt.datetime(9999, 12, 31, 23, 59, 59, 999999)

# Declared column types, in column order. Copied from the WWI warehouse DDL
# for the columns the Sale job uses (dimension tables are trimmed).
SQL_TYPES = {
    "Integration.Sale_Staging": [
        ("Sale Staging Key", "bigint"), ("City Key", "int"), ("Customer Key", "int"),
        ("Bill To Customer Key", "int"), ("Stock Item Key", "int"), ("Invoice Date Key", "date"),
        ("Delivery Date Key", "date"), ("Salesperson Key", "int"), ("WWI Invoice ID", "int"),
        ("Description", "nvarchar(100)"), ("Package", "nvarchar(50)"), ("Quantity", "int"),
        ("Unit Price", "decimal(18,2)"), ("Tax Rate", "decimal(18,3)"),
        ("Total Excluding Tax", "decimal(18,2)"), ("Tax Amount", "decimal(18,2)"),
        ("Profit", "decimal(18,2)"), ("Total Including Tax", "decimal(18,2)"),
        ("Total Dry Items", "int"), ("Total Chiller Items", "int"), ("WWI City ID", "int"),
        ("WWI Customer ID", "int"), ("WWI Bill To Customer ID", "int"),
        ("WWI Stock Item ID", "int"), ("WWI Salesperson ID", "int"),
        ("Last Modified When", "datetime2"),
    ],
    "Fact.Sale": [
        ("Sale Key", "bigint"), ("City Key", "int"), ("Customer Key", "int"),
        ("Bill To Customer Key", "int"), ("Stock Item Key", "int"), ("Invoice Date Key", "date"),
        ("Delivery Date Key", "date"), ("Salesperson Key", "int"), ("WWI Invoice ID", "int"),
        ("Description", "nvarchar(100)"), ("Package", "nvarchar(50)"), ("Quantity", "int"),
        ("Unit Price", "decimal(18,2)"), ("Tax Rate", "decimal(18,3)"),
        ("Total Excluding Tax", "decimal(18,2)"), ("Tax Amount", "decimal(18,2)"),
        ("Profit", "decimal(18,2)"), ("Total Including Tax", "decimal(18,2)"),
        ("Total Dry Items", "int"), ("Total Chiller Items", "int"), ("Lineage Key", "int"),
    ],
    "Integration.Lineage": [
        ("Lineage Key", "int"), ("Data Load Started", "datetime2"), ("Table Name", "sysname"),
        ("Data Load Completed", "datetime2"), ("Was Successful", "bit"),
        ("Source System Cutoff Time", "datetime2"),
    ],
    "Integration.ETL Cutoff": [("Table Name", "sysname"), ("Cutoff Time", "datetime2")],
    "Dimension.City": [
        ("City Key", "int"), ("WWI City ID", "int"), ("City", "nvarchar(50)"),
        ("Valid From", "datetime2"), ("Valid To", "datetime2"), ("Lineage Key", "int"),
    ],
    "Dimension.Customer": [
        ("Customer Key", "int"), ("WWI Customer ID", "int"), ("Customer", "nvarchar(100)"),
        ("Valid From", "datetime2"), ("Valid To", "datetime2"), ("Lineage Key", "int"),
    ],
    "Dimension.Stock Item": [
        ("Stock Item Key", "int"), ("WWI Stock Item ID", "int"), ("Stock Item", "nvarchar(100)"),
        ("Valid From", "datetime2"), ("Valid To", "datetime2"), ("Lineage Key", "int"),
    ],
    "Dimension.Employee": [
        ("Employee Key", "int"), ("WWI Employee ID", "int"), ("Employee", "nvarchar(50)"),
        ("Is SalesPerson", "bit"), ("Valid From", "datetime2"), ("Valid To", "datetime2"),
        ("Lineage Key", "int"),
    ],
}

# What pyodbc reports for each SQL type: (Python type, internal size)
_PYODBC = {
    "int": (int, 10), "bigint": (int, 19), "bit": (bool, 1), "date": (dt.date, 10),
    "datetime2": (dt.datetime, 27), "decimal": (D, None), "nvarchar": (str, None),
    "sysname": (str, 128),
}


def _parse(sql_type):
    """'decimal(18,2)' -> ('decimal', 18, 2); 'nvarchar(50)' -> ('nvarchar', 50, 0); 'int' -> ('int', 10, 0)"""
    m = re.fullmatch(r"(\w+)(?:\((\d+)(?:,(\d+))?\))?", sql_type)
    base, a, b = m.group(1), m.group(2), m.group(3)
    if base == "decimal":
        return base, int(a), int(b)
    if base == "nvarchar":
        return base, int(a), 0
    precision = {"int": 10, "bigint": 19, "bit": 1, "date": 10, "datetime2": 27, "sysname": 128}[base]
    scale = 7 if base == "datetime2" else 0
    return base, precision, scale


class FakeCursor:
    """
    Just enough of a pyodbc cursor for run_legacy.snapshot().

    Understands two kinds of query:
      - the sys.columns lookup in run_legacy.select_list(). It reads the SELECT list,
        so adding c.precision, c.scale, c.max_length or c.is_nullable to that query works.
      - SELECT <columns> FROM <table>
    If you change run_legacy to ask for something else, teach it here.
    """

    def __init__(self, tables):
        # tables: {"Fact.Sale": {column: [values]}}. Types come from SQL_TYPES.
        self.tables = tables
        self.description = None
        self._rows = []

    @staticmethod
    def _table_key(name):
        return name.replace("[", "").replace("]", "")

    def execute(self, query, *params):
        if "sys.columns" in query:
            self._sys_columns(query, self._table_key(params[0]))
        else:
            m = re.search(r"\bFROM\s+(.+?)\s*$", query, re.S)
            self._select(self._table_key(m.group(1).strip()))
        return self

    def _sys_columns(self, query, table):
        select_list = re.search(r"SELECT\s+(.*?)\s+FROM\s+sys\.columns", query, re.S | re.I).group(1)
        fields = [re.split(r"\s+AS\s+", f.strip(), flags=re.I)[0].strip() for f in select_list.split(",")]
        rows = []
        for i, (name, sql_type) in enumerate(SQL_TYPES.get(table, []), start=1):
            base, precision, scale = _parse(sql_type)
            values = {
                "c.name": name, "t.name": base, "type_name(c.user_type_id)": base,
                "c.precision": precision if base in ("decimal", "int", "bigint", "bit", "datetime2") else 0,
                "c.scale": scale, "c.max_length": precision * 2 if base in ("nvarchar", "sysname") else 8,
                "c.is_nullable": True, "c.column_id": i,
            }
            row = []
            for f in fields:
                if f.lower() not in values:
                    raise NotImplementedError(f"FakeCursor doesn't know sys.columns field {f!r}")
                row.append(values[f.lower()])
            rows.append(tuple(row))
        self.description = [(f, str, None, None, None, None, True) for f in fields]
        self._rows = rows

    def _select(self, table):
        types = SQL_TYPES[table]
        data = self.tables[table]
        self.description = []
        for name, sql_type in types:
            base, precision, scale = _parse(sql_type)
            py_type, size = _PYODBC[base]
            self.description.append((name, py_type, None, size or precision, precision, scale, True))
        n = len(next(iter(data.values()))) if data else 0
        self._rows = [tuple(data[name][i] for name, _ in types) for i in range(n)]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def nextset(self):
        return False


def write_snapshot(folder, tables):
    """Write tables through the real run_legacy.snapshot(). Returns its {table: row count}."""
    return run_legacy.snapshot(FakeCursor(tables), list(tables), folder)


def sale_tables():
    """A tiny Sale job input: 2 staged lines for invoice 100, plus one untouched invoice (99)."""
    lmw = dt.datetime(2016, 6, 1, 10, 0, 0)  # Last Modified When of the staged lines
    v1 = dt.datetime(2013, 1, 1)
    return {
        "Integration.Sale_Staging": {
            "Sale Staging Key": [1, 2],
            "City Key": [None, None],
            "Customer Key": [None, None],
            "Bill To Customer Key": [None, None],
            "Stock Item Key": [None, None],
            "Invoice Date Key": [dt.date(2016, 6, 1)] * 2,
            "Delivery Date Key": [dt.date(2016, 6, 2), None],
            "Salesperson Key": [None, None],
            "WWI Invoice ID": [100, 100],
            "Description": ["Chocolate frogs 250g", "USB rocket launcher"],
            "Package": ["Each", "Each"],
            "Quantity": [3, 1],
            "Unit Price": [D("4.10"), D("25.00")],
            "Tax Rate": [D("15.000"), D("15.000")],
            "Total Excluding Tax": [D("12.30"), D("25.00")],
            "Tax Amount": [D("1.85"), D("3.75")],
            "Profit": [D("6.30"), D("12.50")],
            "Total Including Tax": [D("14.15"), D("28.75")],
            "Total Dry Items": [0, 1],
            "Total Chiller Items": [3, 0],
            "WWI City ID": [10, 10],
            "WWI Customer ID": [20, 20],
            "WWI Bill To Customer ID": [20, 20],
            "WWI Stock Item ID": [30, 31],
            "WWI Salesperson ID": [40, 40],
            "Last Modified When": [lmw, lmw],
        },
        "Fact.Sale": {
            "Sale Key": [1, 2],
            "City Key": [5, 5],
            "Customer Key": [7, 7],
            "Bill To Customer Key": [7, 7],
            "Stock Item Key": [8, 8],
            "Invoice Date Key": [dt.date(2016, 5, 1)] * 2,
            "Delivery Date Key": [dt.date(2016, 5, 2)] * 2,
            "Salesperson Key": [4, 4],
            "WWI Invoice ID": [99, 100],  # invoice 100 is being reloaded, so this old line goes
            "Description": ["Old line of invoice 99", "Old line of invoice 100"],
            "Package": ["Each", "Each"],
            "Quantity": [1, 1],
            # The real Fact.Sale has 228k rows, so its largest values are large. Keep one
            # big row here, or run_legacy's guessed decimal types come out unrealistically narrow.
            "Unit Price": [D("1899.00"), D("9.99")],
            "Tax Rate": [D("15.000"), D("15.000")],
            "Total Excluding Tax": [D("18990.00"), D("9.99")],
            "Tax Amount": [D("2848.50"), D("1.50")],
            "Profit": [D("8500.00"), D("5.00")],
            "Total Including Tax": [D("21838.50"), D("11.49")],
            "Total Dry Items": [1, 1],
            "Total Chiller Items": [0, 0],
            "Lineage Key": [1, 1],
        },
        "Integration.Lineage": {
            "Lineage Key": [1, 2],
            "Data Load Started": [dt.datetime(2016, 5, 6, 12, 0), dt.datetime(2016, 6, 6, 12, 0)],
            "Table Name": ["Sale", "Sale"],
            "Data Load Completed": [dt.datetime(2016, 5, 6, 12, 5), None],  # load 2 is the open one
            "Was Successful": [True, False],
            "Source System Cutoff Time": [dt.datetime(2016, 5, 6, 12, 31, 17), dt.datetime(2016, 6, 6, 12, 31, 17)],
        },
        "Integration.ETL Cutoff": {
            "Table Name": ["Sale", "City"],
            "Cutoff Time": [dt.datetime(2016, 5, 6, 12, 31, 17)] * 2,
        },
        "Dimension.City": {
            "City Key": [0, 5], "WWI City ID": [0, 10], "City": ["Unknown", "Cork"],
            "Valid From": [v1, v1], "Valid To": [END_OF_TIME] * 2, "Lineage Key": [0, 1],
        },
        "Dimension.Customer": {
            "Customer Key": [0, 7], "WWI Customer ID": [0, 20], "Customer": ["Unknown", "Anna"],
            "Valid From": [v1, v1], "Valid To": [END_OF_TIME] * 2, "Lineage Key": [0, 1],
        },
        "Dimension.Stock Item": {
            "Stock Item Key": [0, 8, 9], "WWI Stock Item ID": [0, 30, 31],
            "Stock Item": ["Unknown", "Chocolate frogs 250g", "USB rocket launcher"],
            "Valid From": [v1] * 3, "Valid To": [END_OF_TIME] * 3, "Lineage Key": [0, 1, 1],
        },
        "Dimension.Employee": {
            "Employee Key": [0, 4], "WWI Employee ID": [0, 40], "Employee": ["Unknown", "Kayla"],
            "Is SalesPerson": [False, True], "Valid From": [v1, v1],
            "Valid To": [END_OF_TIME] * 2, "Lineage Key": [0, 1],
        },
    }
