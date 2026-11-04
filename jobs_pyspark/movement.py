from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    lineage = tables["Integration.Lineage"]
    cutoff = tables["Integration.ETL Cutoff"]
    staging = tables["Integration.Movement_Staging"]
    fact = tables["Fact.Movement"]

    staging_cols = staging.columns
    fact_cols = fact.columns
    lineage_cols = lineage.columns
    cutoff_cols = cutoff.columns

    # @LineageKey
    lk_row = (lineage
              .filter((F.col("Table Name") == F.lit("Movement")) & F.col("Data Load Completed").isNull())
              .agg(F.max(F.col("Lineage Key")).alias("lk"))
              .collect())
    lineage_key = lk_row[0]["lk"] if lk_row else None

    # ---- Update staging dimension keys ----
    m = staging.withColumn("_rid", F.monotonically_increasing_id())

    def lookup(m, dim, dim_id_col, m_id_col, key_col, target_col):
        d = dim.select(
            F.col(dim_id_col).alias("_did"),
            F.col("Valid From").alias("_vf"),
            F.col("Valid To").alias("_vt"),
            F.col(key_col).alias("_k"),
        )
        mm = m.select(
            "_rid",
            F.col(m_id_col).alias("_mid"),
            F.col("Last Modifed When").alias("_lmw"),
        )
        j = mm.join(
            d,
            (F.col("_did") == F.col("_mid"))
            & (F.col("_lmw") > F.col("_vf"))
            & (F.col("_lmw") <= F.col("_vt")),
            "inner",
        )
        w = Window.partitionBy("_rid").orderBy(F.col("_vf").asc(), F.col("_k").asc())
        r = (j.withColumn("_rn", F.row_number().over(w))
               .filter(F.col("_rn") == 1)
               .select("_rid", F.col("_k").alias("_newkey")))
        m = (m.join(r, "_rid", "left")
               .withColumn(target_col, F.coalesce(F.col("_newkey"), F.lit(0)).cast("long"))
               .drop("_newkey"))
        return m

    m = lookup(m, tables["Dimension.Stock Item"], "WWI Stock Item ID", "WWI Stock Item ID",
               "Stock Item Key", "Stock Item Key")
    m = lookup(m, tables["Dimension.Customer"], "WWI Customer ID", "WWI Customer ID",
               "Customer Key", "Customer Key")
    m = lookup(m, tables["Dimension.Supplier"], "WWI Supplier ID", "WWI Supplier ID",
               "Supplier Key", "Supplier Key")
    m = lookup(m, tables["Dimension.Transaction Type"], "WWI Transaction Type ID", "WWI Transaction Type ID",
               "Transaction Type Key", "Transaction Type Key")

    new_staging = m.select(*[F.col(c) for c in staging_cols])

    # ---- MERGE into Fact.Movement ----
    lk_lit = F.lit(lineage_key).cast("long")
    upd_cols = ["Date Key", "Stock Item Key", "Customer Key", "Supplier Key",
                "Transaction Type Key", "WWI Invoice ID", "WWI Purchase Order ID", "Quantity"]

    s = new_staging.select(
        F.col("WWI Stock Item Transaction ID").alias("_s_tid"),
        *[F.col(c).alias("_s_" + c) for c in upd_cols],
        F.lit(1).alias("_matched"),
    )

    t = fact.join(s, fact["WWI Stock Item Transaction ID"] == s["_s_tid"], "left")
    matched = F.col("_matched").isNotNull()
    sel = []
    for c in fact_cols:
        if c in upd_cols:
            sel.append(F.when(matched, F.col("_s_" + c)).otherwise(F.col(c)).cast(fact.schema[c].dataType).alias(c))
        elif c == "Lineage Key":
            sel.append(F.when(matched, lk_lit).otherwise(F.col(c)).cast("long").alias(c))
        else:
            sel.append(F.col(c))
    updated_fact = t.select(*sel)

    fact_ids = fact.select(F.col("WWI Stock Item Transaction ID").alias("_f_tid"))
    to_insert = new_staging.join(
        fact_ids,
        new_staging["WWI Stock Item Transaction ID"] == fact_ids["_f_tid"],
        "left_anti",
    )

    max_key_row = fact.agg(F.max(F.col("Movement Key")).alias("mk")).collect()
    max_key = max_key_row[0]["mk"] if max_key_row and max_key_row[0]["mk"] is not None else 0

    w_ins = Window.orderBy(F.col("Movement Staging Key").asc(), F.col("WWI Stock Item Transaction ID").asc())
    inserted = to_insert.withColumn("_rn", F.row_number().over(w_ins))
    ins_sel = []
    for c in fact_cols:
        dt = fact.schema[c].dataType
        if c == "Movement Key":
            ins_sel.append((F.lit(max_key) + F.col("_rn")).cast(dt).alias(c))
        elif c == "Lineage Key":
            ins_sel.append(lk_lit.cast(dt).alias(c))
        else:
            ins_sel.append(F.col(c).cast(dt).alias(c))
    inserted = inserted.select(*ins_sel)

    new_fact = updated_fact.unionByName(inserted)

    # ---- Update Lineage ----
    is_lk = (F.col("Lineage Key") == lk_lit) if lineage_key is not None else F.lit(False)
    lsel = []
    for c in lineage_cols:
        if c == "Data Load Completed":
            lsel.append(F.when(is_lk, F.current_timestamp().cast("timestamp")).otherwise(F.col(c)).alias(c))
        elif c == "Was Successful":
            lsel.append(F.when(is_lk, F.lit(True)).otherwise(F.col(c)).cast("boolean").alias(c))
        else:
            lsel.append(F.col(c))
    new_lineage = lineage.select(*lsel)

    # ---- Update ETL Cutoff ----
    cutoff_val = None
    if lineage_key is not None:
        rows = (lineage.filter(F.col("Lineage Key") == lk_lit)
                       .select("Source System Cutoff Time").limit(1).collect())
        if rows:
            cutoff_val = rows[0][0]
    csel = []
    for c in cutoff_cols:
        if c == "Cutoff Time":
            csel.append(
                F.when(F.col("Table Name") == F.lit("Movement"), F.lit(cutoff_val).cast("timestamp"))
                 .otherwise(F.col(c)).alias(c)
            )
        else:
            csel.append(F.col(c))
    new_cutoff = cutoff.select(*csel)

    return {
        "Integration.Movement_Staging": new_staging,
        "Fact.Movement": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
