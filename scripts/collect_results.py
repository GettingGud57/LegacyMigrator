"""
collect_results.py: gather every verdict into docs/reports/data/results.json for the dashboard.

Reads, for each job that has been checked:
    snapshots/<job>/meta.json        legacy run: procedure time, row counts, staging window
    snapshots/<job>/spark/run.json   Spark run: time
    snapshots/<job>/check.json       the verdict per table (check.py)
    jobs/evidence/<job>.json         which columns were ignored, and the evidence why

Field names follow docs/results-contract.md on the dashboard branch where they mean the same
thing (table, key_cols, ignored, rows_legacy, rows_spark, extra_checks), but this file is a
flat list of checked runs, not the retry loop's attempt history.

Usage (from the repo root):
    python scripts/collect_results.py
"""
import json
import time
from pathlib import Path

JOBS = [  # (dataset label, snapshot job name, translated job)
    ("dev", "sale", "sale"),
    ("holdout", "sale_holdout", "sale"),
    ("dev", "city", "city"),
    ("dev", "movement", "movement"),
]
OUT = Path("docs/reports/data/results.json")


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def table_entry(t):
    checks = t.get("checks", {})
    return {
        "table": t["table"],
        "status": t["status"],
        "key_cols": t.get("key_columns") or None,
        "ignored": [{"column": c, "reason": r} for c, r in t.get("ignored_columns", {}).items()],
        "rows_before": t.get("rows_before"),
        "rows_legacy": t.get("rows_legacy"),
        "rows_spark": t.get("rows_spark"),
        "rows_changed_by_legacy": t.get("changed_by_legacy"),
        "compared_cols": t.get("compared_columns", []),
        "result": checks.get("whole_rows"),
        "extra_checks": [dict(name=n, **c) for n, c in checks.items() if n != "whole_rows"],
    }


def main():
    runs = []
    for dataset, job, translated in JOBS:
        base = Path("snapshots") / job
        meta, verdict = read(base / "meta.json"), read(base / "check.json")
        if not meta or not verdict:
            print(f"   skipping {job}: not run and checked yet")
            continue
        spark = read(base / "spark" / "run.json") or {}
        evidence = read(Path("jobs/evidence") / f"{job}.json")
        runs.append({
            "job": translated,
            "dataset": dataset,
            "snapshot": job,
            "ai_can_see": dataset != "holdout",
            "proc": meta["proc"],
            "spark_file": spark.get("spark_job"),
            "status": verdict["status"],
            "staging_window": meta.get("staging_params") or "default: the month up to the ETL cutoff",
            "legacy_proc_seconds": meta.get("proc_seconds"),
            "spark_job_seconds": spark.get("job_and_write_seconds"),
            "spark_total_seconds": spark.get("total_seconds_including_spark_startup"),
            "tables_found_by_metadata": meta.get("tables_found"),
            "probe": {"method": evidence["method"], "probed_at": evidence["probed_at"]} if evidence else None,
            "tables": [table_entry(t) for t in verdict["tables"]],
        })
        print(f"   {translated:9} {dataset:8} {verdict['status'].upper()}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample": False,
        "notes": ["Real runs on the cloud test bench (SQL Server 2022 in Docker, PySpark local mode).",
                  "City and Movement are first-attempt AI translations, unedited."],
        "runs": runs,
    }, indent=2, default=str) + "\n")
    print(f"   saved to {OUT}")


if __name__ == "__main__":
    main()
