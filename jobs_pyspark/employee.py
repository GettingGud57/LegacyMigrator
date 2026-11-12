from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.Employee"]
    stg = tables["Integration.Employee_Staging"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]

    # Lineage key lookup
    lk_rows = (lin.filter((F.col("Table Name") == "Employee") & F.col("Data Load Completed").isNull())
               .orderBy(F.col("Lineage Key").desc()).limit(1).collect())
    lk = lk_rows[0]["Lineage Key"] if lk_rows else None

    end_of_time = F.lit("9999-12-31 23:59:59.999999").cast("timestamp")

    # Close off existing rows
    rtco = stg.groupBy("WWI Employee ID").agg(F.min("Valid From").alias("_rtco_from"))
    d = dim.join(rtco, on="WWI Employee ID", how="left")
    vt_type = dim.schema["Valid To"].dataType
    d = d.withColumn(
        "Valid To",
        F.when(F.col("_rtco_from").isNotNull() & (F.col("Valid To") == end_of_time),
               F.col("_rtco_from")).otherwise(F.col("Valid To")).cast(vt_type))
    d = d.select([F.col(c.name) for c in dim.schema.fields])

    # Insert new rows
    max_key = dim.agg(F.coalesce(F.max("Employee Key"), F.lit(0)).alias("_mk"))
    w = Window.orderBy("Employee Staging Key")
    new = stg.crossJoin(max_key).withColumn("_rn", F.row_number().over(w))
    lk_col = F.lit(lk) if lk is not None else F.lit(None)
    new = new.select(
        (F.col("_mk") + F.col("_rn")).cast(dim.schema["Employee Key"].dataType).alias("Employee Key"),
        F.col("WWI Employee ID").cast(dim.schema["WWI Employee ID"].dataType).alias("WWI Employee ID"),
        F.col("Employee").cast(dim.schema["Employee"].dataType).alias("Employee"),
        F.col("Preferred Name").cast(dim.schema["Preferred Name"].dataType).alias("Preferred Name"),
        F.col("Is Salesperson").cast(dim.schema["Is Salesperson"].dataType).alias("Is Salesperson"),
        F.col("Photo").cast(dim.schema["Photo"].dataType).alias("Photo"),
        F.col("Valid From").cast(dim.schema["Valid From"].dataType).alias("Valid From"),
        F.col("Valid To").cast(dim.schema["Valid To"].dataType).alias("Valid To"),
        lk_col.cast(dim.schema["Lineage Key"].dataType).alias("Lineage Key"),
    )
    new_dim = d.unionByName(new)

    # Lineage update
    cutoff_val = None
    if lk is not None:
        cond = F.col("Lineage Key") == F.lit(lk)
        for r in lin.filter(F.col("Lineage Key") == lk).select("Source System Cutoff Time").limit(1).collect():
            cutoff_val = r[0]
        new_lin = (lin
                   .withColumn("Data Load Completed",
                               F.when(cond, F.current_timestamp().cast("timestamp"))
                                .otherwise(F.col("Data Load Completed"))
                                .cast(lin.schema["Data Load Completed"].dataType))
                   .withColumn("Was Successful",
                               F.when(cond, F.lit(True)).otherwise(F.col("Was Successful"))
                               .cast(lin.schema["Was Successful"].dataType)))
        new_lin = new_lin.select([F.col(c.name) for c in lin.schema.fields])
    else:
        new_lin = lin

    # ETL Cutoff update
    ct_type = cut.schema["Cutoff Time"].dataType
    new_cut = cut.withColumn(
        "Cutoff Time",
        F.when(F.col("Table Name") == "Employee",
               F.lit(cutoff_val).cast(ct_type)).otherwise(F.col("Cutoff Time")).cast(ct_type))
    new_cut = new_cut.select([F.col(c.name) for c in cut.schema.fields])

    return {
        "Dimension.Employee": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
