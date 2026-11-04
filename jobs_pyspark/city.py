from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    city = tables["Dimension.City"]
    staging = tables["Integration.City_Staging"]
    cutoff = tables["Integration.ETL Cutoff"]
    lineage = tables["Integration.Lineage"]

    # @LineageKey
    lk_row = (
        lineage.filter((F.col("Table Name") == F.lit("City")) & F.col("Data Load Completed").isNull())
        .orderBy(F.col("Lineage Key").desc())
        .select("Lineage Key")
        .limit(1)
        .collect()
    )
    lineage_key = lk_row[0][0] if lk_row else None

    end_of_time = F.to_timestamp(F.lit("9999-12-31 23:59:59.999999"))

    # Close off current rows
    rtco = staging.groupBy("WWI City ID").agg(F.min("Valid From").alias("__rtco_vf"))
    c = city.join(rtco, on="WWI City ID", how="left")
    cond = F.col("__rtco_vf").isNotNull() & (F.col("Valid To") >= end_of_time)
    city_cols = city.columns
    updated = c.select(
        *[
            (F.when(cond, F.col("__rtco_vf")).otherwise(F.col("Valid To")).alias("Valid To"))
            if col == "Valid To"
            else F.col(col)
            for col in city_cols
        ]
    )

    # Insert new rows with generated keys
    max_key_row = city.agg(F.max("City Key")).collect()
    max_key = max_key_row[0][0] if max_key_row and max_key_row[0][0] is not None else 0
    w = Window.orderBy(F.col("City Staging Key"))
    lk_lit = F.lit(lineage_key).cast(city.schema["Lineage Key"].dataType)
    new_rows = staging.withColumn("__rn", F.row_number().over(w)).select(
        *[
            (
                (F.lit(max_key) + F.col("__rn")).cast(city.schema["City Key"].dataType).alias("City Key")
                if col == "City Key"
                else lk_lit.alias("Lineage Key")
                if col == "Lineage Key"
                else F.col(col).cast(city.schema[col].dataType).alias(col)
            )
            for col in city_cols
        ]
    )
    new_city = updated.unionByName(new_rows)

    # Update lineage
    now = F.current_timestamp()
    if lineage_key is not None:
        is_lk = F.col("Lineage Key") == F.lit(lineage_key)
        new_lineage = lineage.select(
            *[
                (F.when(is_lk, now).otherwise(F.col(col)).cast(lineage.schema[col].dataType).alias(col))
                if col == "Data Load Completed"
                else (F.when(is_lk, F.lit(True)).otherwise(F.col(col)).cast("boolean").alias(col))
                if col == "Was Successful"
                else F.col(col)
                for col in lineage.columns
            ]
        )
        sc_row = (
            lineage.filter(F.col("Lineage Key") == F.lit(lineage_key))
            .select("Source System Cutoff Time")
            .collect()
        )
        source_cutoff = sc_row[0][0] if sc_row else None
    else:
        new_lineage = lineage
        source_cutoff = None

    # Update ETL Cutoff
    cut_type = cutoff.schema["Cutoff Time"].dataType
    new_cutoff = cutoff.select(
        *[
            (
                F.when(F.col("Table Name") == F.lit("City"), F.lit(source_cutoff).cast("timestamp"))
                .otherwise(F.col(col))
                .cast(cut_type if str(cut_type) != "NullType()" else "timestamp")
                .alias(col)
            )
            if col == "Cutoff Time"
            else F.col(col)
            for col in cutoff.columns
        ]
    )

    return {
        "Dimension.City": new_city,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
