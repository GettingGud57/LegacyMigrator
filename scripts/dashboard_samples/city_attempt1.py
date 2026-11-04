from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    lineage = tables["Integration.Lineage"]
    cutoff = tables["Integration.ETL Cutoff"]
    city = tables["Dimension.City"]
    staging = tables["Integration.City_Staging"]

    lk = (lineage
          .filter((F.col("Table Name") == "City") & F.col("Data Load Completed").isNull())
          .orderBy(F.col("Lineage Key").desc())
          .select("Lineage Key").limit(1).collect())
    lineage_key = lk[0]["Lineage Key"] if lk else None

    # Close off the cities that have new versions in staging
    close_at = staging.groupBy("WWI City ID").agg(F.min("Valid From").alias("__close_at"))
    joined = city.join(close_at, "WWI City ID", "left")
    new_valid_to = F.coalesce(F.col("__close_at"), F.col("Valid To"))
    closed = joined.select(*[
        new_valid_to.alias(c) if c == "Valid To" else F.col(c) for c in city.columns
    ])

    # Insert the staged versions with new identity keys
    max_key = city.agg(F.max("City Key")).collect()[0][0] or 0
    w = Window.orderBy("City Staging Key")
    inserted = staging.withColumn("__rn", F.row_number().over(w)).select(*[
        (F.lit(max_key) + F.col("__rn")).cast("int").alias(c) if c == "City Key"
        else F.lit(lineage_key).cast("int").alias(c) if c == "Lineage Key"
        else F.col(c)
        for c in city.columns
    ])
    new_city = closed.unionByName(inserted)

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
        F.when(F.col("Table Name") == "City", F.lit(cutoff_time)).otherwise(F.col("Cutoff Time")),
    )

    return {
        "Dimension.City": new_city,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
