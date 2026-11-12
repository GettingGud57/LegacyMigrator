"""
make_wwi_jobs.py: set up the remaining WideWorldImporters jobs from the live databases.

For each job in WWI_JOBS below it writes:
    legacy_jobs/wwi/MigrateStaged<Entity>Data.sql   the legacy procedure, exported from WideWorldImportersDW
                                                    (skipped if the file already exists)
    scripts/load_<job>_staging.sql                  loads one batch into Integration.<Entity>_Staging,
                                                    the way Microsoft's SSIS package would (always rewritten)
    jobs/<job>.json                                 how to run the job and its batches, with empty "keys"
                                                    and "ignore" for a human to fill in
                                                    (skipped if the file already exists, so it never
                                                    overwrites columns a human chose)

The staging script's column lists come from the database itself: the shop procedure's real
output columns, and the staging table's declared types. Edit WWI_JOBS and rerun this script
rather than editing a generated staging script by hand.

Usage (from the repo root, SQL Server running):
    python scripts/make_wwi_jobs.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "migrator"))
import run_legacy  # noqa: E402  (the same connection settings as every other script)

DW, SHOP = "WideWorldImportersDW", "WideWorldImporters"

# One entry per job. Months are counted back from the warehouse's last load (2016-06-06),
# the same way load_sale_staging.sql and load_city_staging.sql count them.
#   dev:      the staging script's default window (MonthsBack)
#   holdout:  the holdout batch's staging_vars
#   rename:   shop column -> staging column, where Microsoft's names differ
#   split_id: a column to split by ID (even = dev, odd = holdout), for jobs with a single batch of data
WWI_JOBS = {
    "movement":         {"entity": "Movement",        "table": "Movement",         "dev": 0,  "holdout": {"MonthsBack": 1},
                         "rename": {"Transaction Occurred When": "Last Modifed When"}},
    "order":            {"entity": "Order",           "table": "Order",            "dev": 0,  "holdout": {"MonthsBack": 1}},
    "purchase":         {"entity": "Purchase",        "table": "Purchase",         "dev": 0,  "holdout": {"MonthsBack": 1}},
    "transaction":      {"entity": "Transaction",     "table": "Transaction",      "dev": 0,  "holdout": {"MonthsBack": 1}},
    "employee":         {"entity": "Employee",        "table": "Employee",         "dev": 0,  "holdout": {"MonthsBack": 2}},
    "stock_item":       {"entity": "StockItem",       "table": "Stock Item",       "dev": 0,  "holdout": {"MonthsBack": 41}},
    "supplier":         {"entity": "Supplier",        "table": "Supplier",         "dev": 41, "holdout": {"MonthsBack": 17}},
    "transaction_type": {"entity": "TransactionType", "table": "Transaction Type", "dev": 41, "holdout": {"MonthsBack": 5}},
    "payment_method":   {"entity": "PaymentMethod",   "table": "Payment Method",   "dev": 41, "holdout": {"MonthsBack": 5}},
    "customer":         {"entity": "Customer",        "table": "Customer",         "dev": 41, "holdout": {"IdRemainder": 1},
                         "split_id": "WWI Customer ID"},
    "stock_holding":    {"entity": "StockHolding",    "table": "Stock Holding",    "dev": None, "holdout": {"IdRemainder": 1},
                         "split_id": "WWI Stock Item ID"},
}


def sql_type(type_name, max_length, precision, scale):
    """A column's declared type as T-SQL, e.g. nvarchar(50), decimal(18,2), datetime2(7)."""
    if type_name in ("nvarchar", "nchar"):
        return f"{type_name}({'max' if max_length == -1 else max_length // 2})"
    if type_name in ("varchar", "char", "varbinary", "binary"):
        return f"{type_name}({'max' if max_length == -1 else max_length})"
    if type_name in ("decimal", "numeric"):
        return f"{type_name}({precision},{scale})"
    if type_name in ("datetime2", "time", "datetimeoffset"):
        return f"{type_name}({scale})"
    return type_name


