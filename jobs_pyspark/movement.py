from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stg = tables["Integration.Movement_Staging"]
    cust = tables["Dimension.Customer"]
    si = tables["Dimension.Stock Item"]
    sup = tables["Dimension.Supplier"]
    tt = tables["Dimension.Transaction Type"]
    fact = tables["Fact.Movement"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]

    SK = "Movement Staging Key"
    LM = "Last Modifed When"

    # Lineage key
    lk_df = (lin.filter((F.col("Table Name") == "Movement") & F.col("Data Load Completed").isNull())
             .agg(F.max("Lineage Key").alias("lk")))
    lk_df = lk_df.select(F.col("lk").cast(fact.schema["Lineage Key"].dataType).alias("lk"))

    def lookup(dim, idcol, keycol, stg_idcol, outname):
        d = dim.select(F.col(idcol).alias("_did"), F.col(keycol).alias("_dkey"),
                       F.col("Valid From").alias("_vf"), F.col("Valid To").alias("_vt"))
        s = stg.select(F.col(SK).alias("_sk"), F.col(stg_idcol).alias("_sid"), F.col(LM).alias("_lm"))
        j = s.join(d, (F.col("_did") == F.col("_sid")) & (F.col("_lm") > F.col("_vf"))
                   & (F.col("_lm") <= F.col("_vt")), "inner")
        w = Window.partitionBy("_sk").orderBy(F.col("_vf"))
        j = j.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1)
        return j.select(F.col("_sk"), F.col("_dkey").alias(outname))

    l_si = lookup(si, "WWI Stock Item ID", "Stock Item Key", "WWI Stock Item ID", "_n_si")
    l_c = lookup(cust, "WWI Customer ID", "Customer Key", "WWI Customer ID", "_n_c")
    l_s = lookup(sup, "WWI Supplier ID", "Supplier Key", "WWI Supplier ID", "_n_s")
    l_t = lookup(tt, "WWI Transaction Type ID", "Transaction Type Key", "WWI Transaction Type ID", "_n_t")

    s2 = stg
    for l in (l_si, l_c, l_s, l_t):
        s2 = s2.join(l, s2[SK] == l["_sk"], "left").drop("_sk")

    def keycast(name):
        return fact.schema[name].dataType

    new_stg = s2.select(
        *[
            (F.coalesce(F.col("_n_si"), F.lit(0)).cast(keycast("Stock Item Key")).alias("Stock Item Key")
             if c == "Stock Item Key" else
             F.coalesce(F.col("_n_c"), F.lit(0)).cast(keycast("Customer Key")).alias("Customer Key")
             if c == "Customer Key" else
             F.coalesce(F.col("_n_s"), F.lit(0)).cast(keycast("Supplier Key")).alias("Supplier Key")
             if c == "Supplier Key" else
             F.coalesce(F.col("_n_t"), F.lit(0)).cast(keycast("Transaction Type Key")).alias("Transaction Type Key")
             if c == "Transaction Type Key" else
             F.col(c))
            for c in stg.columns
        ]
    )

    # Merge into fact
    TID = "WWI Stock Item Transaction ID"
    fcols = fact.columns
    s_m = new_stg.select(
        F.col(TID).alias("_tid"),
        F.col("Date Key").alias("_dk"),
        F.col("Stock Item Key").alias("_si"),
        F.col("Customer Key").alias("_c"),
        F.col("Supplier Key").alias("_s"),
        F.col("Transaction Type Key").alias("_t"),
        F.col("WWI Invoice ID").alias("_inv"),
        F.col("WWI Purchase Order ID").alias("_po"),
        F.col("Quantity").alias("_q"),
        F.lit(1).alias("_m"),
    )
    j = fact.join(s_m, fact[TID] == s_m["_tid"], "left")
    mt = F.col("_m").isNotNull()
    lk = lk_df.collect()[0]["lk"] if False else None  # placeholder, not used
    j = j.crossJoin(lk_df)
    repl = {
        "Date Key": "_dk", "Stock Item Key": "_si", "Customer Key": "_c",
        "Supplier Key": "_s", "Transaction Type Key": "_t",
        "WWI Invoice ID": "_inv", "WWI Purchase Order ID": "_po", "Quantity": "_q",
    }
    cols = []
    for c in fcols:
        dt = fact.schema[c].dataType
        if c in repl:
            cols.append(F.when(mt, F.col(repl[c])).otherwise(F.col(c)).cast(dt).alias(c))
        elif c == "Lineage Key":
            cols.append(F.when(mt, F.col("lk")).otherwise(F.col(c)).cast(dt).alias(c))
        else:
            cols.append(F.col(c))
    updated = j.select(*cols)

    # Inserts
    ins = new_stg.join(fact.select(F.col(TID).alias("_ftid")),
                       new_stg[TID] == F.col("_ftid"), "left_anti")
    maxk = fact.agg(F.coalesce(F.max("Movement Key"), F.lit(0)).alias("_mx"))
    ins = ins.crossJoin(maxk).crossJoin(lk_df)
    w = Window.orderBy(F.col(SK))
    ins = ins.withColumn("_rk", F.row_number().over(w))
    ins_sel = ins.select(
        (F.col("_mx") + F.col("_rk")).cast(fact.schema["Movement Key"].dataType).alias("Movement Key"),
        F.col("Date Key").cast(fact.schema["Date Key"].dataType).alias("Date Key"),
        F.col("Stock Item Key").cast(fact.schema["Stock Item Key"].dataType).alias("Stock Item Key"),
        F.col("Customer Key").cast(fact.schema["Customer Key"].dataType).alias("Customer Key"),
        F.col("Supplier Key").cast(fact.schema["Supplier Key"].dataType).alias("Supplier Key"),
        F.col("Transaction Type Key").cast(fact.schema["Transaction Type Key"].dataType).alias("Transaction Type Key"),
        F.col(TID).cast(fact.schema[TID].dataType).alias(TID),
        F.col("WWI Invoice ID").cast(fact.schema["WWI Invoice ID"].dataType).alias("WWI Invoice ID"),
        F.col("WWI Purchase Order ID").cast(fact.schema["WWI Purchase Order ID"].dataType).alias("WWI Purchase Order ID"),
        F.col("Quantity").cast(fact.schema["Quantity"].dataType).alias("Quantity"),
        F.col("lk").cast(fact.schema["Lineage Key"].dataType).alias("Lineage Key"),
    ).select(*fcols)
    new_fact = updated.select(*fcols).unionByName(ins_sel)

    # Lineage update
    lkv = lk_df.select(F.col("lk").alias("_lk"))
    l2 = lin.crossJoin(lkv)
    is_t = F.col("Lineage Key") == F.col("_lk")
    new_lin = l2.select(
        *[
            (F.when(is_t, F.current_timestamp()).otherwise(F.col(c))
             .cast(lin.schema[c].dataType).alias(c) if c == "Data Load Completed" else
             F.when(is_t, F.lit(True)).otherwise(F.col(c))
             .cast(lin.schema[c].dataType).alias(c) if c == "Was Successful" else
             F.col(c))
            for c in lin.columns
        ]
    )

    # ETL Cutoff update
    src = (lin.join(lkv, lin["Lineage Key"] == lkv["_lk"], "inner")
           .agg(F.max("Source System Cutoff Time").alias("_cv")))
    c2 = cut.crossJoin(src)
    new_cut = c2.select(
        *[
            (F.when(F.col("Table Name") == "Movement", F.col("_cv"))
             .otherwise(F.col(c)).cast(cut.schema[c].dataType).alias(c)
             if c == "Cutoff Time" else F.col(c))
            for c in cut.columns
        ]
    )

    return {
        "Integration.Movement_Staging": new_stg,
        "Fact.Movement": new_fact,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
