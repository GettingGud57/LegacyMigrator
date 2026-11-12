"""
run_sql.py: run a .sql file that uses GO batch separators, the way sqlcmd does.

pyodbc can't run GO (it's a sqlcmd command, not T-SQL), so this splits the file
on lines that say only GO and runs each batch in order on one connection.
Uses the same .env settings as migrator/run_legacy.py.

Usage (from the repo root):
    python scripts/insurance/run_sql.py scripts/insurance/create_insurance.sql
    python scripts/insurance/run_sql.py legacy_jobs/insurance/MyProc.sql InsuranceDW

The optional second argument is the database to start in (default: master).
"""
import os
import re
import sys
from pathlib import Path

import pyodbc
from dotenv import load_dotenv


def batches(text):
    parts = re.split(r"^\s*GO\s*;?\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    return [p for p in parts if p.strip()]


def connect(database):
    load_dotenv()
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.environ['MSSQL_SERVER']};"
        f"DATABASE={database};"
        f"UID={os.environ['MSSQL_USER']};"
        f"PWD={{{os.environ['MSSQL_PASSWORD']}}};"
        "Encrypt=yes;TrustServerCertificate=yes",
        autocommit=True,  # CREATE DATABASE can't run inside a transaction
    )
    return conn.cursor()


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python scripts/insurance/run_sql.py path/to/script.sql [database]")
    path = Path(sys.argv[1])
    database = sys.argv[2] if len(sys.argv) == 3 else "master"
    parts = batches(path.read_text(encoding="utf-8-sig"))
    cur = connect(database)

    for i, batch in enumerate(parts, 1):
        first_line = next(line for line in batch.splitlines() if line.strip()).strip()
        print(f"[{i}/{len(parts)}] {first_line[:70]}")
        try:
            cur.execute(batch)
            # Walk every result set: errors in later statements only surface here
            while True:
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    for row in cur.fetchall():
                        print("   ", dict(zip(cols, row)))
                if not cur.nextset():
                    break
        except pyodbc.Error as e:
            sys.exit(f"\nBatch {i} failed:\n{e}")

    print(f"\nDone: {len(parts)} batches from {path}")


if __name__ == "__main__":
    main()
