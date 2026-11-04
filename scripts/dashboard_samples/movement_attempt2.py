from pyspark.sql import functions as F
from pyspark.sql import Window

TXN = "WWI Stock Item Transaction ID"


def lookup(staging, dim, dim_id, dim_key, stg_id, target):
    """COALESCE((SELECT TOP(1) key ... valid on [Last Modifed When] ORDER BY [Valid From]), 0)"""
    d = dim.select(F.col(dim_id).alias("__id"), F.col(dim_key).alias("__key"),
                   F.col("Valid From").alias("__from"), F.col("Valid To").alias("__to"))
    cond = ((F.col("__id") == F.col(stg_id))
            & (F.col("Last Modifed When") > F.col("__from"))
            & (F.col("Last Modifed When") <= F.col("__to")))
    w = Window.partitionBy("__rid").orderBy(F.col("__from").asc())
    return (staging.join(d, cond, "left")
            .withColumn("__rn", F.row_number().over(w)).filter("__rn = 1")
            .withColumn(target, F.coalesce(F.col("__key"), F.lit(0)).cast("int"))
            .drop("__id", "__key", "__from", "__to", "__rn"))


def run(spark, tables):
    lineage = tables["Integration.Lineage"]
    cutoff = tables["Integration.ETL Cutoff"]
    staging = tables["Integration.Movement_Staging"]
    fact = tables["Fact.Movement"]

    lk = (lineage
          .filter((F.col("Table Name") == "Movement") & F.col("Data Load Completed").isNull())
          .orderBy(F.col("Lineage Key").desc()).select("Lineage Key").limit(1).collect())
    lineage_key = lk[0]["Lineage Key"] if lk else None

    # UPDATE staging: dimension key lookups
    s = staging.withColumn("__rid", F.monotonically_increasing_id())
    s = lookup(s, tables["Dimension.Stock Item"], "WWI Stock Item ID", "Stock Item Key", "WWI Stock Item ID", "Stock Item Key")
    s = lookup(s, tables["Dimension.Customer"], "WWI Customer ID", "Customer Key", "WWI Customer ID", "Customer Key")
    s = lookup(s, tables["Dimension.Supplier"], "WWI Supplier ID", "Supplier Key", "WWI Supplier ID", "Supplier Key")
    s = lookup(s, tables["Dimension.Transaction Type"], "WWI Transaction Type ID", "Transaction Type Key",
               "WWI Transaction Type ID", "Transaction Type Key")
    new_staging = s.select(*staging.columns).localCheckpoint()

    # MERGE: matched rows take the staged values, unmatched staged rows are inserted
    updated_cols = ["Date Key", "Stock Item Key", "Customer Key", "Supplier Key",
                    "Transaction Type Key", "WWI Invoice ID", "WWI Purchase Order ID", "Quantity"]
    ms = new_staging.select(F.col(TXN).alias("__txn"), *[F.col(c).alias("__ms_" + c) for c in updated_cols])
    joined = fact.join(ms, fact[TXN] == ms["__txn"], "left")
    matched = F.col("__txn").isNotNull()
    merged = joined.select(*[
        F.when(matched, F.col("__ms_" + c)).otherwise(F.col(c)).alias(c) if c in updated_cols
        else F.col(c)
        for c in fact.columns
    ])

    max_key = fact.agg(F.max("Movement Key")).collect()[0][0] or 0
    new_rows = new_staging.join(fact.select(TXN), TXN, "left_anti")
    w = Window.orderBy("Movement Staging Key")
    inserted = new_rows.withColumn("__rn", F.row_number().over(w)).select(*[
        (F.lit(max_key) + F.col("__rn")).cast("long").alias(c) if c == "Movement Key"
        else F.lit(lineage_key).cast("int").alias(c) if c == "Lineage Key"
        else F.col(c)
        for c in fact.columns
    ])
    new_fact = merged.unionByName(inserted)

    is_target = F.coalesce(F.col("Lineage Key") == F.lit(lineage_key), F.lit(False))
    new_lineage = lineage.select(*[
        F.when(is_target, F.current_timestamp()).otherwise(F.col(c)).alias(c) if c == "Data Load Completed"
        else F.when(is_target, F.lit(True)).otherwise(F.col(c)).alias(c) if c == "Was Successful"
        else F.col(c)
        for c in lineage.columns
    ])
    cutoff_time = (lineage.filter(F.col("Lineage Key") == F.lit(lineage_key))
                   .select("Source System Cutoff Time").collect())
    cutoff_time = cutoff_time[0][0] if cutoff_time else None
    new_cutoff = cutoff.withColumn(
        "Cutoff Time",
        F.when(F.col("Table Name") == "Movement", F.lit(cutoff_time)).otherwise(F.col("Cutoff Time")),
    )

    return {
        "Integration.Movement_Staging": new_staging,
        "Fact.Movement": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
