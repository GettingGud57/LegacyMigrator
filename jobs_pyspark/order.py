from pyspark.sql import functions as F
from pyspark.sql.window import Window


def run(spark, tables):
    staging = tables["Integration.Order_Staging"]
    fact = tables["Fact.Order"]
    lineage = tables["Integration.Lineage"]
    cutoff = tables["Integration.ETL Cutoff"]
    city = tables["Dimension.City"]
    cust = tables["Dimension.Customer"]
    emp = tables["Dimension.Employee"]
    si = tables["Dimension.Stock Item"]

    st = staging.withColumn("_rid", F.monotonically_increasing_id())

    def lookup(dim, keycol, idcol, stagecol, outname):
        d = dim.select(F.col(keycol).alias("_dk"), F.col(idcol).alias("_did"),
                       F.col("Valid From").alias("_vf"), F.col("Valid To").alias("_vt"))
        s = st.select("_rid", F.col(stagecol).alias("_sid"), F.col("Last Modified When").alias("_lm"))
        j = s.join(d, (F.col("_sid") == F.col("_did")) &
                   (F.col("_lm") > F.col("_vf")) &
                   (F.col("_lm") <= F.col("_vt")))
        w = Window.partitionBy("_rid").orderBy("_vf", "_dk")
        return (j.withColumn("_rn", F.row_number().over(w))
                .filter(F.col("_rn") == 1)
                .select("_rid", F.col("_dk").alias(outname)))

    key_cols = ["City Key", "Customer Key", "Stock Item Key", "Salesperson Key", "Picker Key"]
    base = st.drop(*key_cols)
    lookups = [
        ("City Key", lookup(city, "City Key", "WWI City ID", "WWI City ID", "City Key")),
        ("Customer Key", lookup(cust, "Customer Key", "WWI Customer ID", "WWI Customer ID", "Customer Key")),
        ("Stock Item Key", lookup(si, "Stock Item Key", "WWI Stock Item ID", "WWI Stock Item ID", "Stock Item Key")),
        ("Salesperson Key", lookup(emp, "Employee Key", "WWI Employee ID", "WWI Salesperson ID", "Salesperson Key")),
        ("Picker Key", lookup(emp, "Employee Key", "WWI Employee ID", "WWI Picker ID", "Picker Key")),
    ]
    for name, lk in lookups:
        base = base.join(lk, "_rid", "left")
        base = base.withColumn(name, F.coalesce(F.col(name), F.lit(0)).cast("long"))

    new_staging = base.select(*[F.col(c) for c in staging.columns])
    staged_with_rid = base  # has _rid and all columns

    # Lineage key
    lk_row = (lineage.filter((F.col("Table Name") == "Order") & F.col("Data Load Completed").isNull())
              .agg(F.max("Lineage Key").alias("_lk")))
    lk_val = lk_row.select(F.col("_lk"))

    # Delete existing facts
    ids = staging.select(F.col("WWI Order ID").alias("_oid")).filter(F.col("_oid").isNotNull()).distinct()
    kept = fact.join(ids, fact["WWI Order ID"] == ids["_oid"], "left_anti")

    # Insert
    max_key = kept.agg(F.coalesce(F.max("Order Key"), F.lit(0)).alias("_mk"))
    ins = staged_with_rid.crossJoin(lk_val).crossJoin(max_key)
    w = Window.orderBy("Order Staging Key", "_rid")
    ins = ins.withColumn("_rn", F.row_number().over(w))
    fs = fact.schema
    ins_cols = []
    for f in fact.schema.fields:
        n = f.name
        if n == "Order Key":
            ins_cols.append((F.col("_mk") + F.col("_rn")).cast(f.dataType).alias(n))
        elif n == "Lineage Key":
            ins_cols.append(F.col("_lk").cast(f.dataType).alias(n))
        else:
            ins_cols.append(F.col(n).cast(f.dataType).alias(n))
    ins = ins.select(*ins_cols)
    new_fact = kept.select(*[F.col(c) for c in fact.columns]).unionByName(ins)

    # Lineage update
    lin_ts = lineage.schema["Data Load Completed"].dataType
    lin_bool = lineage.schema["Was Successful"].dataType
    lcond = F.col("Lineage Key") == F.col("_lk")
    new_lineage = (lineage.crossJoin(lk_val)
                   .withColumn("Data Load Completed",
                               F.when(lcond, F.current_timestamp().cast(lin_ts))
                               .otherwise(F.col("Data Load Completed")))
                   .withColumn("Was Successful",
                               F.when(lcond, F.lit(True).cast(lin_bool))
                               .otherwise(F.col("Was Successful")))
                   .select(*[F.col(c) for c in lineage.columns]))

    # ETL Cutoff update
    src = (lineage.crossJoin(lk_val)
           .filter(F.col("Lineage Key") == F.col("_lk"))
           .agg(F.max("Source System Cutoff Time").alias("_sc")))
    ct = cutoff.schema["Cutoff Time"].dataType
    new_cutoff = (cutoff.crossJoin(src)
                  .withColumn("Cutoff Time",
                              F.when(F.col("Table Name") == "Order", F.col("_sc").cast(ct))
                              .otherwise(F.col("Cutoff Time")))
                  .select(*[F.col(c) for c in cutoff.columns]))

    return {
        "Integration.Order_Staging": new_staging,
        "Fact.Order": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
