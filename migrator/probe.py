"""
probe.py: find the columns that can never match, from evidence instead of guesswork.

Stage the input once, then run the legacy job twice on it, each run in its own transaction
that gets rolled back. Both runs start from exactly the same tables, so any column that
comes out different between them is not decided by the input. Typical causes:

  - an identity column: SQL Server hands out the next number, and a rollback does NOT
    give numbers back, so the second run gets new ones
  - SYSDATETIME() / GETDATE(): the clock moved between the runs

No translation can reproduce those values, so check.py stops comparing them, and records why.
Everything else must match exactly. A column is only ignored if this probe saw it change.

    jobs/evidence/<job>.json   what was found, with example values from both runs (commit this)
    snapshots/<job>/probe/     the two runs' output tables

Usage (from the repo root):
    python migrator/probe.py sale
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import diff  # noqa: E402
import discover  # noqa: E402
import jobspec  # noqa: E402
import run_legacy  # noqa: E402


def column_values(rows, col):
    return Counter(row[col] for row in rows)


def unstable_columns(rows_1, rows_2):
    """Columns whose values (as a multiset, ignoring row order) differ between the two runs."""
    cols = sorted(rows_1[0]) if rows_1 else []
    return [c for c in cols if column_values(rows_1, c) != column_values(rows_2, c)]


def reason(col, identity_cols, rows_1, rows_2):
    if col in identity_cols:
        return ("identity column: SQL Server gives new rows the next number, and a rollback "
                "doesn't hand numbers back, so two runs on the same input get different values")
    only_1 = column_values(rows_1, col) - column_values(rows_2, col)
    sample = next(iter(only_1), None)
    if hasattr(sample, "year"):
        return ("date-time that differs between two runs on the same input: "
                "a clock value such as SYSDATETIME(), set when the job runs")
    return "differs between two runs of the legacy job on the same input"


def main():
    job_name = sys.argv[1] if len(sys.argv) > 1 else "sale"
    spec = jobspec.load(job_name)
    cur = run_legacy.connect(spec["database"])
    tables, keys, found = run_legacy.job_tables(cur, spec)
    out = Path("snapshots") / job_name / "probe"

    print("1. Loading staging once")
    run_legacy.stage(cur, spec)

    print("2. Running the legacy job twice on the same input, rolling back each time")
    run_1 = run_legacy.run_in_transaction(cur, spec, tables, None, out / "run1")
    time.sleep(1)  # make sure a clock value can't land on the same tick by luck
    run_2 = run_legacy.run_in_transaction(cur, spec, tables, None, out / "run2")
    print(f"   return codes: {run_1[0]}, {run_2[0]}")

    print("3. Comparing the two runs\n")
    evidence = {"job": job_name, "proc": spec["proc"], "probed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "method": "staged once, ran the legacy job twice in separate rolled-back transactions, "
                          "compared every column of every table",
                "tables": {}, "unstable": {}}
    for table in tables:
        name = discover.file_name(table)
        rows_1 = pq.read_table(out / "run1" / f"{name}.parquet").to_pylist()
        rows_2 = pq.read_table(out / "run2" / f"{name}.parquet").to_pylist()
        cols = unstable_columns(rows_1, rows_2)
        identity = discover.identity_columns(cur, table)

        # With the unstable columns left out, the two runs must agree row for row.
        # If they don't, the job is not repeatable and no verdict on it could be trusted.
        same = diff.reconcile(rows_1, rows_2, None, cols)["status"] == "pass"
        evidence["tables"][name] = {"rows": len(rows_1), "unstable_columns": cols,
                                    "runs_agree_on_everything_else": same}
        if cols:
            evidence["unstable"][name] = {}
        for col in cols:
            only_1 = list((column_values(rows_1, col) - column_values(rows_2, col)).elements())
            only_2 = list((column_values(rows_2, col) - column_values(rows_1, col)).elements())
            evidence["unstable"][name][col] = {
                "reason": reason(col, identity, rows_1, rows_2),
                "rows_that_differ": len(only_1),
                "example_run_1": str(sorted(only_1, key=str)[0]) if only_1 else None,
                "example_run_2": str(sorted(only_2, key=str)[0]) if only_2 else None,
            }
        flag = "" if same else "   <-- runs disagree even without these columns!"
        print(f"   {name:30} {', '.join(cols) if cols else 'stable'}{flag}")

    path = jobspec.JOBS_DIR / "evidence" / f"{job_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"\n   evidence saved to {path}")


if __name__ == "__main__":
    main()
