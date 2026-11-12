from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    stock = tables["Dimension.Stock Item"]
    supp = tables["Dimension.Supplier"]
    fact = tables["Fact.Purchase"]
    cutoff = tables["Integration.ETL Cutoff"]
    lineage = tables["Integration.Lineage"]
    staging = tables["Integration.Purchase_Staging"]

    # Lineage key (max of open Purchase loads == TOP 1 ORDER BY DESC)
    lk = (lineage
          .filter((F.col("Table Name") == "Purchase") & F.col("Data Load Completed").isNull())
          .agg(F.max("Lineage Key").alias("lk")))

    # ---- Staging update
    st = staging.withColumn("_rid", F.monotonically_increasing_id())
    orig_cols = staging.columns
    sup_type = staging.schema["Supplier Key"].dataType
    si_type = staging.schema["Stock Item Key"].dataType
    # null-typed columns: real type is bigint (matches the dimension/fact keys)
    key_type = fact.schema["Supplier Key"].dataType
    si_key_type = fact.schema["Stock Item Key"].dataType

    s_look = (st.select("_rid", "WWI Supplier ID", "Last Modified When")
              .join(supp.select(F.col("Supplier Key").alias("_k"),
                                F.col("WWI Supplier ID").alias("_sid"),
                                F.col("Valid From").alias("_vf"),
                                F.col("Valid To").alias("_vt")),
                    (F.col("_sid") == F.col("WWI Supplier ID")) &
                    (F.col("Last Modified When") > F.col("_vf")) &
                    (F.col("Last Modified When") <= F.col("_vt")),
                    "inner")
              .withColumn("_rn", F.row_number().over(
                  Window.partitionBy("_rid").orderBy(F.col("_vf"))))
              .filter(F.col("_rn") == 1)
              .select("_rid", F.col("_k").alias("_supk")))

    i_look = (st.select("_rid", "WWI Stock Item ID", "Last Modified When")
              .join(stock.select(F.col("Stock Item Key").alias("_k"),
                                 F.col("WWI Stock Item ID").alias("_iid"),
                                 F.col("Valid From").alias("_vf"),
                                 F.col("Valid To").alias("_vt")),
                    (F.col("_iid") == F.col("WWI Stock Item ID")) &
                    (F.col("Last Modified When") > F.col("_vf")) &
                    (F.col("Last Modified When") <= F.col("_vt")),
                    "inner")
              .withColumn("_rn", F.row_number().over(
                  Window.partitionBy("_rid").orderBy(F.col("_vf"))))
              .filter(F.col("_rn") == 1)
              .select("_rid", F.col("_k").alias("_itk")))

    st2 = (st.drop("Supplier Key", "Stock Item Key")
           .join(s_look, "_rid", "left")
           .join(i_look, "_rid", "left")
           .withColumn("Supplier Key", F.coalesce(F.col("_supk"), F.lit(0)).cast(key_type))
           .withColumn("Stock Item Key", F.coalesce(F.col("_itk"), F.lit(0)).cast(si_key_type)))

    new_staging = st2.select(*[F.col(c) for c in orig_cols])

    # ---- Fact delete
    ids = staging.select(F.col("WWI Purchase Order ID").alias("_oid")).distinct()
    remaining = fact.join(ids, fact["WWI Purchase Order ID"] == ids["_oid"], "left_anti")

    # ---- Fact insert
    max_key = fact.agg(F.coalesce(F.max("Purchase Key"), F.lit(0)).alias("_mx"))
    w = Window.orderBy("Purchase Staging Key", "_rid")
    ins = (st2.crossJoin(max_key).crossJoin(lk)
           .withColumn("_rn", F.row_number().over(w))
           .select(
               (F.col("_mx") + F.col("_rn")).cast(fact.schema["Purchase Key"].dataType).alias("Purchase Key"),
               F.col("Date Key").cast(fact.schema["Date Key"].dataType).alias("Date Key"),
               F.col("Supplier Key").cast(fact.schema["Supplier Key"].dataType).alias("Supplier Key"),
               F.col("Stock Item Key").cast(fact.schema["Stock Item Key"].dataType).alias("Stock Item Key"),
               F.col("WWI Purchase Order ID").cast(fact.schema["WWI Purchase Order ID"].dataType).alias("WWI Purchase Order ID"),
               F.col("Ordered Outers").cast(fact.schema["Ordered Outers"].dataType).alias("Ordered Outers"),
               F.col("Ordered Quantity").cast(fact.schema["Ordered Quantity"].dataType).alias("Ordered Quantity"),
               F.col("Received Outers").cast(fact.schema["Received Outers"].dataType).alias("Received Outers"),
               F.col("Package").cast(fact.schema["Package"].dataType).alias("Package"),
               F.col("Is Order Finalized").cast(fact.schema["Is Order Finalized"].dataType).alias("Is Order Finalized"),
               F.col("lk").cast(fact.schema["Lineage Key"].dataType).alias("Lineage Key"),
           ))
    new_fact = remaining.select(*fact.columns).unionByName(ins.select(*fact.columns))

    # ---- Lineage update
    lcols = lineage.columns
    cond = F.col("Lineage Key") == F.col("lk")
    new_lineage = (lineage.crossJoin(lk)
                   .withColumn("Data Load Completed",
                               F.when(cond, F.current_timestamp().cast(lineage.schema["Data Load Completed"].dataType))
                                .otherwise(F.col("Data Load Completed")))
                   .withColumn("Was Successful",
                               F.when(cond, F.lit(True)).otherwise(F.col("Was Successful"))
                               .cast(lineage.schema["Was Successful"].dataType))
                   .select(*lcols))

    # ---- ETL Cutoff update
    src = (lineage.join(lk, lineage["Lineage Key"] == lk["lk"], "inner")
           .agg(F.max("Source System Cutoff Time").alias("_src")))
    new_cutoff = (cutoff.crossJoin(src)
                  .withColumn("Cutoff Time",
                              F.when(F.col("Table Name") == "Purchase", F.col("_src"))
                               .otherwise(F.col("Cutoff Time"))
                               .cast(cutoff.schema["Cutoff Time"].dataType))
                  .select(*cutoff.columns))

    return {
        "Integration.Purchase_Staging": new_staging,
        "Fact.Purchase": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