def bracket(name):
    """Schema.Table as SQL: Fact.[Order], Dimension.[Stock Item]."""
    schema, table = name.split(".", 1)
    return f"{schema}.[{table}]"


def staging_columns(dw, entity):
    dw.execute(
        "SELECT c.name, t.name, c.max_length, c.precision, c.scale FROM sys.columns AS c "
        "JOIN sys.types AS t ON c.user_type_id = t.user_type_id "
        "WHERE c.object_id = OBJECT_ID(?) AND c.is_identity = 0 ORDER BY c.column_id",
        f"Integration.{entity}_Staging",
    )
    return {name: sql_type(t, ml, p, s) for name, t, ml, p, s in dw.fetchall()}


def getter_has_params(shop, entity):
    shop.execute("SELECT COUNT(*) FROM sys.parameters WHERE object_id = OBJECT_ID(?)", f"Integration.Get{entity}Updates")
    return shop.fetchone()[0] > 0


def getter_columns(shop, entity, has_params):
    """The shop procedure's real output columns, read from a run on a one-second window."""
    args = " @LastCutoff = '2016-05-31', @NewCutoff = '2016-05-31 00:00:01'" if has_params else ""
    shop.execute(f"SET NOCOUNT ON; EXEC Integration.Get{entity}Updates{args}")
    while shop.description is None and shop.nextset():
        pass
    names = [d[0] for d in shop.description]
    shop.fetchall()
    while shop.nextset():
        pass
    return names


def proc_tables(dw, proc):
    dw.execute(
        "SELECT DISTINCT referenced_schema_name, referenced_entity_name "
        "FROM sys.dm_sql_referenced_entities(?, 'OBJECT') WHERE referenced_minor_id = 0",
        proc,
    )
    names = sorted(f"{s}.{t}" for s, t in dw.fetchall())
    # staging first, then the bookkeeping tables, then what the job loads
    return sorted(names, key=lambda n: (not n.endswith("_Staging"), not n.startswith("Integration."), n))


