"""
run_legacy.py: run one legacy job on SQL Server and save the tables it touches.

    snapshots/<job>/before/   the job's input
    snapshots/<job>/after/    the answer key (what the legacy job produced)
    snapshots/<job>/meta.json return code and row counts

The job runs inside a transaction that gets rolled back at the end,
so the database is left exactly as it was and this can be rerun any time.

Usage (from the repo root):
    python migrator/run_legacy.py sale
"""
import json
import os
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pyodbc
from dotenv import load_dotenv

# One entry per legacy job. "tables" = everything the job reads or writes.
JOBS = {
    "sale": {
        "database": "WideWorldImportersDW",
        "staging_script": "scripts/load_sale_staging.sql",
        "proc": "Integration.MigrateStagedSaleData",
        "tables": [
            "Integration.Sale_Staging",
            "Integration.Lineage",
            "Integration.[ETL Cutoff]",
            "Dimension.City",
            "Dimension.Customer",
            "Dimension.[Stock Item]",
            "Dimension.Employee",
            "Fact.Sale",
        ],
    },
}

# pyodbc can't read map columns (geography/geometry), so read them as text instead
SPATIAL_TYPES = {"geography", "geometry"}


def connect(database):
    load_dotenv()
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.environ['MSSQL_SERVER']};"
        f"DATABASE={database};"
        f"UID={os.environ['MSSQL_USER']};"
        f"PWD={{{os.environ['MSSQL_PASSWORD']}}};"
        "Encrypt=yes;TrustServerCertificate=yes",
        autocommit=True,
    )
    return conn.cursor()


def run_script(cur, path):
    """Run a .sql file and print its last result set."""
    cur.execute(Path(path).read_text(encoding="utf-8-sig"))
    last = None
    while True:
        if cur.description:
            last = ([d[0] for d in cur.description], cur.fetchall())
        if not cur.nextset():
            break
    if last:
        cols, rows = last
        for row in rows:
            print("   ", dict(zip(cols, row)))


def select_list(cur, table):
    """Column list for SELECT, converting map columns to text."""
    cur.execute(
        "SELECT c.name, t.name FROM sys.columns AS c "
        "JOIN sys.types AS t ON c.user_type_id = t.user_type_id "
        "WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
        table,
    )
    parts = []
    for name, type_name in cur.fetchall():
        col = f"[{name}]"
        parts.append(f"{col}.STAsText() AS {col}" if type_name in SPATIAL_TYPES else col)
    if not parts:
        raise SystemExit(f"Table not found: {table}")
    return ", ".join(parts)


def read_table(cur, table):
    """Whole table as an Arrow table. Arrow keeps decimals exact and handles year-9999 dates."""
    cur.execute(f"SELECT {select_list(cur, table)} FROM {table}")
    names = [d[0] for d in cur.description]
    rows = cur.fetchall()
    columns = list(zip(*rows)) if rows else [[] for _ in names]
    return pa.table({name: pa.array(list(values)) for name, values in zip(names, columns)})


def snapshot(cur, tables, folder):
    """Save each table as Parquet. Returns {table: row count}."""
    folder.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table in tables:
        name = table.replace("[", "").replace("]", "")
        data = read_table(cur, table)
        pq.write_table(data, folder / f"{name}.parquet")
        counts[name] = data.num_rows
    return counts


def main():
    job_name = sys.argv[1] if len(sys.argv) > 1 else "sale"
    job = JOBS[job_name]
    out = Path("snapshots") / job_name
    cur = connect(job["database"])

    # Outside the transaction: SQL Server won't let one transaction touch an
    # in-memory table and a second database, and this script reads the shop database.
    print("1. Loading staging")
    run_script(cur, job["staging_script"])

    print("2. Running the legacy job inside a transaction")
    cur.execute("BEGIN TRAN")
    try:
        before = snapshot(cur, job["tables"], out / "before")
        cur.execute(f"SET NOCOUNT ON; DECLARE @r int; EXEC @r = {job['proc']}; SELECT @r")
        return_code = cur.fetchone()[0]
        after = snapshot(cur, job["tables"], out / "after")
    finally:
        cur.execute("IF @@TRANCOUNT > 0 ROLLBACK")
    print("3. Rolled back, database unchanged")

    meta = {
        "job": job_name,
        "proc": job["proc"],
        "return_code": return_code,
        "rows_before": before,
        "rows_after": after,
        "taken_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"\n   return code: {return_code}\n")
    print(f"   {'table':28} {'before':>8} {'after':>8}")
    for table in before:
        print(f"   {table:28} {before[table]:>8} {after[table]:>8}")
    print(f"\n   saved to {out}/")


if __name__ == "__main__":
    main()
