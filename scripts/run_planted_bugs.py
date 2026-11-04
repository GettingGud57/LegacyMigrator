"""
run_planted_bugs.py: does the checker catch planted bugs? ("We tested our tester.")

For the real translation and for every copy in experiments/planted_bugs/, on the dev data (sale)
and on the holdout data (sale_holdout):
    1. run it with migrator/run_spark.py           -> snapshots/<dataset>/planted/<bug>/
    2. judge it with migrator/check.py (diff.reconcile inside), the same checker the project uses

A planted bug should FAIL. The real translation should PASS. Results go to
docs/reports/data/planted_bugs.json and are printed as a table.

Usage (from the repo root, after run_legacy.py for sale and sale_holdout):
    python scripts/make_planted_bugs.py
    python scripts/run_planted_bugs.py
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "migrator")
import check  # noqa: E402

DATASETS = {"dev": "sale", "holdout": "sale_holdout"}
BUG_DIR = Path("experiments/planted_bugs")
OUT = Path("docs/reports/data/planted_bugs.json")


def describe(path):
    first = path.read_text().splitlines()[0]
    return first.split(": ", 1)[1].rstrip(".") if path.parent == BUG_DIR else "the real AI translation, no planted bug"


def run_one(name, code, job):
    spark_dir = Path("snapshots") / job / "planted" / name
    started = time.perf_counter()
    run = subprocess.run([sys.executable, "migrator/run_spark.py", job, str(code), str(spark_dir)],
                         capture_output=True, text=True)
    if run.returncode != 0:
        # A crash counts as caught: the job can't produce output at all
        return {"status": "fail", "crashed": True, "error": run.stderr.strip().splitlines()[-1][:300],
                "failed_tables": [], "seconds": round(time.perf_counter() - started, 1)}
    result = check.check_job(job, spark_dir)
    failed = []
    for t in result["tables"]:
        if t["status"] == "fail":
            bad = {n: c for n, c in t.get("checks", {}).items() if c["status"] == "fail"}
            failed.append({
                "table": t["table"],
                "failed_checks": sorted(bad),
                "rows_unmatched_legacy": max([c.get("rows_only_in_legacy", 0) for c in bad.values()] or [0]),
                "rows_unmatched_spark": max([c.get("rows_only_in_spark", 0) for c in bad.values()] or [0]),
                "changed_columns": sorted({col for c in bad.values() for col in c.get("changed_columns", {})}),
            })
    return {"status": result["status"], "crashed": False, "failed_tables": failed,
            "seconds": round(time.perf_counter() - started, 1)}


def main():
    entries = [("real_translation", Path("jobs_pyspark/sale.py"))]
    entries += [(p.stem, p) for p in sorted(BUG_DIR.glob("*.py"))]
    results = []
    for name, code in entries:
        row = {"bug": name, "description": describe(code), "file": str(code), "runs": {}}
        for dataset, job in DATASETS.items():
            row["runs"][dataset] = run_one(name, code, job)
            r = row["runs"][dataset]
            tables = ", ".join(t["table"] for t in r["failed_tables"]) or ("crashed" if r["crashed"] else "-")
            print(f"   {name:18} {dataset:8} {r['status'].upper():5} {r['seconds']:6.1f}s  {tables}", flush=True)
        dev, hold = row["runs"]["dev"]["status"], row["runs"]["holdout"]["status"]
        if name == "real_translation":
            row["outcome"] = "passes both, as it should" if dev == hold == "pass" else "WRONG: real translation failed"
        else:
            row["outcome"] = ("caught by dev" if dev == "fail" else
                              "caught only by holdout" if hold == "fail" else "caught by nothing")
        results.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "what": "Planted bugs in jobs_pyspark/sale.py, each run through run_spark.py and check.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sample": False,
        "datasets": {"dev": {"job": "sale", "ai_can_see": True}, "holdout": {"job": "sale_holdout", "ai_can_see": False}},
        "bugs": results,
    }, indent=2, default=str) + "\n")
    print("\n   summary")
    for row in results:
        print(f"   {row['bug']:18} {row['outcome']}")
    print(f"\n   saved to {OUT}")


if __name__ == "__main__":
    main()
