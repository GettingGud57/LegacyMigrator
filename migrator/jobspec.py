"""
jobspec.py: read a job spec from jobs/<job>.json.

A job spec says which legacy procedure to run and how to stage its input.
Everything else is optional, because run_legacy.py can work it out from the database:

    {
      "database": "WideWorldImportersDW",
      "proc": "Integration.MigrateStagedSaleData",
      "legacy_sql": "legacy_jobs/wwi/MigrateStagedSaleData.sql",
      "staging_script": "scripts/load_sale_staging.sql",

      optional:
      "extends": "sale",                      copy another spec, then apply the fields below
      "staging_params": {"window_from": ...}, passed to the staging script (see run_legacy.py)
      "tables": [...],                        skip discovery and use this list
      "keys":   {"Fact.Sale": ["Sale Key"]},  skip discovery for these tables
      "ignore": {"Fact.Sale": {"Sale Key": "why it can never match"}}
    }

Columns to ignore also come from jobs/evidence/<job>.json, which probe.py writes after
running the legacy job twice on the same input. A column is only ever ignored with a reason.
"""
import json
from pathlib import Path

JOBS_DIR = Path("jobs")


def load(name):
    path = JOBS_DIR / f"{name}.json"
    if not path.exists():
        known = sorted(p.stem for p in JOBS_DIR.glob("*.json"))
        raise SystemExit(f"No job spec {path}. Known jobs: {', '.join(known)}")
    spec = json.loads(path.read_text())
    if "extends" in spec:
        parent = load(spec["extends"])
        parent.update({k: v for k, v in spec.items() if k != "extends"})
        spec = parent
    spec["name"] = name
    return spec


def evidence(name):
    """What probe.py found for this job, or {} if it hasn't been run."""
    path = JOBS_DIR / "evidence" / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def ignored_columns(spec, table):
    """{column: reason} for one table: hand-written ones from the spec, plus probe evidence."""
    out = dict(spec.get("ignore", {}).get(table, {}))
    for col, info in evidence(spec.get("evidence_from", spec["name"])).get("unstable", {}).get(table, {}).items():
        out.setdefault(col, info["reason"])
    return out
