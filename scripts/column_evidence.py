"""
column_evidence.py: the facts a human needs to choose a job's key and ignored columns.

It decides nothing. jobs/<job>.json's "keys" and "ignore" stay a human's choice; this only
prints the evidence for that choice, from the legacy SQL, the database and the job's snapshot:

    clock columns     set from the clock in the legacy SQL (SYSDATETIME() and friends), with line numbers
    counter columns   filled by the database itself (an IDENTITY or a sequence default) and never
                      written by the legacy SQL
    unique columns    per table in the legacy output: candidates for a key (some are unique by chance)
    changed tables    which tables the legacy job actually changed

The rule for ignoring a column: only a clock or a counter, i.e. a value that would differ if the
same legacy job ran twice on the same input. Anything copied or calculated from the input is data.

Usage (from the repo root, after run_legacy.py has made snapshots/<job>/):
    python scripts/column_evidence.py movement
"""
import json
import re
import sys
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrator"))
import run_legacy  # noqa: E402

CLOCK = re.compile(r"\[([^\]]+)\]\s*=\s*(SYSDATETIME|SYSUTCDATETIME|GETDATE|GETUTCDATE|CURRENT_TIMESTAMP)\b", re.I)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    job = sys.argv[1]
    spec = json.loads((Path("jobs") / f"{job}.json").read_text())
    sql_lines = Path(spec["legacy_sql"]).read_text(encoding="utf-8-sig").splitlines()
    sql_text = "\n".join(sql_lines)
    snap = Path("snapshots") / job

    print(f"== Evidence for jobs/{job}.json (legacy SQL: {spec['legacy_sql']})")
    print("\nClock columns, set from the clock in the legacy SQL:")
    clocks = [(n, m.group(1), m.group(2)) for n, line in enumerate(sql_lines, 1) for m in CLOCK.finditer(line)]
    for n, col, fn in clocks:
        print(f"   line {n}: [{col}] = {fn.upper()}()")
    if not clocks:
        print("   none")

    # Tables the legacy SQL inserts new rows into (INSERT, or MERGE ... WHEN NOT MATCHED THEN INSERT).
    # A counter only causes a mismatch there: rows that already existed keep their value and are copied.
    plain = lambda name: name.replace("[", "").replace("]", "").strip()
    inserted = {plain(m) for m in re.findall(r"\bINSERT\s+(?:INTO\s+)?((?:\[[^\]]+\]|\w+)\.(?:\[[^\]]+\]|\w+))", sql_text, re.I)}
    inserted |= {plain(m) for m in re.findall(r"\bMERGE\s+(?:INTO\s+)?((?:\[[^\]]+\]|\w+)\.(?:\[[^\]]+\]|\w+))", sql_text, re.I)
                 if re.search(r"WHEN\s+NOT\s+MATCHED[^;]*?\bINSERT\b", sql_text, re.I | re.S)}

    cur = run_legacy.connect(spec["database"])
    print("\nCounter columns, filled by the database and never written by the legacy SQL:")
    print("   (they only matter in tables the job inserts new rows into)")
    found = False
    for table in spec["tables"]:
        cur.execute(
            "SELECT c.name, CASE WHEN c.is_identity = 1 THEN 'IDENTITY' ELSE dc.definition END "
            "FROM sys.columns AS c LEFT JOIN sys.default_constraints AS dc "
            "ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id "
            "WHERE c.object_id = OBJECT_ID(?) AND (c.is_identity = 1 OR dc.definition LIKE '%NEXT VALUE FOR%')",
            table,
        )
        for col, how in cur.fetchall():
            if f"[{col}]" in sql_text or re.search(rf"\b{re.escape(col)}\b", sql_text):
                continue  # the legacy SQL writes or reads it by name: not left to the database
            found = True
            where = "the job inserts new rows here" if plain(table) in inserted else "the job inserts no rows here, so existing values are copied"
            print(f"   {plain(table)}.[{col}]: {how}   ({where})")
    if not found:
        print("   none")

    print("\nTables, legacy output (after/) vs input (before/):")
    for f in sorted((snap / "after").glob("*.parquet")):
        after = pq.read_table(f)
        changed = not after.equals(pq.read_table(snap / "before" / f.name))
        unique = [c for c in after.column_names if after.num_rows and len(set(after.column(c).to_pylist())) == after.num_rows]
        print(f"   {f.stem:32} {'changed' if changed else 'unchanged':9} {after.num_rows:7} rows   unique: {unique or 'none'}")


if __name__ == "__main__":
    main()
