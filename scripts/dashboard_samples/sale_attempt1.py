from pyspark.sql import functions as F


def run(spark, tables):
    for name, df in tables.items():
        df.createOrReplaceTempView(name.replace(".", "_").replace(" ", "_"))

    # Find the dimension keys required
    spark.sql("""
        UPDATE s
            SET s.`City Key` = COALESCE((SELECT c.`City Key`
                                         FROM Dimension_City AS c
                                         WHERE c.`WWI City ID` = s.`WWI City ID`
                                         AND s.`Last Modified When` > c.`Valid From`
                                         AND s.`Last Modified When` <= c.`Valid To`
                                         ORDER BY c.`Valid From` LIMIT 1), 0)
        FROM Integration_Sale_Staging AS s
    """)

    staging = spark.table("Integration_Sale_Staging")
    fact = tables["Fact.Sale"]
    kept = fact.join(staging.select("WWI Invoice ID").distinct(), "WWI Invoice ID", "left_anti")
    return {
        "Integration.Sale_Staging": staging,
        "Fact.Sale": kept.unionByName(staging.select(*fact.columns)),
    }
