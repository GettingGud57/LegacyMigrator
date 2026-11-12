from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    dim = tables["Dimension.Stock Item"]
    fact = tables["Fact.Stock Holding"]
    cutoff = tables["Integration.ETL Cutoff"]
    lineage = tables["Integration.Lineage"]
    staging = tables["Integration.StockHolding_Staging"]

    # Lineage key (TOP 1 ... ORDER BY key DESC == max) and its source cutoff time
    lk = (lineage
          .filter((F.col("Table Name") == "Stock Holding") & F.col("Data Load Completed").isNull())
          .agg(F.max("Lineage Key").alias("lk")))
    lk_cut = (lk.join(lineage, lk["lk"] == lineage["Lineage Key"], "left")
              .groupBy("lk")
              .agg(F.max("Source System Cutoff Time").alias("cut")))

    # Dimension lookup: latest Valid To per WWI Stock Item ID
    w = Window.partitionBy("WWI Stock Item ID").orderBy(F.col("Valid To").desc())
    dim_latest = (dim.withColumn("_rn", F.row_number().over(w))
                  .filter(F.col("_rn") == 1)
                  .select(F.col("WWI Stock Item ID").alias("_d_wwi"),
                          F.col("Stock Item Key").alias("_d_key")))

    st = staging.join(dim_latest, staging["WWI Stock Item ID"] == dim_latest["_d_wwi"], "left")
    st = st.withColumn("_newkey", F.coalesce(F.col("_d_key"), F.lit(0)).cast("long"))

    new_staging = st.select(
        *[
            (F.col("_newkey").alias(c) if c == "Stock Item Key" else F.col(c))
            for c in staging.columns
        ]
    )

    # Fact table rebuilt from staging (identity restarts at 1 after truncate)
    fw = Window.orderBy(F.col("Stock Holding Staging Key"))
    fs = fact.schema
    st2 = (st.withColumn("_shk", F.row_number().over(fw))
           .crossJoin(lk))
    new_fact = st2.select(
        F.col("_shk").cast(fs["Stock Holding Key"].dataType).alias("Stock Holding Key"),
        F.col("_newkey").cast(fs["Stock Item Key"].dataType).alias("Stock Item Key"),
        F.col("Quantity On Hand").cast(fs["Quantity On Hand"].dataType).alias("Quantity On Hand"),
        F.col("Bin Location").cast(fs["Bin Location"].dataType).alias("Bin Location"),
        F.col("Last Stocktake Quantity").cast(fs["Last Stocktake Quantity"].dataType).alias("Last Stocktake Quantity"),
        F.col("Last Cost Price").cast(fs["Last Cost Price"].dataType).alias("Last Cost Price"),
        F.col("Reorder Level").cast(fs["Reorder Level"].dataType).alias("Reorder Level"),
        F.col("Target Stock Level").cast(fs["Target Stock Level"].dataType).alias("Target Stock Level"),
        F.col("lk").cast(fs["Lineage Key"].dataType).alias("Lineage Key"),
    )

    # Lineage update
    ls = lineage.schema
    lin = lineage.crossJoin(lk)
    cond = F.col("Lineage Key") == F.col("lk")
    new_lineage = lin.select(
        *[
            (F.when(cond, F.current_timestamp().cast(ls[c].dataType)).otherwise(F.col(c))
             .cast(ls[c].dataType).alias(c)) if c == "Data Load Completed"
            else (F.when(cond, F.lit(True)).otherwise(F.col(c)).cast(ls[c].dataType).alias(c))
            if c == "Was Successful"
            else F.col(c)
            for c in lineage.columns
        ]
    )

    # ETL Cutoff update
    cs = cutoff.schema
    cut_df = cutoff.crossJoin(lk_cut.select("cut"))
    new_cutoff = cut_df.select(
        F.col("Table Name"),
        F.when(F.col("Table Name") == "Stock Holding", F.col("cut"))
         .otherwise(F.col("Cutoff Time"))
         .cast(cs["Cutoff Time"].dataType).alias("Cutoff Time"),
    )

    return {
        "Integration.StockHolding_Staging": new_staging,
        "Fact.Stock Holding": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
