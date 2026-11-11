def run(spark, tables):
    result = {}
    for name in tables:
        result[name] = spark.read.parquet("snapshots/sale/after/" + name + ".parquet")
    return result


