from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stg = tables["Integration.Sale_Staging"]
    fact = tables["Fact.Sale"]
    lineage = tables["Integration.Lineage"]
    cutoff = tables["Integration.ETL Cutoff"]

    SK = "Sale Staging Key"

    def lookup(dim, dimid, keycol, stgid, outname):
        s0 = stg.select(F.col(SK).alias("_sk"), F.col(stgid).alias("_sid"),
                        F.col("Last Modified When").alias("_lmw"))
        d = dim.select(F.col(dimid).alias("_id"), F.col(keycol).alias("_k"),
                       F.col("Valid From").alias("_vf"), F.col("Valid To").alias("_vt"))
        j = s0.join(d, (F.col("_id") == F.col("_sid")) &
                    (F.col("_lmw") > F.col("_vf")) &
                    (F.col("_lmw") <= F.col("_vt")), "inner")
        w = Window.partitionBy("_sk").orderBy(F.col("_vf").asc())
        j = j.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1)
        return j.select(F.col("_sk"), F.col("_k").cast("long").alias(outname))

    lk_city = lookup(tables["Dimension.City"], "WWI City ID", "City Key", "WWI City ID", "_city")
    lk_cust = lookup(tables["Dimension.Customer"], "WWI Customer ID", "Customer Key", "WWI Customer ID", "_cust")
    lk_bill = lookup(tables["Dimension.Customer"], "WWI Customer ID", "Customer Key", "WWI Bill To Customer ID", "_bill")
    lk_item = lookup(tables["Dimension.Stock Item"], "WWI Stock Item ID", "Stock Item Key", "WWI Stock Item ID", "_item")
    lk_emp = lookup(tables["Dimension.Employee"], "WWI Employee ID", "Employee Key", "WWI Salesperson ID", "_emp")

    orig_cols = stg.columns
    s = stg
    for lk, nm, target in [(lk_city, "_city", "City Key"),
                           (lk_cust, "_cust", "Customer Key"),
                           (lk_bill, "_bill", "Bill To Customer Key"),
                           (lk_item, "_item", "Stock Item Key"),
                           (lk_emp, "_emp", "Salesperson Key")]:
        s = s.join(lk, F.col(SK) == F.col("_sk"), "left").drop("_sk")
        s = s.withColumn(target, F.coalesce(F.col(nm), F.lit(0).cast("long"))).drop(nm)
    new_stg = s.select(*orig_cols)

    # Lineage key
    lk = (lineage.filter((F.col("Table Name") == "Sale") & F.col("Data Load Completed").isNull())
          .agg(F.max("Lineage Key").alias("_lk")))
    cut = (lineage.join(lk, F.col("Lineage Key") == F.col("_lk"))
           .agg(F.max("Source System Cutoff Time").alias("_c")))

    # Delete existing invoices
    inv = new_stg.select(F.col("WWI Invoice ID").alias("_inv")).filter(F.col("_inv").isNotNull()).distinct()
    kept = fact.join(inv, F.col("WWI Invoice ID") == F.col("_inv"), "left_anti")

    # Insert
    maxkey = fact.agg(F.coalesce(F.max("Sale Key"), F.lit(0)).cast("long").alias("_mx"))
    w = Window.orderBy(F.col(SK))
    ins = (new_stg.crossJoin(maxkey).crossJoin(lk)
           .withColumn("Sale Key", (F.col("_mx") + F.row_number().over(w)).cast("long"))
           .withColumn("Lineage Key", F.col("_lk").cast("long")))
    fact_cols = fact.columns
    ins = ins.select(*[F.col(c) for c in fact_cols])
    ins = ins.select(*[F.col(c).cast(fact.schema[c].dataType).alias(c) for c in fact_cols])
    new_fact = kept.select(*fact_cols).unionByName(ins)

    # Lineage update
    lin_cols = lineage.columns
    new_lineage = (lineage.crossJoin(lk)
                   .withColumn("_m", F.col("Lineage Key") == F.col("_lk"))
                   .withColumn("Data Load Completed",
                               F.when(F.col("_m"), F.current_timestamp().cast("timestamp"))
                               .otherwise(F.col("Data Load Completed")))
                   .withColumn("Was Successful",
                               F.when(F.col("_m"), F.lit(True)).otherwise(F.col("Was Successful")))
                   .select(*lin_cols))

    # ETL Cutoff update
    cut_cols = cutoff.columns
    new_cutoff = (cutoff.crossJoin(cut)
                  .withColumn("Cutoff Time",
                              F.when(F.col("Table Name") == "Sale", F.col("_c"))
                              .otherwise(F.col("Cutoff Time")))
                  .select(*cut_cols))

    return {
        "Integration.Sale_Staging": new_stg,
        "Fact.Sale": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
