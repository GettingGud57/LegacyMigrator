from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stg = tables["Integration.Transaction_Staging"]
    cust = tables["Dimension.Customer"]
    pm = tables["Dimension.Payment Method"]
    sup = tables["Dimension.Supplier"]
    tt = tables["Dimension.Transaction Type"]
    fact = tables["Fact.Transaction"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]

    stg_cols = stg.columns
    base = stg.withColumn("_rid", F.monotonically_increasing_id())

    def lookup(dim, stg_id, dim_id, key_col, out_name):
        s = base.select("_rid", F.col(stg_id).alias("_sid"),
                        F.col("Last Modified When").alias("_lmw"))
        d = dim.select(F.col(dim_id).alias("_did"),
                       F.col("Valid From").alias("_vf"),
                       F.col("Valid To").alias("_vt"),
                       F.col(key_col).alias("_k"))
        j = s.join(d, (F.col("_sid") == F.col("_did")) &
                   (F.col("_lmw") > F.col("_vf")) &
                   (F.col("_lmw") <= F.col("_vt")), "left")
        g = j.groupBy("_rid").agg(F.min(F.struct(F.col("_vf"), F.col("_k"))).alias("_m"))
        return g.select("_rid", F.coalesce(F.col("_m.`_k`"), F.lit(0)).cast("long").alias(out_name))

    lk_c = lookup(cust, "WWI Customer ID", "WWI Customer ID", "Customer Key", "_ck")
    lk_b = lookup(cust, "WWI Bill To Customer ID", "WWI Customer ID", "Customer Key", "_bk")
    lk_s = lookup(sup, "WWI Supplier ID", "WWI Supplier ID", "Supplier Key", "_sk")
    lk_t = lookup(tt, "WWI Transaction Type ID", "WWI Transaction Type ID", "Transaction Type Key", "_tk")
    lk_p = lookup(pm, "WWI Payment Method ID", "WWI Payment Method ID", "Payment Method Key", "_pk")

    j = (base.join(lk_c, "_rid", "left").join(lk_b, "_rid", "left")
         .join(lk_s, "_rid", "left").join(lk_t, "_rid", "left").join(lk_p, "_rid", "left"))

    keymap = {
        "Customer Key": "_ck",
        "Bill To Customer Key": "_bk",
        "Supplier Key": "_sk",
        "Transaction Type Key": "_tk",
        "Payment Method Key": "_pk",
    }
    upd = j
    for c, tmp in keymap.items():
        upd = upd.withColumn(c, F.col(tmp).cast("long"))
    new_stg = upd.select(*[
        (F.col(c).cast("long").alias(c) if c in keymap else F.col(c))
        for c in stg_cols
    ])

    # Lineage key
    lk_df = (lin.filter((F.col("Table Name") == "Transaction") &
                        F.col("Data Load Completed").isNull())
             .agg(F.max("Lineage Key").alias("_lk")))

    # Fact insert
    max_key = fact.agg(F.coalesce(F.max("Transaction Key"), F.lit(0)).alias("_mx"))
    w = Window.orderBy("Transaction Staging Key", "_rid")
    ins = (upd.crossJoin(lk_df).crossJoin(max_key)
           .withColumn("_rn", F.row_number().over(w)))
    fcols = []
    for f in fact.schema.fields:
        n = f.name
        if n == "Transaction Key":
            fcols.append((F.col("_mx") + F.col("_rn")).cast(f.dataType).alias(n))
        elif n == "Lineage Key":
            fcols.append(F.col("_lk").cast(f.dataType).alias(n))
        else:
            fcols.append(F.col(n).cast(f.dataType).alias(n))
    new_rows = ins.select(*fcols)
    new_fact = fact.select(*[F.col(c) for c in fact.columns]).unionByName(new_rows)

    # Lineage update
    lin_x = lin.crossJoin(lk_df)
    match = F.col("Lineage Key") == F.col("_lk")
    dl = lin.schema["Data Load Completed"].dataType
    wsd = lin.schema["Was Successful"].dataType
    new_lin = lin_x.select(*[
        (F.when(match, F.current_timestamp().cast(dl)).otherwise(F.col(c)).cast(dl).alias(c)
         if c == "Data Load Completed" else
         F.when(match, F.lit(True)).otherwise(F.col(c)).cast(wsd).alias(c)
         if c == "Was Successful" else F.col(c))
        for c in lin.columns
    ])

    # ETL cutoff
    src = (lin.crossJoin(lk_df).filter(F.col("Lineage Key") == F.col("_lk"))
           .agg(F.max("Source System Cutoff Time").alias("_src")))
    ct = cut.schema["Cutoff Time"].dataType
    new_cut = cut.crossJoin(src).select(*[
        (F.when(F.col("Table Name") == "Transaction", F.col("_src")).otherwise(F.col("Cutoff Time"))
         .cast(ct).alias(c) if c == "Cutoff Time" else F.col(c))
        for c in cut.columns
    ])

    return {
        "Integration.Transaction_Staging": new_stg,
        "Fact.Transaction": new_fact,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
