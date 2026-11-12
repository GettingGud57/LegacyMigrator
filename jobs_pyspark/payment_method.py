from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.Payment Method"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]
    stg = tables["Integration.PaymentMethod_Staging"]

    # @LineageKey: latest open lineage row for 'Payment Method'
    lk = (lin.filter((F.col("Table Name") == "Payment Method") & F.col("Data Load Completed").isNull())
             .agg(F.max("Lineage Key").alias("_lk")))

    # Source system cutoff for that lineage key (one row always, possibly NULL)
    lin_ren = lin.select(F.col("Lineage Key").alias("_lin_key"),
                         F.col("Source System Cutoff Time").alias("_cut"))
    lk_cut = (lk.join(lin_ren, F.col("_lk") == F.col("_lin_key"), "left")
                .select("_lk", "_cut"))
    lk_cut = lk_cut.agg(F.max("_lk").alias("_lk"), F.max("_cut").alias("_cut"))

    end_of_time = F.lit("9999-12-31 23:59:59.999999").cast("timestamp")

    # Step 1: close off existing rows
    rtco = (stg.groupBy("WWI Payment Method ID")
               .agg(F.min("Valid From").alias("_new_to"))
               .withColumnRenamed("WWI Payment Method ID", "_rt_id"))
    dim_j = dim.join(rtco, dim["WWI Payment Method ID"] == F.col("_rt_id"), "left")
    vt_type = dim.schema["Valid To"].dataType
    new_valid_to = (F.when(F.col("_rt_id").isNotNull() & (F.col("Valid To") == end_of_time),
                           F.col("_new_to"))
                     .otherwise(F.col("Valid To")).cast(vt_type))
    dim_cols = dim.columns
    dim_updated = dim_j.select(*[
        (new_valid_to.alias(c) if c == "Valid To" else F.col(c)) for c in dim_cols
    ])

    # Step 2: insert staged rows
    max_key = dim.agg(F.coalesce(F.max("Payment Method Key"), F.lit(0)).alias("_mk"))
    w = Window.orderBy("Payment Method Staging Key")
    stg_j = (stg.crossJoin(max_key).crossJoin(lk)
                .withColumn("_rn", F.row_number().over(w)))
    new_rows = stg_j.select(
        (F.col("_mk") + F.col("_rn")).cast(dim.schema["Payment Method Key"].dataType).alias("Payment Method Key"),
        F.col("WWI Payment Method ID").cast(dim.schema["WWI Payment Method ID"].dataType).alias("WWI Payment Method ID"),
        F.col("Payment Method").cast(dim.schema["Payment Method"].dataType).alias("Payment Method"),
        F.col("Valid From").cast(dim.schema["Valid From"].dataType).alias("Valid From"),
        F.col("Valid To").cast(dim.schema["Valid To"].dataType).alias("Valid To"),
        F.col("_lk").cast(dim.schema["Lineage Key"].dataType).alias("Lineage Key"),
    )
    new_dim = dim_updated.select(*dim_cols).unionByName(new_rows.select(*dim_cols))

    # Step 3: update lineage
    lin_j = lin.crossJoin(lk)
    match = F.col("Lineage Key") == F.col("_lk")
    lin_cols = lin.columns
    new_lin = lin_j.select(*[
        (F.when(match, F.current_timestamp()).otherwise(F.col(c)).cast(lin.schema[c].dataType).alias(c)
         if c == "Data Load Completed" else
         F.when(match, F.lit(True)).otherwise(F.col(c)).cast(lin.schema[c].dataType).alias(c)
         if c == "Was Successful" else F.col(c))
        for c in lin_cols
    ])

    # Step 4: update ETL cutoff
    cut_j = cut.crossJoin(lk_cut)
    cut_cols = cut.columns
    new_cut = cut_j.select(*[
        (F.when(F.col("Table Name") == "Payment Method", F.col("_cut"))
          .otherwise(F.col(c)).cast(cut.schema[c].dataType).alias(c)
         if c == "Cutoff Time" else F.col(c))
        for c in cut_cols
    ])

    return {
        "Dimension.Payment Method": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
