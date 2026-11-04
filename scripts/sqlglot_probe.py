"""
sqlglot_probe.py: why a plain SQL transpiler isn't enough.

For each legacy procedure, strip the CREATE PROCEDURE ... BEGIN/END wrapper, transpile every
statement from T-SQL to Spark SQL with sqlglot (strict errors on), then hand the result to
Spark's own SQL parser. sqlglot reports success for statements Spark still can't run.

Writes dashboard/public/data/sqlglot_probe.json, which the dashboard's "How it works" page shows.

Needs: pip install sqlglot pyspark   (and Java, which Spark needs anyway)
Usage (from the repo root):
    python scripts/sqlglot_probe.py
"""
import json
import re
import sys
from pathlib import Path

import sqlglot
from sqlglot.errors import ErrorLevel

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "public" / "data" / "sqlglot_probe.json"


def statements(sql_text):
    """The statements inside the procedure body, without the wrapper and transaction control."""
    body = sql_text.split("AS\nBEGIN", 1)[1]
    body = body[: body.rstrip().rfind("END")]
    # Transaction control and RETURN aren't data work, and sqlglot can't parse RETURN 0 here
    body = re.sub(r"^\s*(RETURN \d+|COMMIT|BEGIN TRAN|SET (NOCOUNT|XACT_ABORT) ON);\s*$", "", body, flags=re.M)
    parsed = sqlglot.parse(body, read="tsql", error_level=ErrorLevel.RAISE)
    return [p for p in parsed if p is not None]


def spark_parse_error(spark, sql):
    """None if Spark's parser accepts the statement, else the first line of its error."""
    # sqlglot turns T-SQL variables like @LineageKey into ${LineageKey}, which Spark only fills
    # in with variable substitution. To be fair to sqlglot, make that part valid Spark first:
    # a bare name where the variable is declared, a plain number where it's used.
    if sql.lstrip().upper().startswith("DECLARE"):
        sql = re.sub(r"\$\{(\w+)\}", r"\1", sql)
    else:
        sql = re.sub(r"\$\{\w+\}", "14", sql)
    try:
        spark._jsparkSession.sessionState().sqlParser().parsePlan(sql)
        return None
    except Exception as e:  # Py4J wraps Spark's ParseException
        text = str(e)
        m = re.search(r"\[(\w+(?:\.\w+)?)\][^\n]*", text)
        return m.group(0) if m else text.strip().splitlines()[0]


def main():
    from pyspark.sql import SparkSession

    spark = (SparkSession.builder.master("local[1]").appName("sqlglot_probe")
             .config("spark.ui.enabled", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    results = []
    for path in sorted((ROOT / "legacy_jobs" / "wwi").glob("*.sql")):
        for stmt in statements(path.read_text(encoding="utf-8-sig")):
            kind = stmt.key.upper()
            if kind in ("SET", "TRANSACTION", "COMMIT", "RETURN"):
                continue
            tsql = stmt.sql(dialect="tsql", pretty=True)
            try:
                spark_sql = sqlglot.transpile(tsql, read="tsql", write="spark",
                                              unsupported_level=ErrorLevel.RAISE, pretty=True)[0]
                transpile_error = None
            except Exception as e:
                spark_sql, transpile_error = None, str(e).splitlines()[0]
            results.append({
                "file": path.relative_to(ROOT).as_posix(),
                "kind": kind,
                "tsql": tsql,
                "transpiled": spark_sql,
                "sqlglot_error": transpile_error,
                "spark_error": spark_parse_error(spark, spark_sql) if spark_sql else None,
            })
    spark.stop()

    ok = [r for r in results if r["sqlglot_error"] is None]
    rejected = [r for r in ok if r["spark_error"]]
    summary = {
        "sqlglot_version": sqlglot.__version__,
        "statements": len(results),
        "sqlglot_succeeded": len(ok),
        "spark_parse_rejected": len(rejected),
        "note": "Only the 3 procedures in legacy_jobs/wwi/. The DEVLOG probe ran the same idea on all 13 "
                "Microsoft procedures (141/141 statements transpiled).",
    }
    OUT.write_text(json.dumps({"summary": summary, "statements": results}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    for r in rejected:
        print(f"\n{r['file']} {r['kind']}: Spark says {r['spark_error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
