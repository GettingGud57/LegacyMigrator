"""
test_bench_to_results.py: turn the test bench's real results into the dashboard's results file.

The test bench (branch claude/test-bench) writes:

    docs/reports/data/results.json        one entry per job and dataset, check.py verdicts per table
    docs/reports/data/planted_bugs.json   bugs planted in jobs_pyspark/sale.py, and whether check.py caught them

This script reads those (plus each job's PySpark file and the legacy SQL) and writes one file in
the format of docs/results-contract.md, so the dashboard can show them. It never merges branches:
with --ref it reads the files straight out of git, otherwise from the working tree.

Usage (from the repo root):
    python scripts/test_bench_to_results.py --ref origin/claude/test-bench
    python scripts/test_bench_to_results.py               # once test-bench is merged
    python scripts/check_results.py dashboard/public/data/real.json
"""
import argparse
import json
import subprocess
from pathlib import Path

LEGACY_SQL = {
    "sale": "legacy_jobs/wwi/MigrateStagedSaleData.sql",
    "city": "legacy_jobs/wwi/MigrateStagedCityData.sql",
    "movement": "legacy_jobs/wwi/MigrateStagedMovementData.sql",
}
SUMMARY = {
    "sale": "Looks up five dimension keys for each staged sale line, then replaces those invoices in "
            "Fact.Sale and closes the load in the lineage log.",
    "city": "Closes off the current version of each changed city and inserts the new versions, "
            "keeping the full history.",
    "movement": "Looks up four dimension keys, then MERGEs stock movements into Fact.Movement: "
                "update the ones that exist, insert the rest.",
}

# Human analysis of each run, from docs/reports/test-bench.html on claude/test-bench.
# Shown as a note on the attempt, clearly separate from what the AI was told.
ATTEMPT_NOTES = {
    "movement": (
        "The MERGE itself is right: all 5,053 updated movement rows match. The failure is one realistic "
        "mistake. The code casts timestamps with .cast(\"timestamp\"), which in Spark means a moment in time "
        "with a time zone. SQL Server's datetime2 has no time zone (Spark calls that timestamp_ntz). "
        "The values are the same moment, but the column changed type: 2016-06-06 12:31:17 came back as "
        "2016-06-06 12:31:17+00:00. A downstream report would now apply time zone rules to it, so it "
        "counts as a real failure. The Sale translation avoided it by casting to the input column's own type."
    ),
}

# Why each planted bug was or wasn't caught, from the same report. planted_bugs.json has no reasons.
BUG_WHY = {
    "real_translation": "Control. Must pass both, or the checker cries wolf.",
    "changed_rows_only": "Fact.Sale shrinks from 228,265 rows to the few thousand reloaded ones.",
    "default_decimal": "39,717 sale lines have cents in the unit price; decimal(10,0) rounds them away.",
    "no_delete": "Reloaded invoices appear twice: old lines plus new ones.",
    "no_valid_to": "Picks a customer's or product's oldest version instead of the one valid at sale time.",
    "null_not_zero": "Thousands of lookups find no dimension row in every window, so NULLs show up straight away.",
    "forget_cutoff": "On dev the job sets the cutoff to the value it already had, so skipping the update "
                     "looks perfect. The holdout window moves the cutoff.",
    "ge_valid_from": "No sale is stamped exactly at a version start, so >= and > always agree on this data "
                     "(0 such lines in every month). Would catch it: a small boundary dataset with a sale "
                     "at exactly a Valid From.",
    "tax_rate_scale": "Every tax rate is 15.000 or 10.000, and Python compares 15.000 == 15.00 as equal, so "
                      "values match. Would catch it: comparing column types between after/ and spark/.",
    "top1_desc": "776 dev lookups match two City versions, but in every case both have the same Valid From "
                 "(a tie), and real version histories never overlap otherwise. So reversing the date order "
                 "can never change a result here. Would catch it: only a dimension with overlapping date "
                 "ranges, which is broken data.",
}