def staging_script(job, cfg, getter_cols, stg_types, has_params):
    entity, table = cfg["entity"], cfg["table"]
    rename = cfg.get("rename", {})
    target = [rename.get(c, c) for c in getter_cols]
    missing = [c for c in target if c not in stg_types]
    if missing:
        raise SystemExit(f"{job}: shop columns with no staging column: {missing}. Add them to 'rename'.")
    split = cfg.get("split_id")
    col_list = ", ".join(f"[{c}]" for c in target)

    lines = [
        f"-- load_{job}_staging.sql",
        f"-- Generated by scripts/make_wwi_jobs.py: edit WWI_JOBS there and rerun it, rather than editing this file.",
        f"-- Fills WideWorldImportersDW.Integration.{entity}_Staging the way Microsoft's SSIS package would,",
        f"-- so Integration.MigrateStaged{entity}Data has input to work on.",
        "-- Run against WideWorldImportersDW. Needs the WideWorldImporters (shop) database on the same server.",
        "",
        "SET NOCOUNT ON;",
        "",
    ]
    if has_params:
        lines += [
            "-- 1. Pick a time window: @WindowMonths long, ending @MonthsBack months before the warehouse's last load.",
            f"--    The default is the dev batch; jobs/{job}.json changes it for the holdout.",
            f"DECLARE @MonthsBack   int = {cfg['dev']};",
            "DECLARE @WindowMonths int = 1;",
        ]
    else:
        lines += [f"-- 1. Get{entity}Updates takes no time window: it returns every current row."]
    if split:
        lines += [
            f"--    Only one batch of data exists, so dev and holdout are split by [{split}]:",
            "--    even IDs are the dev batch (the default), odd IDs the holdout.",
            "DECLARE @IdRemainder  int = 0;",
        ]
    lines += [
        f"DECLARE @LastLoad   datetime2(7) = (SELECT [Cutoff Time] FROM Integration.[ETL Cutoff] WHERE [Table Name] = N'{table}');",
    ]
    if has_params:
        lines += [
            "DECLARE @NewCutoff  datetime2(7) = DATEADD(month, -@MonthsBack, @LastLoad);",
            "DECLARE @LastCutoff datetime2(7) = DATEADD(month, -@WindowMonths, @NewCutoff);",
        ]
    else:
        lines += ["DECLARE @NewCutoff  datetime2(7) = @LastLoad;"]
    lines += [
        "",
        "-- 2. Clear staging (in-memory tables don't allow TRUNCATE)",
        f"DELETE FROM Integration.{entity}_Staging;",
        "",
        "-- 3. Pull the rows from the shop database. In-memory tables can't be written in the same",
        "--    statement as another user database, so go through a temp table.",
        "CREATE TABLE #rows (",
        ",\n".join(f"    [{c}] {stg_types[rename.get(c, c)]}" for c in getter_cols),
        ");",
        "",
        "INSERT INTO #rows",
        f"EXEC WideWorldImporters.Integration.Get{entity}Updates"
        + (" @LastCutoff = @LastCutoff, @NewCutoff = @NewCutoff;" if has_params else ";"),
        "",
    ]
    if rename:
        lines += ["-- Microsoft's staging table names these columns differently: "
                  + "; ".join(f"[{a}] -> [{b}]" for a, b in rename.items())]
    lines += [
        f"INSERT INTO Integration.{entity}_Staging ({col_list})",
        f"SELECT {', '.join(f'[{c}]' for c in getter_cols)}",
        "FROM #rows" + (f"\nWHERE [{split}] % 2 = @IdRemainder" if split else "") + ";",
        "",
        "DROP TABLE #rows;",
        "",
        f"-- 4. Open a lineage record. MigrateStaged{entity}Data looks for one with no completion time.",
        f"EXEC Integration.GetLineageKey @TableName = N'{table}', @NewCutoffTime = @NewCutoff;",
        "",
        "-- 5. Report what got staged",
        "SELECT COUNT(*) AS staged_rows,"
        + (" @LastCutoff AS window_from," if has_params else "")
        + " @NewCutoff AS window_to",
        f"FROM Integration.{entity}_Staging;",
        "",
    ]
    return "\n".join(lines)


def main():
    root = Path(__file__).resolve().parent.parent
    dw, shop = run_legacy.connect(DW), run_legacy.connect(SHOP)
    for job, cfg in WWI_JOBS.items():
        entity = cfg["entity"]
        proc = f"Integration.MigrateStaged{entity}Data"

        sql_path = root / "legacy_jobs" / "wwi" / f"MigrateStaged{entity}Data.sql"
        if not sql_path.exists():
            dw.execute("SELECT definition FROM sys.sql_modules WHERE object_id = OBJECT_ID(?)", proc)
            sql_path.write_text(dw.fetchone()[0].strip() + "\n", encoding="utf-8")

        has_params = getter_has_params(shop, entity)
        script = staging_script(job, cfg, getter_columns(shop, entity, has_params), staging_columns(dw, entity), has_params)
        script_path = root / "scripts" / f"load_{job}_staging.sql"
        script_path.write_text(script, encoding="utf-8")

        json_path = root / "jobs" / f"{job}.json"
        if not json_path.exists():
            holdout = dict(cfg["holdout"])
            note = (f"months back {holdout['MonthsBack']}" if "MonthsBack" in holdout
                    else f"odd [{cfg['split_id']}] values")
            spec = {
                "legacy_sql": f"legacy_jobs/wwi/MigrateStaged{entity}Data.sql",
                "database": DW,
                "proc": proc,
                "staging_script": f"scripts/load_{job}_staging.sql",
                "tables": [bracket(t) for t in proc_tables(dw, proc)],
                "batches": {"holdout": {"note": note, "staging_vars": holdout}},
                "keys": {},
                "ignore": {},
            }
            json_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        print(f"{job:17} procedure: {sql_path.relative_to(root)}  staging: {script_path.relative_to(root)}  spec: {json_path.relative_to(root)}")


if __name__ == "__main__":
    main()
