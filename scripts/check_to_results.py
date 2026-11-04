"""
check_to_results.py: turn migrator/check.py output into the dashboard's results file.

check.py (branch claude/test-bench) writes one verdict file per job and dataset:

    snapshots/<job>/check.json            dev data
    snapshots/<job>_holdout/check.json    holdout data (if it exists)

This script reads those, plus the job spec (jobs/<job>.json) and the translation
(jobs_pyspark/<job>.py), and writes one file in the format of docs/results-contract.md.
There is no retry loop yet, so each job gets a single attempt. Once loop.py exists it
should write the results file itself, attempts and all, and this script can go.

Usage (from the repo root):
    python scripts/check_to_results.py sale [city movement ...]
    python scripts/check_to_results.py sale --out dashboard/public/data/results.json
    python scripts/check_results.py dashboard/public/data/results.json
"""
import argparse
import json
import time
from pathlib import Path


def read_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def check_detail(name, check):
    """One plain sentence for each of check.py's extra checks."""
    if name == "untouched_rows":
        n = check.get("rows_checked", 0)
        if check["status"] == "pass":
            return (f"All {n:,} rows the old job left alone are identical in the new output, "
                    "ignored columns included.")
        return (f"Of the rows the old job left alone, {check['rows_only_in_legacy']:,} are missing "
                f"or changed in the new output (checked with ignored columns included).")
    if name == "unique_key":
        if check["status"] == "pass":
            return "No key value appears twice in the new output."
        return f"{check['duplicate_keys']:,} key values appear more than once in the new output."
    return check["status"]


def table_entry(t):
    """check.py's table verdict -> a TableResult."""
    ignored = [{"column": c, "reason": r} for c, r in sorted((t.get("ignored_columns") or {}).items())]
    if "error" in t:  # e.g. the Spark output file is missing
        return {"table": t["table"], "key_cols": None, "ignored": ignored, "rows_legacy": None,
                "rows_spark": None, "result": None,
                "extra_checks": [{"name": "spark_output", "status": "fail", "detail": t["error"]}]}

    whole = t["checks"]["whole_rows"]
    explanation = None
    if whole.get("examples"):
        explanation = {
            "cols_only_a": [], "cols_only_b": [], "rows_only_a": [], "rows_only_b": [],
            "dupes_a": [], "dupes_b": [],
            "changed": [{"key": e["key"], "col": e["column"], "a": e["legacy"], "b": e["spark"]}
                        for e in whole["examples"]],
        }
    result = {
        "status": whole["status"],
        # check.py still compares ignored columns as "filled in or empty". Their values aren't
        # compared, so they're listed under "ignored" (and the extra check below), not here.
        "compared_cols": [c for c in t["compared_columns"] if c not in (t.get("ignored_columns") or {})],
        # check.py keeps counts, not the rows themselves, so only the counts below are known
        "only_a": [],
        "only_b": [],
        "cols_only_a": whole["columns_only_in_legacy"],
        "cols_only_b": whole["columns_only_in_spark"],
        "explanation": explanation,
    }
    counts = {"only_a": whole["rows_only_in_legacy"], "only_b": whole["rows_only_in_spark"]}
    if "cells_changed" in whole:
        counts["changed"] = whole["cells_changed"]
    extra = [{"name": name, "status": c["status"], "detail": check_detail(name, c)}
             for name, c in t["checks"].items() if name != "whole_rows"]
    if ignored:
        extra.insert(0, {"name": "ignored_columns_filled", "status": whole["status"],
                         "detail": "Ignored columns still had to be filled in (or empty) on exactly "
                                   "the same rows as the old output. Only their values were skipped."})
    return {
        "table": t["table"], "key_cols": t.get("key_columns") or None, "ignored": ignored,
        "rows_legacy": t["rows_legacy"], "rows_spark": t["rows_spark"],
        "result": result, "counts": counts, "extra_checks": extra,
    }


def run_from_check(check):
    if not check:
        return None
    return {"tables": [table_entry(t) for t in check["tables"]]}


def all_pass(run):
    return bool(run) and all(
        t["result"] and t["result"]["status"] == "pass"
        and all(c["status"] == "pass" for c in t.get("extra_checks", []))
        for t in run["tables"])


def job_entry(name):
    spec = read_json(f"jobs/{name}.json") or {}
    sql_path = Path(spec.get("legacy_sql", ""))
    code_path = Path("jobs_pyspark") / f"{name}.py"
    dev = run_from_check(read_json(f"snapshots/{name}/check.json"))
    holdout = run_from_check(read_json(f"snapshots/{name}_holdout/check.json"))
    run_info = read_json(f"snapshots/{name}/run.json") or {}

    attempts = []
    if dev:
        attempts.append({
            "number": 1,
            "started_at": None,
            "seconds": run_info.get("seconds"),
            "code": code_path.read_text(encoding="utf-8") if code_path.exists() else "",
            "error": None,
            "error_stage": None,
            "feedback": None,
            "runs": {"dev": dev, "holdout": holdout},
        })

    if not attempts:
        status = "not_started"
    elif all_pass(dev) and all_pass(holdout):
        status = "verified"
    elif all_pass(dev):
        status = "in_progress"  # dev matches, holdout not run (or not all passing yet)
    else:
        status = "failed"  # one attempt, no loop yet to retry
    return {
        "id": name,
        "name": name.replace("_", " ").title(),
        "proc": spec.get("proc", name),
        "source_file": str(sql_path) if spec.get("legacy_sql") else None,
        "status": status,
        "max_attempts": None,
        "legacy_sql": sql_path.read_text(encoding="utf-8-sig") if sql_path.is_file() else "",
        "attempts": attempts,
    }


def main():
    parser = argparse.ArgumentParser(description="check.py output -> dashboard results file")
    parser.add_argument("jobs", nargs="+")
    parser.add_argument("--out", default="dashboard/public/data/results.json")
    args = parser.parse_args()

    results = {
        "contract_version": 1,
        "sample": False,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": "Latest check.py run",
        "notes": ["Built from migrator/check.py output by scripts/check_to_results.py. "
                  "One attempt per job: the retry loop isn't built yet."],
        "datasets": {
            "dev": {"label": "Dev data", "ai_can_see": True,
                    "description": "The data the AI may learn from."},
            "holdout": {"label": "Holdout data", "ai_can_see": False,
                        "description": "A different slice of data the AI never sees."},
        },
        "jobs": [job_entry(name) for name in args.jobs],
    }
    out = Path(args.out)
    out.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for job in results["jobs"]:
        print(f"   {job['id']:12} {job['status']}")
    print('Add it to dashboard/public/data/manifest.json, e.g. {"id": "results", "label": "Latest run", "path": "results.json"}')


if __name__ == "__main__":
    main()
