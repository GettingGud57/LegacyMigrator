"""
check.py: the verdict. Compares the legacy answer key with what the PySpark job produced.

    snapshots/<job>/after/    the answer key (legacy SQL Server output)
    snapshots/<job>/spark/    what the PySpark translation produced
    snapshots/<job>/check.json  the verdict, one entry per table

Every comparison goes through diff.reconcile, the hand-written checker. This file only
decides WHICH rows and columns to hand it, using the job spec (jobs/<job>.json).

Some columns can never match, even between two runs of the legacy job itself
(an identity number, a SYSDATETIME() timestamp). Ignoring them outright would make the
checker blind to real bugs in those columns, so for each ignored column we still check:

  1. whole rows:      every other column must match exactly, and the ignored column must be
                      filled in (or empty) on exactly the same rows as in the legacy output.
  2. untouched rows:  rows the legacy job did not change must come out of Spark byte for byte,
                      ignored columns included. Only rows the job really wrote get a pass.
  3. unique key:      the Spark output must not repeat a primary key value.

A table passes only if all of its checks pass. A job passes only if every table passes.

Usage (from the repo root):
    python migrator/check.py sale
    python migrator/check.py sale_holdout --spark-dir snapshots/sale_holdout/spark
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import diff  # noqa: E402  (the hand-written checker, next to this file)
import jobspec  # noqa: E402

# What an ignored column's value is replaced with when it has one.
# NULL stays NULL, so "filled in vs empty" is still compared.
PRESENT = "<value present, not compared>"


def load_rows(path):
    return pq.read_table(path).to_pylist()


def mask(rows, cols):
    """Copy of rows where each column in cols only says whether it has a value."""
    if not cols:
        return rows
    out = []
    for row in rows:
        row = dict(row)
        for col in cols:
            if row.get(col) is not None:
                row[col] = PRESENT
        out.append(row)
    return out


def untouched(rows, before_rows):
    """The rows that also appear, identical in every column, in before_rows (multiset aware)."""
    if not rows:
        return []
    cols = sorted(rows[0])
    left = Counter(tuple(r.get(c) for c in cols) for r in before_rows)
    kept = []
    for row in rows:
        t = tuple(row[c] for c in cols)
        if left[t] > 0:
            left[t] -= 1
            kept.append(row)
    return kept


def duplicate_keys(rows, key_cols):
    counts = Counter(tuple(r[c] for c in key_cols) for r in rows)
    return [k for k, n in counts.items() if n > 1]


def summarise(result, limit=5):
    """The small, JSON-friendly part of a diff.reconcile result."""
    out = {
        "status": result["status"],
        "rows_only_in_legacy": len(result["only_a"]),
        "rows_only_in_spark": len(result["only_b"]),
        "columns_only_in_legacy": result["cols_only_a"],
        "columns_only_in_spark": result["cols_only_b"],
    }
    ex = result["explanation"]
    if ex:
        changed = sorted(ex["changed"], key=lambda c: (str(c["key"]), c["col"]))
        out["rows_changed"] = len({c["key"] for c in changed})
        out["cells_changed"] = len(changed)
        out["changed_columns"] = dict(Counter(c["col"] for c in changed).most_common())
        out["keys_only_in_legacy"] = len(ex["rows_only_a"])
        out["keys_only_in_spark"] = len(ex["rows_only_b"])
        out["examples"] = [
            {"key": list(c["key"]), "column": c["col"], "legacy": str(c["a"]), "spark": str(c["b"])}
            for c in changed[:limit]
        ]
    return out


def check_table(table, before, after, spark, key_cols, ignore):
    """All checks for one table. ignore = {column: reason}."""
    ignored = sorted(ignore)
    checks = {}

    # 1. Whole rows, ignored columns reduced to "has a value or not"
    whole = diff.reconcile(mask(after, ignored), mask(spark, ignored), key_cols)
    checks["whole_rows"] = summarise(whole)

    # 2. Rows the legacy job left alone must be untouched in Spark too, every column compared
    if ignored:
        strict = diff.reconcile(untouched(after, before), untouched(spark, before), key_cols)
        checks["untouched_rows"] = summarise(strict)
        checks["untouched_rows"]["rows_checked"] = len(untouched(after, before))

    # 3. The Spark output must respect the table's primary key
    if key_cols:
        dupes = duplicate_keys(spark, key_cols)
        checks["unique_key"] = {
            "status": "fail" if dupes else "pass",
            "duplicate_keys": len(dupes),
            "examples": [list(k) for k in dupes[:5]],
        }

    passed = all(c["status"] == "pass" for c in checks.values())
    return {
        "table": table,
        "status": "pass" if passed else "fail",
        "rows_before": len(before),
        "rows_legacy": len(after),
        "rows_spark": len(spark),
        "changed_by_legacy": len(after) - len(untouched(after, before)),
        "key_columns": key_cols,
        "compared_columns": whole["compared_cols"],
        "ignored_columns": ignore,
        "checks": checks,
    }


def check_job(job_name, spark_dir=None, after_dir=None):
    spec = jobspec.load(job_name)
    base = Path("snapshots") / job_name
    before_dir = base / "before"
    after_dir = Path(after_dir) if after_dir else base / "after"
    spark_dir = Path(spark_dir) if spark_dir else base / "spark"
    meta = json.loads((base / "meta.json").read_text()) if (base / "meta.json").exists() else {}
    keys = meta.get("keys", {})
    tables = []
    for f in sorted(after_dir.glob("*.parquet")):
        name = f.stem
        spark_file = spark_dir / f.name
        if not spark_file.exists():
            tables.append({"table": name, "status": "fail", "error": f"missing {spark_file}"})
            continue
        tables.append(check_table(
            name,
            load_rows(before_dir / f.name),
            load_rows(f),
            load_rows(spark_file),
            spec.get("keys", {}).get(name) or keys.get(name) or [],
            jobspec.ignored_columns(spec, name),
        ))
    passed = bool(tables) and all(t["status"] == "pass" for t in tables)
    return {
        "job": job_name,
        "status": "pass" if passed else "fail",
        "legacy_dir": str(after_dir),
        "spark_dir": str(spark_dir),
        "tables": tables,
    }


def print_result(result):
    print(f"\n{result['job']}: {result['status'].upper()}\n")
    print(f"   {'table':28} {'verdict':8} {'rows':>8} {'changed':>8}  notes")
    for t in result["tables"]:
        if "error" in t:
            print(f"   {t['table']:28} {'FAIL':8}  {t['error']}")
            continue
        notes = []
        for name, c in t["checks"].items():
            if c["status"] != "pass":
                if name == "unique_key":
                    notes.append(f"unique_key failed ({c['duplicate_keys']} repeated keys)")
                    continue
                cols = ", ".join(list(c.get("changed_columns", {}))[:4])
                notes.append(f"{name} failed ({c['rows_only_in_legacy']} legacy rows and "
                             f"{c['rows_only_in_spark']} spark rows unmatched{': ' + cols if cols else ''})")
        if t["ignored_columns"] and not notes:
            notes.append("ignored: " + ", ".join(t["ignored_columns"]))
        print(f"   {t['table']:28} {t['status'].upper():8} {t['rows_legacy']:>8} "
              f"{t['changed_by_legacy']:>8}  {'; '.join(notes)}")


def main():
    parser = argparse.ArgumentParser(description="Compare legacy output with the Spark output.")
    parser.add_argument("job")
    parser.add_argument("--spark-dir", help="default: snapshots/<job>/spark")
    parser.add_argument("--after-dir", help="default: snapshots/<job>/after")
    parser.add_argument("--out", help="default: snapshots/<job>/check.json")
    args = parser.parse_args()

    result = check_job(args.job, args.spark_dir, args.after_dir)
    out = Path(args.out) if args.out else Path("snapshots") / args.job / "check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    print_result(result)
    print(f"\n   details in {out}")
    sys.exit(0 if result["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
