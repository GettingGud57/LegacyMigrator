from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stg = tables["Integration.Claim_Staging"]
    fact = tables["Fact.Claim"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]
    pol = tables["Dimension.Policy"]
    cus = tables["Dimension.Customer"]
    emp = tables["Dimension.Employee"]

    sk = "Claim Staging Key"
    lmw = "Last Modified When"

    def lookup(dim, dim_src, stg_src, dim_key, out_name):
        s = stg.select(
            F.col(sk).alias("_sk"),
            F.col(stg_src).alias("_ssrc"),
            F.col(lmw).alias("_lmw"),
        )
        d = dim.select(
            F.col(dim_src).alias("_dsrc"),
            F.col(dim_key).alias("_dkey"),
            F.col("Valid From").alias("_vf"),
            F.col("Valid To").alias("_vt"),
        )
        j = s.join(
            d,
            (F.col("_dsrc") == F.col("_ssrc"))
            & (F.col("_lmw") > F.col("_vf"))
            & (F.col("_lmw") <= F.col("_vt")),
            "inner",
        )
        w = Window.partitionBy("_sk").orderBy(F.col("_vf").asc())
        j = (
            j.withColumn("_rn", F.row_number().over(w))
            .filter(F.col("_rn") == 1)
            .select(F.col("_sk"), F.col("_dkey").cast("long").alias(out_name))
        )
        return j

    pk = lookup(pol, "Source Policy ID", "Source Policy ID", "Policy Key", "_pk")
    ck = lookup(cus, "Source Customer ID", "Source Customer ID", "Customer Key", "_ck")
    ak = lookup(emp, "Source Employee ID", "Source Adjuster ID", "Employee Key", "_ak")

    s2 = (
        stg.join(pk, stg[sk] == pk["_sk"], "left").drop("_sk")
        .join(ck, stg[sk] == ck["_sk"], "left").drop("_sk")
        .join(ak, stg[sk] == ak["_sk"], "left").drop("_sk")
    )
    s2 = (
        s2.withColumn("Policy Key", F.coalesce(F.col("_pk"), F.lit(0)).cast("long"))
        .withColumn("Customer Key", F.coalesce(F.col("_ck"), F.lit(0)).cast("long"))
        .withColumn("Adjuster Key", F.coalesce(F.col("_ak"), F.lit(0)).cast("long"))
    )
    new_stg = s2.select(*[F.col(f.name) for f in stg.schema.fields])

    # Lineage key
    lk = (
        lin.filter((F.col("Table Name") == "Claim") & F.col("Data Load Completed").isNull())
        .agg(F.max("Lineage Key").alias("_lk"))
    )
    lk_val = lk.select(F.col("_lk").cast("long").alias("_lk"))

    # Fact
    max_key = fact.agg(F.coalesce(F.max("Claim Key"), F.lit(0)).alias("_mx"))
    kept = fact.join(
        stg.select(F.col("Source Claim ID").alias("_sid")).distinct(),
        fact["Source Claim ID"] == F.col("_sid"),
        "left_anti",
    )
    w = Window.orderBy(F.col(sk))
    ins = (
        new_stg.crossJoin(max_key).crossJoin(lk_val)
        .withColumn("_rn", F.row_number().over(w))
    )
    fs = fact.schema
    ins = ins.select(
        (F.col("_mx") + F.col("_rn")).cast(fs["Claim Key"].dataType).alias("Claim Key"),
        F.col("Policy Key").cast(fs["Policy Key"].dataType).alias("Policy Key"),
        F.col("Customer Key").cast(fs["Customer Key"].dataType).alias("Customer Key"),
        F.col("Adjuster Key").cast(fs["Adjuster Key"].dataType).alias("Adjuster Key"),
        F.col("Loss Date Key").cast(fs["Loss Date Key"].dataType).alias("Loss Date Key"),
        F.col("Reported Date Key").cast(fs["Reported Date Key"].dataType).alias("Reported Date Key"),
        F.col("Source Claim ID").cast(fs["Source Claim ID"].dataType).alias("Source Claim ID"),
        F.col("Source Claim Line ID").cast(fs["Source Claim Line ID"].dataType).alias("Source Claim Line ID"),
        F.col("Coverage Type").cast(fs["Coverage Type"].dataType).alias("Coverage Type"),
        F.col("Claim Status").cast(fs["Claim Status"].dataType).alias("Claim Status"),
        F.col("Claimed Amount").cast(fs["Claimed Amount"].dataType).alias("Claimed Amount"),
        F.col("Approved Amount").cast(fs["Approved Amount"].dataType).alias("Approved Amount"),
        F.col("Paid Amount").cast(fs["Paid Amount"].dataType).alias("Paid Amount"),
        F.col("Deductible Applied").cast(fs["Deductible Applied"].dataType).alias("Deductible Applied"),
        F.col("_lk").cast(fs["Lineage Key"].dataType).alias("Lineage Key"),
    )
    new_fact = kept.select(*[F.col(f.name) for f in fs.fields]).unionByName(ins)

    # Lineage update
    ls = lin.schema
    lk_b = lk_val.withColumnRenamed("_lk", "_lkv")
    lj = lin.crossJoin(lk_b)
    is_t = F.col("Lineage Key") == F.col("_lkv")
    new_lin = lj.select(
        *[
            (
                F.when(is_t, F.current_timestamp().cast(ls[n].dataType)).otherwise(F.col(n)).alias(n)
                if n == "Data Load Completed"
                else (
                    F.when(is_t, F.lit(True)).otherwise(F.col(n)).alias(n)
                    if n == "Was Successful"
                    else F.col(n)
                )
            )
            for n in lin.columns
        ]
    )

    # ETL cutoff
    cutoff_val = (
        lk_val.join(lin, lk_val["_lk"] == lin["Lineage Key"], "left")
        .agg(F.max("Source System Cutoff Time").alias("_cv"))
    )
    cs = cut.schema
    new_cut = cut.crossJoin(cutoff_val).select(
        F.col("Table Name"),
        F.when(F.col("Table Name") == "Claim", F.col("_cv").cast(cs["Cutoff Time"].dataType))
        .otherwise(F.col("Cutoff Time"))
        .cast(cs["Cutoff Time"].dataType)
        .alias("Cutoff Time"),
    )

    # Final staging typing
    ss = stg.schema
    out_stg = new_stg.select(
        *[F.col(f.name).cast("long").alias(f.name) if f.name in ("Policy Key", "Customer Key", "Adjuster Key")
          else F.col(f.name) for f in ss.fields]
    )

    return {
        "Integration.Claim_Staging": out_stg,
        "Fact.Claim": new_fact,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