class Source:
    """Reads repo files from a git ref (e.g. origin/claude/test-bench) or from the working tree."""

    def __init__(self, ref):
        self.ref = ref

    def text(self, path):
        if self.ref:
            out = subprocess.run(["git", "show", f"{self.ref}:{path}"], capture_output=True, text=True)
            if out.returncode != 0:
                raise SystemExit(f"git show {self.ref}:{path} failed: {out.stderr.strip()}")
            return out.stdout
        return Path(path).read_text(encoding="utf-8")

    def json(self, path):
        return json.loads(self.text(path))


def check_detail(name, c):
    """One plain sentence for each of check.py's extra checks."""
    if name == "untouched_rows":
        n = c.get("rows_checked", 0)
        if c["status"] == "pass":
            return (f"All {n:,} rows the old job left alone came out of the new code identical, "
                    "ignored columns included.")
        return (f"Of the {n:,} rows the old job left alone, {c.get('rows_only_in_legacy', 0):,} are missing "
                "or changed in the new output (checked with ignored columns included).")
    if name == "unique_key":
        if c["status"] == "pass":
            return "No key value appears twice in the new output."
        return f"{c.get('duplicate_keys', 0):,} key values appear more than once in the new output."
    return c["status"]


def table_entry(t):
    ignored = t.get("ignored") or []
    ignored_names = {i["column"] for i in ignored}
    whole = t["result"]
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
        # check.py compares ignored columns only as "filled in or empty"; their values aren't compared
        "compared_cols": [c for c in t["compared_cols"] if c not in ignored_names],
        # the test bench keeps counts and a few examples, not whole rows
        "only_a": [],
        "only_b": [],
        "cols_only_a": whole.get("columns_only_in_legacy", []),
        "cols_only_b": whole.get("columns_only_in_spark", []),
        "explanation": explanation,
    }
    counts = {"only_a": whole.get("rows_only_in_legacy", 0), "only_b": whole.get("rows_only_in_spark", 0)}
    if "cells_changed" in whole:
        counts["changed"] = whole["cells_changed"]
    extra = []
    if ignored:
        extra.append({"name": "ignored_columns_filled", "status": whole["status"],
                      "detail": "Ignored columns still had to be filled in (or empty) on exactly the same rows "
                                "as the old output. Only their values were skipped."})
    for c in t.get("extra_checks", []):
        extra.append({"name": c["name"], "status": c["status"], "detail": check_detail(c["name"], c)})
    return {
        "table": t["table"],
        "key_cols": t.get("key_cols") or None,
        "ignored": ignored,
        "rows_legacy": t["rows_legacy"],
        "rows_spark": t["rows_spark"],
        "rows_changed_by_legacy": t.get("rows_changed_by_legacy"),
        "result": result,
        "counts": counts,
        "extra_checks": extra,
    }


def window_text(w):
    if isinstance(w, dict):
        return f"Staged {w['window_from'][:10]} to {w['window_to'][:10]}"
    # e.g. "default: the month up to the ETL cutoff"
    text = str(w).replace("default: ", "")
    return text[:1].upper() + text[1:]


def run_entry(r):
    tables = [table_entry(t) for t in r["tables"]]
    staging = next((t for t in tables if t["table"].endswith("_Staging")), None)
    window = window_text(r.get("staging_window", ""))
    if staging:
        window += f", {staging['rows_legacy']:,} staged rows"
    probe = r.get("probe") or {}
    return {
        "tables": tables,
        "seconds": r.get("spark_total_seconds"),
        "legacy_seconds": r.get("legacy_proc_seconds"),
        "window": window,
        "stability_probe": (f"{probe['method'][0].upper()}{probe['method'][1:]} ({probe.get('probed_at', '')}). "
                            "Only columns that differed between those two runs may be ignored.")
        if probe.get("method") else None,
    }


def all_pass(run):
    return bool(run) and all(
        t["result"]["status"] == "pass" and all(c["status"] == "pass" for c in t["extra_checks"])
        for t in run["tables"])


