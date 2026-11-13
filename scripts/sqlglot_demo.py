"""A standard SQL translator fails silently on one statement from Microsoft's Sale procedure.
"""
import sys
import sqlglot
sys.path.insert(0, "migrator")
from run_spark import start_spark
# From legacy_jobs/wwi/MigrateStagedSaleData.sql, line 54
tsql = """
DELETE s
FROM Fact.Sale AS s
WHERE s.[WWI Invoice ID] IN (SELECT [WWI Invoice ID] FROM Integration.Sale_Staging)
"""
# sqlglot converts T-SQL to Spark SQL. "raise" = stop on anything it cant convert.
spark_sql = sqlglot.transpile(tsql, read="tsql", write="spark", unsupported_level="raise")[0]
print("sqlglot says this is Spark SQL:\n")
print(spark_sql)

# Give sqlglots output to real Spark.
print("\nSpark says:\n")
spark = start_spark()
spark.sql(spark_sql)
