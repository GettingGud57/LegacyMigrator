from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.Customer"]
    stg = tables["Integration.Customer_Staging"]
    cutoff = tables["Integration.ETL Cutoff"]
    lin = tables["Integration.Lineage"]

    # Lineage key lookup (one-row DataFrame, possibly null)
    lk = (lin.filter((F.col("Table Name") == "Customer") & F.col("Data Load Completed").isNull())
             .agg(F.max("Lineage Key").alias("lk")))

    # Source system cutoff for that lineage key (one row, possibly null)
    lk_cut = (lin.join(lk, F.col("Lineage Key") == F.col("lk"), "inner")
                 .agg(F.max("Source System Cutoff Time").alias("new_cutoff")))

    end_of_time = F.lit("9999-12-31 23:59:59.999999").cast("timestamp")

    # 1. Close off existing dimension rows
    rtco = stg.groupBy("WWI Customer ID").agg(F.min("Valid From").alias("min_vf")) \
              .withColumnRenamed("WWI Customer ID", "r_id")
    d = dim.join(rtco, dim["WWI Customer ID"] == rtco["r_id"], "left")
    cond = F.col("r_id").isNotNull() & (F.col("Valid To") >= end_of_time)
    vt_type = dim.schema["Valid To"].dataType
    new_vt = F.when(cond, F.col("min_vf")).otherwise(F.col("Valid To")).cast(vt_type)
    closed = d.select(*[
        (new_vt.alias(c) if c == "Valid To" else F.col(c)) for c in dim.columns
    ])

    # 2. Insert staged rows
    max_key = dim.agg(F.coalesce(F.max("Customer Key"), F.lit(0)).alias("mk"))
    w = Window.orderBy("Customer Staging Key")
    ins = (stg.crossJoin(max_key).crossJoin(lk)
              .withColumn("rn", F.row_number().over(w)))
    ins_cols = []
    for c in dim.columns:
        t = dim.schema[c].dataType
        if c == "Customer Key":
            ins_cols.append((F.col("mk") + F.col("rn")).cast(t).alias(c))
        elif c == "Lineage Key":
            ins_cols.append(F.col("lk").cast(t).alias(c))
        else:
            ins_cols.append(F.col(c).cast(t).alias(c))
    inserted = ins.select(*ins_cols)
    new_dim = closed.unionByName(inserted)

    # 3. Update lineage
    l = lin.crossJoin(lk)
    match = F.col("Lineage Key") == F.col("lk")
    lin_cols = []
    for c in lin.columns:
        t = lin.schema[c].dataType
        if c == "Data Load Completed":
            lin_cols.append(F.when(match, F.current_timestamp()).otherwise(F.col(c)).cast(t).alias(c))
        elif c == "Was Successful":
            lin_cols.append(F.when(match, F.lit(True)).otherwise(F.col(c)).cast(t).alias(c))
        else:
            lin_cols.append(F.col(c))
    new_lin = l.select(*lin_cols)

    # 4. Update ETL cutoff
    cc = cutoff.crossJoin(lk_cut)
    cut_cols = []
    for c in cutoff.columns:
        t = cutoff.schema[c].dataType
        if c == "Cutoff Time":
            cut_cols.append(F.when(F.col("Table Name") == "Customer", F.col("new_cutoff"))
                             .otherwise(F.col(c)).cast(t).alias(c))
        else:
            cut_cols.append(F.col(c))
    new_cutoff = cc.select(*cut_cols)

    return {
        "Dimension.Customer": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cutoff,
    }
