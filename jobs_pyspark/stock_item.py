from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.Stock Item"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]
    stg = tables["Integration.StockItem_Staging"]

    # Lineage key: highest key for 'Stock Item' whose load has not completed
    lk = lin.filter((F.col("Table Name") == "Stock Item") & F.col("Data Load Completed").isNull()) \
        .agg(F.max("Lineage Key")).collect()[0][0]

    eot = F.lit("9999-12-31 23:59:59.999999").cast("timestamp")

    # Close off current rows
    rtco = stg.groupBy("WWI Stock Item ID").agg(F.min("Valid From").alias("_rtco_from"))
    d = dim.join(rtco, on="WWI Stock Item ID", how="left")
    vt_type = dim.schema["Valid To"].dataType
    new_vt = F.when(F.col("Valid To") == eot,
                    F.when(F.col("_rtco_from").isNotNull(), F.col("_rtco_from"))
                    .otherwise(F.col("Valid To"))).otherwise(F.col("Valid To")).cast(vt_type)
    d = d.withColumn("Valid To", new_vt)
    closed = d.select(*[F.col(c).alias(c) for c in dim.columns])

    # Insert staged rows
    max_key = dim.agg(F.max("Stock Item Key")).collect()[0][0]
    if max_key is None:
        max_key = 0
    w = Window.orderBy("Stock Item Staging Key")
    s = stg.withColumn("_rn", F.row_number().over(w))
    cols = {}
    for c in dim.columns:
        t = dim.schema[c].dataType
        if c == "Stock Item Key":
            cols[c] = (F.col("_rn") + F.lit(max_key)).cast(t)
        elif c == "Lineage Key":
            cols[c] = F.lit(lk).cast(t)
        else:
            cols[c] = F.col(c).cast(t)
    ins = s.select(*[cols[c].alias(c) for c in dim.columns])
    new_dim = closed.unionByName(ins)

    # Lineage update
    cond = F.col("Lineage Key") == F.lit(lk)
    new_lin = lin.select(
        F.col("Lineage Key"),
        F.col("Data Load Started"),
        F.col("Table Name"),
        F.when(cond, F.current_timestamp()).otherwise(F.col("Data Load Completed"))
        .cast(lin.schema["Data Load Completed"].dataType).alias("Data Load Completed"),
        F.when(cond, F.lit(True)).otherwise(F.col("Was Successful"))
        .cast(lin.schema["Was Successful"].dataType).alias("Was Successful"),
        F.col("Source System Cutoff Time"),
    )

    # ETL Cutoff update
    rows = lin.filter(F.col("Lineage Key") == F.lit(lk)).select("Source System Cutoff Time").limit(1).collect()
    cutoff_val = rows[0][0] if rows else None
    ct_type = cut.schema["Cutoff Time"].dataType
    new_cut = cut.select(
        F.col("Table Name"),
        F.when(F.col("Table Name") == "Stock Item", F.lit(cutoff_val).cast(ct_type))
        .otherwise(F.col("Cutoff Time")).cast(ct_type).alias("Cutoff Time"),
    )

    return {
        "Dimension.Stock Item": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
