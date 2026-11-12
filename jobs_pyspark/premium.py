from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stg = tables["Integration.Premium_Staging"]
    fact = tables["Fact.Premium"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]
    pol = tables["Dimension.Policy"]
    cus = tables["Dimension.Customer"]
    emp = tables["Dimension.Employee"]

    # Lineage key
    lk_row = (lin.filter((F.col("Table Name") == "Premium") & F.col("Data Load Completed").isNull())
              .agg(F.max("Lineage Key").alias("k")).collect())
    lk = lk_row[0]["k"] if lk_row else None

    def lookup(dim, dim_src, dim_key, stg_src, outname):
        s = stg.select(F.col("Premium Staging Key").alias("_sk"),
                       F.col(stg_src).alias("_src"),
                       F.col("Last Modified When").alias("_lmw"))
        d = dim.select(F.col(dim_src).alias("_dsrc"),
                       F.col(dim_key).alias("_dkey"),
                       F.col("Valid From").alias("_vf"),
                       F.col("Valid To").alias("_vt"))
        j = s.join(d, (F.col("_dsrc") == F.col("_src")) &
                   (F.col("_lmw") > F.col("_vf")) &
                   (F.col("_lmw") <= F.col("_vt")), "inner")
        w = Window.partitionBy("_sk").orderBy(F.col("_vf").asc(), F.col("_dkey").asc())
        j = (j.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1)
             .select("_sk", F.col("_dkey").alias(outname)))
        return j

    pk = lookup(pol, "Source Policy ID", "Policy Key", "Source Policy ID", "_pk")
    ck = lookup(cus, "Source Customer ID", "Customer Key", "Source Customer ID", "_ck")
    ak = lookup(emp, "Source Employee ID", "Employee Key", "Source Agent ID", "_ak")

    base = stg.drop("Policy Key", "Customer Key", "Agent Key")
    s2 = (base
          .join(pk, base["Premium Staging Key"] == pk["_sk"], "left").drop("_sk")
          .join(ck, base["Premium Staging Key"] == ck["_sk"], "left").drop("_sk")
          .join(ak, base["Premium Staging Key"] == ak["_sk"], "left").drop("_sk"))
    s2 = (s2.withColumn("Policy Key", F.coalesce(F.col("_pk"), F.lit(0)).cast("long"))
          .withColumn("Customer Key", F.coalesce(F.col("_ck"), F.lit(0)).cast("long"))
          .withColumn("Agent Key", F.coalesce(F.col("_ak"), F.lit(0)).cast("long")))
    new_stg = s2.select(*[F.col(f.name).cast(f.dataType).alias(f.name) if f.name not in
                          ("Policy Key", "Customer Key", "Agent Key")
                          else F.col(f.name).cast("long").alias(f.name)
                          for f in stg.schema.fields])

    # Fact
    mx = fact.agg(F.max("Premium Key").alias("m")).collect()[0]["m"]
    mx = mx if mx is not None else 0
    kept = fact.join(stg.select("Source Transaction ID").alias("x"),
                     on="Source Transaction ID", how="left_anti")
    kept = kept.select(*[F.col(f.name) for f in fact.schema.fields])

    fs = fact.schema
    w = Window.orderBy("Premium Staging Key")
    comm = F.round(F.col("Gross Premium") * F.col("Commission Rate"), 2)
    tax = F.round(F.col("Gross Premium") * F.col("Tax Rate"), 2)
    lkcol = F.lit(lk).cast(fs["Lineage Key"].dataType)
    ins = new_stg.select(
        (F.row_number().over(w) + F.lit(mx)).cast(fs["Premium Key"].dataType).alias("Premium Key"),
        F.col("Policy Key").cast(fs["Policy Key"].dataType).alias("Policy Key"),
        F.col("Customer Key").cast(fs["Customer Key"].dataType).alias("Customer Key"),
        F.col("Agent Key").cast(fs["Agent Key"].dataType).alias("Agent Key"),
        F.col("Transaction Date Key").cast(fs["Transaction Date Key"].dataType).alias("Transaction Date Key"),
        F.col("Source Transaction ID").cast(fs["Source Transaction ID"].dataType).alias("Source Transaction ID"),
        F.col("Transaction Type").cast(fs["Transaction Type"].dataType).alias("Transaction Type"),
        F.col("Gross Premium").cast(fs["Gross Premium"].dataType).alias("Gross Premium"),
        comm.cast("decimal(18,2)").cast(fs["Commission Amount"].dataType).alias("Commission Amount"),
        tax.cast("decimal(18,2)").cast(fs["Tax Amount"].dataType).alias("Tax Amount"),
        (F.col("Gross Premium") - comm).cast("decimal(18,2)").cast(fs["Net Premium"].dataType).alias("Net Premium"),
        lkcol.alias("Lineage Key"),
    )
    new_fact = kept.unionByName(ins)

    # Lineage
    cond = (F.col("Lineage Key") == F.lit(lk)) if lk is not None else F.lit(False)
    cond = F.coalesce(cond, F.lit(False))
    ls = lin.schema
    new_lin = lin.select(*[
        (F.when(cond, F.current_timestamp().cast(ls[c].dataType)).otherwise(F.col(c)).alias(c)
         if c == "Data Load Completed" else
         F.when(cond, F.lit(True)).otherwise(F.col(c)).cast(ls[c].dataType).alias(c)
         if c == "Was Successful" else F.col(c))
        for c in lin.columns])

    # ETL Cutoff
    cval = None
    if lk is not None:
        rows = lin.filter(F.col("Lineage Key") == lk).select("Source System Cutoff Time").collect()
        if rows:
            cval = rows[0][0]
    cs = cut.schema
    new_cut = cut.select(
        F.col("Table Name"),
        F.when(F.col("Table Name") == "Premium", F.lit(cval).cast(cs["Cutoff Time"].dataType))
        .otherwise(F.col("Cutoff Time")).cast(cs["Cutoff Time"].dataType).alias("Cutoff Time"))

    return {
        "Integration.Premium_Staging": new_stg,
        "Fact.Premium": new_fact,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