def job_entry(src, job_id, runs):
    dev = next((r for r in runs if r["dataset"] == "dev"), None)
    hold = next((r for r in runs if r["dataset"] == "holdout"), None)
    dev_run = run_entry(dev) if dev else None
    hold_run = run_entry(hold) if hold else None
    first = dev or hold
    seconds = None
    if dev:
        seconds = round(sum(x for x in (dev.get("spark_total_seconds"), dev.get("legacy_proc_seconds")) if x), 1)

    if all_pass(dev_run) and all_pass(hold_run):
        status, stop = "verified", None
    elif all_pass(dev_run):
        status, stop = "in_progress", "Matches on dev data. Holdout data hasn't been prepared for this job yet."
    else:
        status = "failed"
        stop = "First attempt, no retry yet: the retry loop (loop.py) isn't built, so nothing was sent back to the AI."
    return {
        "id": job_id,
        "name": job_id.title(),
        "proc": first["proc"],
        "source_file": LEGACY_SQL[job_id],
        "summary": SUMMARY.get(job_id),
        "status": status,
        "stop_reason": stop,
        "max_attempts": None,
        "legacy_sql": Path(LEGACY_SQL[job_id]).read_text(encoding="utf-8-sig"),
        "attempts": [{
            "number": 1,
            "started_at": None,
            "seconds": seconds,
            "code": src.text(first["spark_file"]),
            "error": None,
            "error_stage": None,
            "feedback": None,
            "note": ATTEMPT_NOTES.get(job_id),
            "runs": {"dev": dev_run, "holdout": hold_run},
        }],
    }


def checker_tests(bugs):
    out = []
    for b in bugs["bugs"]:
        def run(r):
            return {"status": r["status"], "crashed": r.get("crashed", False),
                    "failed_tables": [{"table": f["table"], "failed_checks": f["failed_checks"],
                                       "changed_columns": f.get("changed_columns", [])}
                                      for f in r.get("failed_tables", [])]}
        out.append({
            "name": b["bug"],
            "description": b["description"],
            "control": b["bug"] == "real_translation",
            "dev": run(b["runs"]["dev"]),
            "holdout": run(b["runs"]["holdout"]),
            "outcome": b["outcome"],
            "why": b.get("why") or BUG_WHY.get(b["bug"], ""),
        })
    return {"what": bugs["what"], "generated_at": bugs["generated_at"], "job": "sale", "bugs": out}


def main():
    parser = argparse.ArgumentParser(description="test bench results -> dashboard results file")
    parser.add_argument("--ref", help="read the test bench files from this git ref, e.g. origin/claude/test-bench")
    parser.add_argument("--out", default="dashboard/public/data/real.json")
    args = parser.parse_args()
    src = Source(args.ref)

    collected = src.json("docs/reports/data/results.json")
    bugs = src.json("docs/reports/data/planted_bugs.json")
    order = []
    for r in collected["runs"]:
        if r["job"] not in order:
            order.append(r["job"])
    jobs = [job_entry(src, j, [r for r in collected["runs"] if r["job"] == j]) for j in order]

    results = {
        "contract_version": 1,
        "sample": False,
        "generated_at": collected["generated_at"],
        "title": "Test bench, real runs",
        "notes": collected.get("notes", []) + [
            "Each job has one attempt: the AI's first translation, unedited. The retry loop isn't built yet.",
            f"Converted from {args.ref or 'the working tree'} by scripts/test_bench_to_results.py.",
        ],
        "datasets": {
            "dev": {"label": "Dev data", "ai_can_see": True,
                    "description": "The month of staged data up to the warehouse's ETL cutoff. The AI may "
                                   "learn from differences found here."},
            "holdout": {"label": "Holdout data", "ai_can_see": False,
                        "description": "A different month the AI never sees: not in prompts, not in feedback, "
                                       "not in the folder it runs in."},
        },
        "jobs": jobs,
        "checker_tests": checker_tests(bugs),
    }
    out = Path(args.out)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for j in jobs:
        print(f"   {j['id']:10} {j['status']}")
    caught = sum(1 for b in results["checker_tests"]["bugs"] if not b["control"] and "caught by nothing" not in b["outcome"])
    print(f"   planted bugs caught: {caught} of {len(results['checker_tests']['bugs']) - 1}")


if __name__ == "__main__":
    main()
