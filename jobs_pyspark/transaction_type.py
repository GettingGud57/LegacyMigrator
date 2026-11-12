from pyspark.sql import functions as F
from pyspark.sql.window import Window


def run(spark, tables):
    dim = tables["Dimension.Transaction Type"]
    lin = tables["Integration.Lineage"]
    cut = tables["Integration.ETL Cutoff"]
    stg = tables["Integration.TransactionType_Staging"]

    # Lineage key: latest open lineage row for 'Transaction Type'
    lk_rows = (lin.filter((F.col("Table Name") == "Transaction Type") & F.col("Data Load Completed").isNull())
               .orderBy(F.col("Lineage Key").desc()).limit(1).collect())
    lk = lk_rows[0]["Lineage Key"] if lk_rows else None

    # Source cutoff for that lineage key (before lineage update; column is unchanged by it)
    if lk is not None:
        sc_rows = lin.filter(F.col("Lineage Key") == lk).select("Source System Cutoff Time").limit(1).collect()
        sc = sc_rows[0][0] if sc_rows else None
    else:
        sc = None

    ts_type = dim.schema["Valid To"].dataType
    end_of_time = F.lit("9999-12-31 23:59:59.999999").cast(ts_type)

    # Close off existing rows
    rtco = stg.groupBy("WWI Transaction Type ID").agg(F.min("Valid From").alias("_rtco_from"))
    d = dim.alias("pm").join(
        rtco.alias("r"),
        F.col("pm.WWI Transaction Type ID") == F.col("r.WWI Transaction Type ID"),
        "left",
    )
    new_valid_to = F.when(
        F.col("r._rtco_from").isNotNull() & (F.col("pm.Valid To") == end_of_time),
        F.col("r._rtco_from"),
    ).otherwise(F.col("pm.Valid To")).cast(ts_type)
    closed = d.select(
        F.col("pm.Transaction Type Key").alias("Transaction Type Key"),
        F.col("pm.WWI Transaction Type ID").alias("WWI Transaction Type ID"),
        F.col("pm.Transaction Type").alias("Transaction Type"),
        F.col("pm.Valid From").alias("Valid From"),
        new_valid_to.alias("Valid To"),
        F.col("pm.Lineage Key").alias("Lineage Key"),
    )

    # Insert staged rows with identity keys
    max_key = dim.agg(F.coalesce(F.max("Transaction Type Key"), F.lit(0)).alias("m")).collect()[0]["m"]
    w = Window.orderBy("Transaction Type Staging Key")
    new_rows = stg.select(
        (F.row_number().over(w) + F.lit(max_key)).cast(dim.schema["Transaction Type Key"].dataType).alias("Transaction Type Key"),
        F.col("WWI Transaction Type ID").cast(dim.schema["WWI Transaction Type ID"].dataType).alias("WWI Transaction Type ID"),
        F.col("Transaction Type").cast(dim.schema["Transaction Type"].dataType).alias("Transaction Type"),
        F.col("Valid From").cast(dim.schema["Valid From"].dataType).alias("Valid From"),
        F.col("Valid To").cast(dim.schema["Valid To"].dataType).alias("Valid To"),
        F.lit(lk).cast(dim.schema["Lineage Key"].dataType).alias("Lineage Key"),
    )
    new_dim = closed.unionByName(new_rows)

    # Lineage update
    cond = F.col("Lineage Key") == F.lit(lk).cast(lin.schema["Lineage Key"].dataType)
    new_lin = lin.select(
        F.col("Lineage Key"),
        F.col("Data Load Started"),
        F.col("Table Name"),
        F.when(cond, F.current_timestamp().cast(lin.schema["Data Load Completed"].dataType))
         .otherwise(F.col("Data Load Completed")).alias("Data Load Completed"),
        F.when(cond, F.lit(True)).otherwise(F.col("Was Successful"))
         .cast(lin.schema["Was Successful"].dataType).alias("Was Successful"),
        F.col("Source System Cutoff Time"),
    )

    # ETL Cutoff update
    cut_type = cut.schema["Cutoff Time"].dataType
    new_cut = cut.select(
        F.col("Table Name"),
        F.when(F.col("Table Name") == "Transaction Type", F.lit(sc).cast(cut_type))
         .otherwise(F.col("Cutoff Time")).cast(cut_type).alias("Cutoff Time"),
    )

    return {
        "Dimension.Transaction Type": new_dim,
        "Integration.Lineage": new_lin,
        "Integration.ETL Cutoff": new_cut,
    }
