from pyspark.sql import functions as F


def run(spark, tables):
    dim = tables["Dimension.Supplier"]
    stg = tables["Integration.Supplier_Staging"]
    lin = tables["Integration.Lineage"]
    etl = tables["Integration.ETL Cutoff"]

    eot = F.lit("9999-12-31 23:59:59.999999").cast("timestamp")

    # Latest open lineage key for 'Supplier'
    lk = (lin.filter((F.col("Table Name") == "Supplier") & F.col("Data Load Completed").isNull())
          .agg(F.max("Lineage Key").alias("lk")))

    # Close off existing current rows
    rtco = (stg.groupBy("WWI Supplier ID")
            .agg(F.min("Valid From").alias("new_valid_to")))
    d = dim.alias("d").join(rtco.alias("r"),
                            F.col("d.WWI Supplier ID") == F.col("r.WWI Supplier ID"),
                            "left")
    vt_type = dim.schema["Valid To"].dataType
    cols = []
    for f in dim.schema.fields:
        if f.name == "Valid To":
            cols.append(F.when(F.col("r.new_valid_to").isNotNull() & (F.col("d.Valid To") == eot),
                               F.col("r.new_valid_to"))
                        .otherwise(F.col("d.Valid To")).cast(vt_type).alias("Valid To"))
        else:
            cols.append(F.col("d.`%s`" % f.name).alias(f.name))
    dim_updated = d.select(*cols)

    # Insert staged rows
    max_key = dim.agg(F.coalesce(F.max("Supplier Key"), F.lit(0)).alias("mk"))
    from pyspark.sql import Window
    w = Window.orderBy("Supplier Staging Key")
    s = (stg.withColumn("_rn", F.row_number().over(w))
         .crossJoin(max_key).crossJoin(lk))
    new_cols = []
    for f in dim.schema.fields:
        if f.name == "Supplier Key":
            c = (F.col("mk") + F.col("_rn"))
        elif f.name == "Lineage Key":
            c = F.col("lk")
        else:
            c = F.col("`%s`" % f.name)
        new_cols.append(c.cast(f.dataType).alias(f.name))
    new_rows = s.select(*new_cols)
    dim_out = dim_updated.unionByName(new_rows)

    # Lineage update
    lk2 = lk.alias("k")
    l = lin.crossJoin(lk2)
    hit = F.col("Lineage Key") == F.col("lk")
    lcols = []
    for f in lin.schema.fields:
        if f.name == "Data Load Completed":
            c = F.when(hit, F.current_timestamp()).otherwise(F.col("`%s`" % f.name))
        elif f.name == "Was Successful":
            c = F.when(hit, F.lit(True)).otherwise(F.col("`%s`" % f.name))
        else:
            c = F.col("`%s`" % f.name)
        lcols.append(c.cast(f.dataType).alias(f.name))
    lin_out = l.select(*lcols)

    # ETL Cutoff update
    cut = (lin.join(lk, lin["Lineage Key"] == lk["lk"])
           .agg(F.max("Source System Cutoff Time").alias("ct")))
    e = etl.crossJoin(cut)
    ecols = []
    for f in etl.schema.fields:
        if f.name == "Cutoff Time":
            c = F.when(F.col("Table Name") == "Supplier", F.col("ct")).otherwise(F.col("Cutoff Time"))
        else:
            c = F.col("`%s`" % f.name)
        ecols.append(c.cast(f.dataType).alias(f.name))
    etl_out = e.select(*ecols)

    return {
        "Dimension.Supplier": dim_out,
        "Integration.Lineage": lin_out,
        "Integration.ETL Cutoff": etl_out,
    }
