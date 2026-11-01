from pyspark.sql import functions as F
from pyspark.sql import Window


def run(spark, tables):
    lineage = tables["Integration.Lineage"]
    etl_cutoff = tables["Integration.ETL Cutoff"]
    city = tables["Dimension.City"]
    customer = tables["Dimension.Customer"]
    employee = tables["Dimension.Employee"]
    stock_item = tables["Dimension.Stock Item"]
    fact_sale = tables["Fact.Sale"]
    staging = tables["Integration.Sale_Staging"]

    staging_cols = staging.columns
    fact_cols = fact_sale.columns
    lineage_cols = lineage.columns
    cutoff_cols = etl_cutoff.columns

    # DECLARE @LineageKey = TOP(1) ... ORDER BY [Lineage Key] DESC
    lk_row = (
        lineage
        .filter((F.col("Table Name") == F.lit("Sale")) & F.col("Data Load Completed").isNull())
        .orderBy(F.col("Lineage Key").desc_nulls_last())
        .select("Lineage Key")
        .limit(1)
        .collect()
    )
    lineage_key = lk_row[0]["Lineage Key"] if lk_row else None

    # UPDATE staging: dimension key lookups
    s = staging.withColumn("__rid", F.monotonically_increasing_id())

    def lookup(df, dim, dim_id_col, dim_key_col, stg_id_col, target_col):
        d = dim.select(
            F.col(dim_id_col).alias("__d_id"),
            F.col(dim_key_col).alias("__d_key"),
            F.col("Valid From").alias("__d_from"),
            F.col("Valid To").alias("__d_to"),
        )
        cond = (
            (F.col("__d_id") == F.col(stg_id_col))
            & (F.col("Last Modified When") > F.col("__d_from"))
            & (F.col("Last Modified When") <= F.col("__d_to"))
        )
        joined = df.join(d, cond, "left")
        w = Window.partitionBy("__rid").orderBy(
            F.col("__d_from").asc_nulls_first(), F.col("__d_key").asc_nulls_first()
        )
        joined = (
            joined.withColumn("__rn", F.row_number().over(w))
            .filter(F.col("__rn") == 1)
            .withColumn(
                target_col,
                F.coalesce(F.col("__d_key").cast("long"), F.lit(0).cast("long")),
            )
            .drop("__d_id", "__d_key", "__d_from", "__d_to", "__rn")
        )
        return joined

    s = lookup(s, city, "WWI City ID", "City Key", "WWI City ID", "City Key")
    s = lookup(s, customer, "WWI Customer ID", "Customer Key", "WWI Customer ID", "Customer Key")
    s = lookup(s, customer, "WWI Customer ID", "Customer Key", "WWI Bill To Customer ID", "Bill To Customer Key")
    s = lookup(s, stock_item, "WWI Stock Item ID", "Stock Item Key", "WWI Stock Item ID", "Stock Item Key")
    s = lookup(s, employee, "WWI Employee ID", "Employee Key", "WWI Salesperson ID", "Salesperson Key")

    s = s.localCheckpoint()

    new_staging = s.select(*[F.col(c) for c in staging_cols])

    # DELETE from Fact.Sale where invoice in staging
    stg_ids = (
        staging.select(F.col("WWI Invoice ID").alias("__inv"))
        .filter(F.col("__inv").isNotNull())
        .distinct()
    )
    kept = fact_sale.join(
        stg_ids, fact_sale["WWI Invoice ID"] == stg_ids["__inv"], "left_anti"
    )

    # INSERT new rows with identity Sale Key
    max_row = fact_sale.agg(F.max(F.col("Sale Key")).alias("m")).collect()
    max_key = max_row[0]["m"] if max_row and max_row[0]["m"] is not None else 0

    w_ins = Window.orderBy(F.col("Sale Staging Key").asc_nulls_first(), F.col("__rid"))
    ins = s.withColumn("__rn", F.row_number().over(w_ins))

    fact_types = dict((f.name, f.dataType) for f in fact_sale.schema.fields)

    def fc(name, expr):
        return expr.cast(fact_types[name]).alias(name)

    insert_exprs = []
    for c in fact_cols:
        if c == "Sale Key":
            insert_exprs.append(fc(c, F.lit(max_key) + F.col("__rn")))
        elif c == "Lineage Key":
            insert_exprs.append(fc(c, F.lit(lineage_key)))
        else:
            insert_exprs.append(fc(c, F.col(c)))
    inserted = ins.select(*insert_exprs)

    new_fact = kept.select(*[F.col(c) for c in fact_cols]).unionByName(inserted)

    # UPDATE Integration.Lineage
    lin_types = dict((f.name, f.dataType) for f in lineage.schema.fields)
    if lineage_key is not None:
        is_target = F.col("Lineage Key") == F.lit(lineage_key)
    else:
        is_target = F.lit(False)
    is_target = F.coalesce(is_target, F.lit(False))

    lin_exprs = []
    for c in lineage_cols:
        if c == "Data Load Completed":
            lin_exprs.append(
                F.when(is_target, F.current_timestamp().cast(lin_types[c]))
                .otherwise(F.col(c))
                .alias(c)
            )
        elif c == "Was Successful":
            lin_exprs.append(
                F.when(is_target, F.lit(True).cast(lin_types[c]))
                .otherwise(F.col(c))
                .alias(c)
            )
        else:
            lin_exprs.append(F.col(c))
    new_lineage = lineage.select(*lin_exprs)

    # UPDATE Integration.ETL Cutoff
    cutoff_val = None
    if lineage_key is not None:
        rows = (
            lineage.filter(F.col("Lineage Key") == F.lit(lineage_key))
            .select("Source System Cutoff Time")
            .limit(1)
            .collect()
        )
        cutoff_val = rows[0]["Source System Cutoff Time"] if rows else None

    cut_types = dict((f.name, f.dataType) for f in etl_cutoff.schema.fields)
    is_sale = F.coalesce(F.col("Table Name") == F.lit("Sale"), F.lit(False))
    cut_exprs = []
    for c in cutoff_cols:
        if c == "Cutoff Time":
            cut_exprs.append(
                F.when(is_sale, F.lit(cutoff_val).cast(cut_types[c]))
                .otherwise(F.col(c))
                .alias(c)
            )
        else:
            cut_exprs.append(F.col(c))
    new_cutoff = etl_cutoff.select(*cut_exprs)

    return {
        "Integration.Sale_Staging": new_staging,
        "Fact.Sale": new_fact,
        "Integration.Lineage": new_lineage,
        "Integration.ETL Cutoff": new_cutoff,
    }
