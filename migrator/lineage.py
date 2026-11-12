"""
lineage.py: column-level lineage for one legacy job.

For every table the legacy procedure writes, it says where each column's value comes from:

    lineage/<job>.json   the map, plus the result of the checks below
    lineage/<job>.md     the same map as tables, for people to read and review

The map is drafted by Claude from the legacy SQL and the table columns (names and types only,
no data). A lineage map has no answer key, so unlike a translation it cannot be proven right.
Two things keep it honest:

    structure checks   run here without AI: every column of every written table is covered, every
                       source column really exists, each kind has the sources it needs, and cited
                       line numbers exist. Failures go back to Claude for one more try.
    cross-checks       compare the map with evidence Claude never saw: the columns a human chose to
                       ignore in jobs/<job>.json, and which tables the legacy job really changed in
                       snapshots/<job>/. Disagreements are reported for a human and never sent back,
                       so the map cannot be bent to fit them.

It reads only the dev snapshot, never a holdout, and nothing it writes is given to the translator.

Usage (from the repo root, after run_legacy.py has made snapshots/<job>/):
    python migrator/lineage.py sale
    python migrator/lineage.py sale --check     # rerun the checks on lineage/sale.json, no API call
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

import translate

OUT_DIR = Path("lineage")
ATTEMPTS = 2  # the first draft, then one more try if the structure checks fail

# kind -> (what it means, does it need source columns?)
KINDS = {
    "copied": ("taken from one source column as it is", True),
    "lookup": ("found by matching a row in another table (a join or subquery)", True),
    "calculated": ("worked out from source columns (an expression, CASE, ISNULL, aggregate, ...)", True),
    "constant": ("a fixed value written in the SQL", False),
    "generated": ("made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...)", False),
    "unchanged": ("the procedure never writes this column", False),
}

PROMPT = """You are documenting a legacy SQL Server stored procedure for a migration team.

Produce its column-level lineage: for every table the procedure writes to (INSERT, UPDATE, DELETE
or MERGE), say where each column's value comes from.

