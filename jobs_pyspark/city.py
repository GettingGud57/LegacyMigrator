from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.City"]
    stg = tables["Integration.City_Staging"]
    cutoff = tables["Integration.ETL Cutoff"]
    lin = tables["Integration.Lineage"]

    ts_type = dim.schema["Valid To"].dataType
    eot = F.lit("9999-12-31 23:59:59.999999").cast(ts_type)

    # Lineage key: the open 'City' lineage row with the highest key (one row, may be NULL)
    lk = (lin.filter((F.col("Table Name") == "City") & F.col("Data Load Completed").isNull())
          .agg(F.max("Lineage Key").alias("_lk")))

    # Close off current dimension rows
    rtco = (stg.groupBy("WWI City ID")
            .agg(F.min("Valid From").alias("_rt_vf"))
            .withColumnRenamed("WWI City ID", "_rt_id"))
    dim_cols = dim.columns
    d = dim.join(rtco, dim["WWI City ID"] == rtco["_rt_id"], "left")
    d = d.withColumn(
        "Valid To",
        F.when(F.col("_rt_id").isNotNull() & (F.col("Valid To") == eot), F.col("_rt_vf"))
         .otherwise(F.col("Valid To")).cast(ts_type))
    d = d.select(*[F.col(c) for c in dim_cols])
    d = d.select(*[F.col(c).cast(dim.schema[c].dataType) for c in dim_cols])

    # Insert staged rows
    max_key = dim.agg(F.coalesce(F.max("City Key"), F.lit(0)).alias("_mk"))
    w = Window.orderBy("City Staging Key")
    s = stg.withColumn("_rn", F.row_number().over(w)).crossJoin(max_key).crossJoin(lk)
    s = s.withColumn("City Key", (F.col("_mk") + F.col("_rn")))
    s = s.withColumn("Lineage Key", F.col("_lk"))
    s = s.select(*[F.col(c).cast(dim.schema[c].dataType).alias(c) for c in dim_cols])
    new_dim = d.unionByName(s)

    # Lineage update
    lin_cols = lin.columns
    l = lin.crossJoin(lk)
    hit = F.col("Lineage Key") == F.col("_lk")
    l = l.withColumn(
        "Data Load Completed",
        F.when(hit, F.current_timestamp()).otherwise(F.col("Data Load Completed"))
    ).withColumn(
        "Was Successful",
        F.when(hit, F.lit(True)).otherwise(F.col("Was Successful")))
    new_lin = l.select(*[F.col(c).cast(lin.schema[c].dataType).alias(c) for c in lin_cols])

    # ETL Cutoff update
    src = (lin.crossJoin(lk)
           .filter(F.col("Lineage Key") == F.col("_lk"))
           .agg(F.max("Source System Cutoff Time").alias("_src")))
    c = cutoff.crossJoin(src)
    c = c.withColumn(
        "Cutoff Time",
        F.when(F.col("Table Name") == "City", F.col("_src")).otherwise(F.col("Cutoff Time")))
    new_cut = c.select(*[F.col(x).cast(cutoff.schema[x].dataType).alias(x) for x in cutoff.columns])

    return {
        "Dimension.City": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
