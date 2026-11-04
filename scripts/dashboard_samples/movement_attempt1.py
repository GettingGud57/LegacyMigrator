from pyspark.sql import functions as F


def run(spark, tables):
    for name, df in tables.items():
        df.createOrReplaceTempView(name.replace(".", "_").replace(" ", "_"))

    staging = tables["Integration.Movement_Staging"]
    lineage_key = (tables["Integration.Lineage"]
                   .filter((F.col("Table Name") == "Movement") & F.col("Data Load Completed").isNull())
                   .agg(F.max("Lineage Key")).collect()[0][0])

    # Merge the data into the fact table
    spark.sql(f"""
        MERGE INTO Fact_Movement AS m
        USING Integration_Movement_Staging AS ms
        ON m.`WWI Stock Item Transaction ID` = ms.`WWI Stock Item Transaction ID`
        WHEN MATCHED THEN UPDATE SET
            m.`Date Key` = ms.`Date Key`, m.Quantity = ms.Quantity, m.`Lineage Key` = {lineage_key}
        WHEN NOT MATCHED THEN INSERT *
    """)
    return {"Fact.Movement": spark.table("Fact_Movement"), "Integration.Movement_Staging": staging}
