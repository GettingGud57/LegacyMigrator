# Sample attempt code for the dashboard demo

These files are **invented** PySpark attempts used only by `scripts/build_dashboard_data.py`
to build `dashboard/public/data/sample.json`, the demo story the dashboard shows behind a
"Sample data" banner.

They are not translations produced by the tool, they are never run by the pipeline, and
they must never be copied into `jobs_pyspark/`. The one real translation in the sample
story (Sale, attempt 3) is read straight from `jobs_pyspark/sale.py`.

Each file plants the kind of mistake the real loop is meant to catch:

| File | Planted mistake |
|---|---|
| sale_attempt1.py | Copies the T-SQL `UPDATE ... FROM` into `spark.sql`, which Spark rejects |
| (built from jobs_pyspark/sale.py) sale attempt 2 | "Optimises" the city lookup to current rows only, so old sales get city 0 |
| city_attempt1.py | Closes off every history row of a city, not only the open one |
| city_attempt2.py | Fixed version |
| movement_attempt1.py | Uses `MERGE INTO` in `spark.sql`, which Spark rejects on plain DataFrames |
| movement_attempt2.py | Matched rows keep their old `Lineage Key`; dev data never hits that branch |