Reply with exactly one ```json code block and nothing else, in this shape:

{{
  "tables": {{
    "<table name, exactly as listed below>": {{
      "operations": ["INSERT", "UPDATE", "DELETE" or "MERGE", in the order the procedure does them],
      "columns": {{
        "<column name, exactly as listed below>": {{
          "kind": "<one of: {kinds}>",
          "sources": [{{"table": "<table name>", "column": "<column name>"}}],
          "lines": [<line numbers of the SQL that decide this column's value>],
          "note": "<one short sentence, or an empty string>"
        }}
      }}
    }}
  }}
}}

The kinds:
{kind_help}

Rules:
- Include only tables the procedure writes to, and for each one list every one of its columns.
- "sources" are the input columns the value is taken or worked out from, traced back through any
  variables and temporary tables to the tables listed below. For a lookup, include both the
  column that is returned and the columns that are matched on.
- copied, lookup and calculated need at least one source. constant, generated and unchanged
  must have an empty "sources" list.
- A column the INSERT leaves out, which the database then fills by itself, is "generated".
- Use table and column names exactly as they are listed below, without square brackets.
- Line numbers refer to the numbered SQL below.
- Describe what the SQL does, even where it looks like a mistake. Do not describe what it should do.

Tables (name: column type, ...):
{tables}

Legacy SQL, with line numbers:
{sql}
"""


def table_columns(job):
    """{table: [column, ...]} from the dev snapshot's schemas. Reads no data."""
    before = Path("snapshots") / job / "before"
    return {f.stem: pq.read_schema(f).names for f in sorted(before.glob("*.parquet"))}


def build_prompt(job, sql_lines, problems=None):
    prompt = PROMPT.format(
        kinds=" | ".join(KINDS),
        kind_help="\n".join(f"- {kind}: {meaning}" for kind, (meaning, _) in KINDS.items()),
        tables=translate.describe_tables(job),
        sql="\n".join(f"{n:>4}  {line}" for n, line in enumerate(sql_lines, 1)),
    )
    if problems:
        prompt += (
            "\nYour previous answer had these problems. Fix them and reply with the whole corrected"
            " JSON:\n" + "\n".join(f"- {p}" for p in problems) + "\n"
        )
    return prompt


def extract_json(answer):
    """The contents of the one ```json block, parsed. Gives back (data, problem)."""
    if answer.count("```json") != 1:
        return None, f"expected exactly one ```json block, found {answer.count('```json')}"
    start = answer.find("```json") + len("```json")
    end = answer.find("```", start)
    if end == -1:
        return None, "the json block was never closed"
    try:
        return json.loads(answer[start:end]), None
    except json.JSONDecodeError as e:
        return None, f"the json block is not valid JSON: {e}"


def structure_problems(lineage, columns, sql_lines):
    """Everything wrong with the shape of the map. An empty list means it is well formed."""
    tables = lineage.get("tables") if isinstance(lineage, dict) else None
    if not isinstance(tables, dict) or not tables:
        return ['the top level must be {"tables": {...}} with at least one table']

    problems = []
    sql_lower = "\n".join(sql_lines).lower()
    for table, entry in tables.items():
        if table not in columns:
            problems.append(f"{table}: not one of the listed tables")
            continue
        cols = entry.get("columns") if isinstance(entry, dict) else None
        if not isinstance(cols, dict):
            problems.append(f'{table}: needs a "columns" object')
            continue
        if not entry.get("operations"):
            problems.append(f'{table}: "operations" is empty')
        missing = [c for c in columns[table] if c not in cols]
        unknown = [c for c in cols if c not in columns[table]]
        if missing:
            problems.append(f"{table}: columns not covered: {missing}")
        if unknown:
            problems.append(f"{table}: columns that are not in this table: {unknown}")

        for col, info in cols.items():
            if col in unknown:
                continue
            where = f"{table}.{col}"
            if not isinstance(info, dict):
                problems.append(f"{where}: must be an object")
                continue
            kind = info.get("kind")
            if kind not in KINDS:
                problems.append(f"{where}: kind {kind!r} is not one of {list(KINDS)}")
                continue
            sources = info.get("sources") or []
            needs_sources = KINDS[kind][1]
            if needs_sources and not sources:
                problems.append(f"{where}: kind {kind} needs at least one source")
            if not needs_sources and sources:
                problems.append(f"{where}: kind {kind} must have no sources")
            for src in sources:
                s_table = src.get("table") if isinstance(src, dict) else None
                s_col = src.get("column") if isinstance(src, dict) else None
                if s_table not in columns:
                    problems.append(f"{where}: source table {s_table!r} is not one of the listed tables")
                elif s_col not in columns[s_table]:
                    problems.append(f"{where}: source column {s_col!r} is not in {s_table}")
            lines = info.get("lines") or []
            bad_lines = [n for n in lines if not isinstance(n, int) or not 1 <= n <= len(sql_lines)]
            if bad_lines:
                problems.append(f"{where}: line numbers out of range: {bad_lines} (the SQL has {len(sql_lines)} lines)")
            if kind != "unchanged":
                if not lines:
                    problems.append(f"{where}: kind {kind} needs the line numbers that decide it")
                # A written column is normally named in the SQL. "generated" ones may not be:
                # the INSERT leaves them out so the database fills them.
                if kind != "generated" and col.lower() not in sql_lower:
                    problems.append(f"{where}: said to be written ({kind}) but the SQL never mentions this column")
    return problems


def cross_checks(job, lineage, spec):
    """Compare the map with evidence Claude never saw. Gives back (agreements, disagreements).

    Never fed back to Claude: it only tells a human where to look.
    """
    agree, disagree = [], []
    tables = lineage["tables"]

    # 1. The columns a human chose to ignore (never the same twice) should be "generated" here
    ignored = {(t, c) for t, cols in spec.get("ignore", {}).items() for c in cols}
    generated = {(t, c) for t, e in tables.items() for c, info in e["columns"].items()
                 if info.get("kind") == "generated"}
    for t, c in sorted(ignored):
        kind = tables.get(t, {}).get("columns", {}).get(c, {}).get("kind")
        if kind == "generated":
            agree.append(f"{t}.{c}: ignored in jobs/{job}.json, and the map says generated")
        elif kind is None:
            disagree.append(f"{t}.{c}: ignored in jobs/{job}.json, but the map says the procedure never writes {t}")
        else:
            disagree.append(f"{t}.{c}: ignored in jobs/{job}.json, but the map says {kind}")
    for t, c in sorted(generated - ignored):
        disagree.append(f"{t}.{c}: the map says generated, but jobs/{job}.json compares it and it reconciles."
                        " Either the map is wrong or the value is the same on every run")

    # 2. Tables the legacy job really changed (dev snapshot, before vs after) should all be in the map
    snap = Path("snapshots") / job
    for f in sorted((snap / "after").glob("*.parquet")):
        before = snap / "before" / f.name
        changed = not before.exists() or not pq.read_table(before).equals(pq.read_table(f))
        if changed and f.stem in tables:
            agree.append(f"{f.stem}: changed by the legacy job, and in the map")
        elif changed:
            disagree.append(f"{f.stem}: changed by the legacy job, but missing from the map")
        elif f.stem in tables:
            # Not an error: the SQL can write a table without changing it on this particular input
            agree.append(f"{f.stem}: in the map, though this batch's data did not change it")
    return agree, disagree


def to_markdown(job, record):
    checks = record["checks"]
    out = [
        f"# Column-level lineage: {job}",
        "",
        f"Source: `{record['legacy_sql']}`.",
        f"Drafted by {record['model']} on {record['generated_at']}, from the SQL and the table columns only.",
        "AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.",
        "",
        "## Checks",
        "",
        f"- Structure: {'passed' if not checks['structure_problems'] else 'FAILED'}"
        f" ({record['columns_mapped']} columns in {len(record['tables'])} tables).",
    ]
    out += [f"  - {p}" for p in checks["structure_problems"]]
    out.append(f"- Agrees with independent evidence: {len(checks['agreements'])} point(s).")
    out += [f"  - {a}" for a in checks["agreements"]]
    out.append(f"- Disagrees with independent evidence: {len(checks['disagreements'])} point(s), for a human to resolve.")
    out += [f"  - {d}" for d in checks["disagreements"]]
    out += ["", "## Kinds", ""]
    out += [f"- **{kind}**: {meaning}." for kind, (meaning, _) in KINDS.items()]

    for table, entry in record["tables"].items():
        out += ["", f"## {table}", "", f"Operations: {', '.join(entry.get('operations', []))}.", "",
                "| Column | Kind | Comes from | SQL lines | Note |", "|---|---|---|---|---|"]
        for col, info in entry["columns"].items():
            sources = "<br>".join(f"{s.get('table')}.{s.get('column')}" for s in info.get("sources") or [])
            lines = ", ".join(str(n) for n in info.get("lines") or [])
            note = (info.get("note") or "").replace("|", "\\|").replace("\n", " ")
            out.append(f"| {col} | {info.get('kind')} | {sources} | {lines} | {note} |")
    return "\n".join(out) + "\n"


def save(job, record):
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"{job}.json").write_text(json.dumps(record, indent=2) + "\n")
    (OUT_DIR / f"{job}.md").write_text(to_markdown(job, record))


def finish(job, record, spec, columns, sql_lines):
    """Run every check on the map, save both files, print the result. True if the structure is sound."""
    problems = structure_problems(record, columns, sql_lines)
    agree, disagree = ([], []) if problems else cross_checks(job, record, spec)
    record["columns_mapped"] = sum(len(e.get("columns", {})) for e in record["tables"].values()
                                    if isinstance(e, dict))
    record["checks"] = {"structure_problems": problems, "agreements": agree, "disagreements": disagree}
    save(job, record)

    print(f"\n{job}: {record['columns_mapped']} columns in {len(record['tables'])} tables")
    print(f"   structure: {'ok' if not problems else 'FAILED'}")
    for p in problems:
        print(f"      - {p}")
    print(f"   agrees with independent evidence: {len(agree)}")
    print(f"   disagrees, for a human to resolve: {len(disagree)}")
    for d in disagree:
        print(f"      - {d}")
    print(f"   saved to {OUT_DIR / f'{job}.md'} and {OUT_DIR / f'{job}.json'}")
    return not problems


def main():
    parser = argparse.ArgumentParser(description="Column-level lineage for a legacy job.")
    parser.add_argument("job", help="job name, e.g. sale (needs jobs/<job>.json and snapshots/<job>/)")
    parser.add_argument("--model", default=translate.DEFAULT_MODEL, choices=sorted(translate.PRICES))
    parser.add_argument("--check", action="store_true",
                        help="rerun the checks on the existing lineage/<job>.json instead of asking Claude")
    args = parser.parse_args()
    job = args.job
    # Keep progress lines in order with translate.py's stderr cost line, also when piped to a log
    sys.stdout.reconfigure(line_buffering=True)

    spec_path = Path("jobs") / f"{job}.json"
    if not spec_path.exists():
        sys.exit(f"No job spec at {spec_path}")
    spec = json.loads(spec_path.read_text())
    columns = table_columns(job)
    if not columns:
        sys.exit(f"No snapshots in snapshots/{job}/before/. Run: python migrator/run_legacy.py {job}")
    sql_lines = Path(spec["legacy_sql"]).read_text(encoding="utf-8-sig").splitlines()

    if args.check:
        path = OUT_DIR / f"{job}.json"
        if not path.exists():
            sys.exit(f"No {path} to check. Run without --check first.")
        sys.exit(0 if finish(job, json.loads(path.read_text()), spec, columns, sql_lines) else 1)

    problems = None
    for attempt in range(1, ATTEMPTS + 1):
        print(f"{attempt}. Asking {args.model} for the lineage of {spec['legacy_sql']}"
              + (" again, with the problems found" if problems else ""))
        try:
            answer = translate.ask_claude(build_prompt(job, sql_lines, problems), args.model)
        except translate.TranslationError as e:
            sys.exit(f"Lineage failed: {e}")
        lineage, problem = extract_json(answer)
        problems = [problem] if problem else structure_problems(lineage, columns, sql_lines)
        if not problems:
            break
        print(f"   structure checks found {len(problems)} problem(s):")
        for p in problems:
            print(f"      - {p}")
    if lineage is None:
        sys.exit(f"Lineage failed: {problems[0]}")

    record = {
        "job": job,
        "legacy_sql": spec["legacy_sql"],
        "model": args.model,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tables": lineage.get("tables", {}) if isinstance(lineage, dict) else {},
    }
    sys.exit(0 if finish(job, record, spec, columns, sql_lines) else 1)


if __name__ == "__main__":
    main()
