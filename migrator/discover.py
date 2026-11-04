"""
discover.py: ask SQL Server what a procedure touches, instead of listing it by hand.

SQL Server keeps track of what every procedure refers to. sys.dm_sql_referenced_entities
returns one row per table, view or procedure that a procedure mentions, and says whether the
procedure writes to it (is_updated). If the procedure calls another procedure, we follow that
one too, so the list covers everything that can change when the job runs.

This is what makes the tool usable on a database we have never seen (say, an online bookstore):
point it at a procedure name and it finds the tables, their keys and their identity columns.

Limits: dynamic SQL (EXEC('...') built from strings) is invisible to this metadata, and tables in
other databases are reported but not snapshotted. A spec can always list "tables" by hand.

Try it:  python migrator/discover.py sale
"""
import re
import sys


def display_name(schema, name):
    """Integration.[ETL Cutoff] style: brackets only where the name needs them."""
    def part(p):
        return p if re.fullmatch(r"\w+", p) else f"[{p}]"
    return f"{part(schema)}.{part(name)}"


def file_name(table):
    """Integration.[ETL Cutoff] -> Integration.ETL Cutoff (the snapshot file name)."""
    return table.replace("[", "").replace("]", "")


def tables(cur, proc, seen=None):
    """Every user table proc (or anything it calls) refers to.
    Returns [{"table", "written", "read", "via"}], written tables first."""
    seen = set() if seen is None else seen
    seen.add(proc.lower())
    cur.execute(
        "SELECT r.referenced_schema_name, r.referenced_entity_name, r.referenced_database_name, "
        "       MAX(CAST(r.is_updated AS int)), MAX(CAST(r.is_selected AS int)), o.type "
        "FROM sys.dm_sql_referenced_entities(?, 'OBJECT') AS r "
        "LEFT JOIN sys.objects AS o ON o.object_id = r.referenced_id "
        "WHERE r.referenced_minor_id = 0 "
        "GROUP BY r.referenced_schema_name, r.referenced_entity_name, r.referenced_database_name, o.type",
        proc,
    )
    rows = cur.fetchall()
    found = {}
    for schema, name, database, updated, selected, obj_type in rows:
        if database:
            print(f"   note: {proc} refers to {database}.{schema}.{name} in another database; not snapshotted")
            continue
        full = display_name(schema or "dbo", name)
        obj_type = (obj_type or "").strip()
        if obj_type == "U":  # user table
            found[full] = {"table": full, "written": bool(updated), "read": bool(selected), "via": proc}
        elif obj_type in ("P", "V", "FN", "IF", "TF") and full.lower() not in seen:
            # a procedure, view or function: follow it and collect its tables too
            for t in tables(cur, full, seen):
                if t["table"] in found:
                    found[t["table"]]["written"] |= t["written"]
                    found[t["table"]]["read"] |= t["read"]
                else:
                    found[t["table"]] = t
    return sorted(found.values(), key=lambda t: (not t["written"], t["table"]))


def primary_key(cur, table):
    """Primary key columns, else the first unique index, else []."""
    cur.execute(
        "SELECT c.name FROM sys.indexes AS i "
        "JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id "
        "JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id "
        "WHERE i.object_id = OBJECT_ID(?) AND ic.is_included_column = 0 "
        "  AND i.index_id = (SELECT TOP(1) index_id FROM sys.indexes "
        "                    WHERE object_id = OBJECT_ID(?) AND (is_primary_key = 1 OR is_unique = 1) "
        "                    ORDER BY is_primary_key DESC, index_id) "
        "ORDER BY ic.key_ordinal",
        table, table,
    )
    return [r[0] for r in cur.fetchall()]


def identity_columns(cur, table):
    cur.execute("SELECT name FROM sys.identity_columns WHERE object_id = OBJECT_ID(?)", table)
    return [r[0] for r in cur.fetchall()]


def main():
    sys.path.insert(0, "migrator")
    import jobspec
    from run_legacy import connect

    spec = jobspec.load(sys.argv[1] if len(sys.argv) > 1 else "sale")
    cur = connect(spec["database"])
    print(f"{spec['proc']}\n")
    print(f"   {'table':28} {'writes':7} {'key columns':32} identity")
    for t in tables(cur, spec["proc"]):
        key = ", ".join(primary_key(cur, t["table"]))
        ident = ", ".join(identity_columns(cur, t["table"]))
        print(f"   {t['table']:28} {'yes' if t['written'] else '':7} {key:32} {ident}")


if __name__ == "__main__":
    main()
