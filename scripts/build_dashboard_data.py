"""
build_dashboard_data.py: write the data files the dashboard reads.

    dashboard/public/data/sample.json    a demo story with invented numbers, marked "sample": true
    dashboard/public/data/manifest.json  which files the dashboard offers, and which one opens first

The real results (real.json) come from the test bench instead:
    python scripts/test_bench_to_results.py --ref origin/claude/test-bench
real_results() below is the older hand-written version, kept for reference and no longer written.

Usage (from the repo root):
    python scripts/build_dashboard_data.py
    python scripts/check_results.py dashboard/public/data/*.json
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "public" / "data"
SAMPLES = ROOT / "scripts" / "dashboard_samples"


def read(path):
    # utf-8-sig drops the byte-order mark Microsoft's .sql files start with
    return (ROOT / path).read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Table layouts (column names in table order, as in the WideWorldImportersDW schema)
# ---------------------------------------------------------------------------

COLUMNS = {
    "Integration.Sale_Staging": [
        "Sale Staging Key", "City Key", "Customer Key", "Bill To Customer Key", "Stock Item Key",
        "Invoice Date Key", "Delivery Date Key", "Salesperson Key", "WWI Invoice ID", "Description",
        "Package", "Quantity", "Unit Price", "Tax Rate", "Total Excluding Tax", "Tax Amount", "Profit",
        "Total Including Tax", "Total Dry Items", "Total Chiller Items", "WWI City ID", "WWI Customer ID",
        "WWI Bill To Customer ID", "WWI Stock Item ID", "WWI Salesperson ID", "Last Modified When",
    ],
    "Fact.Sale": [
        "Sale Key", "City Key", "Customer Key", "Bill To Customer Key", "Stock Item Key",
        "Invoice Date Key", "Delivery Date Key", "Salesperson Key", "WWI Invoice ID", "Description",
        "Package", "Quantity", "Unit Price", "Tax Rate", "Total Excluding Tax", "Tax Amount", "Profit",
        "Total Including Tax", "Total Dry Items", "Total Chiller Items", "Lineage Key",
    ],
    "Integration.Lineage": [
        "Lineage Key", "Data Load Started", "Table Name", "Data Load Completed", "Was Successful",
        "Source System Cutoff Time",
    ],
    "Integration.ETL Cutoff": ["Table Name", "Cutoff Time"],
    "Dimension.City": [
        "City Key", "WWI City ID", "City", "State Province", "Country", "Continent", "Sales Territory",
        "Region", "Subregion", "Location", "Latest Recorded Population", "Valid From", "Valid To",
        "Lineage Key",
    ],
    "Dimension.Customer": [
        "Customer Key", "WWI Customer ID", "Customer", "Bill To Customer", "Category", "Buying Group",
        "Primary Contact", "Postal Code", "Valid From", "Valid To", "Lineage Key",
    ],
    "Dimension.Employee": [
        "Employee Key", "WWI Employee ID", "Employee", "Preferred Name", "Is Salesperson", "Photo",
        "Valid From", "Valid To", "Lineage Key",
    ],
    "Dimension.Stock Item": [
        "Stock Item Key", "WWI Stock Item ID", "Stock Item", "Color", "Selling Package", "Buying Package",
        "Brand", "Size", "Lead Time Days", "Quantity Per Outer", "Is Chiller Stock", "Barcode",
        "Tax Rate", "Unit Price", "Recommended Retail Price", "Typical Weight Per Unit", "Photo",
        "Valid From", "Valid To", "Lineage Key",
    ],
    "Integration.City_Staging": [
        "City Staging Key", "WWI City ID", "City", "State Province", "Country", "Continent",
        "Sales Territory", "Region", "Subregion", "Location", "Latest Recorded Population",
        "Valid From", "Valid To",
    ],
    "Fact.Movement": [
        "Movement Key", "Date Key", "Stock Item Key", "Customer Key", "Supplier Key",
        "Transaction Type Key", "WWI Stock Item Transaction ID", "WWI Invoice ID",
        "WWI Purchase Order ID", "Quantity", "Lineage Key",
    ],
    "Integration.Movement_Staging": [
        "Movement Staging Key", "Date Key", "Stock Item Key", "Customer Key", "Supplier Key",
        "Transaction Type Key", "WWI Stock Item Transaction ID", "WWI Invoice ID",
        "WWI Purchase Order ID", "Quantity", "WWI Stock Item ID", "WWI Customer ID", "WWI Supplier ID",
        "WWI Transaction Type ID", "Last Modifed When",
    ],
    "Dimension.Supplier": [
        "Supplier Key", "WWI Supplier ID", "Supplier", "Category", "Primary Contact",
        "Supplier Reference", "Payment Days", "Postal Code", "Valid From", "Valid To", "Lineage Key",
    ],
    "Dimension.Transaction Type": [
        "Transaction Type Key", "WWI Transaction Type ID", "Transaction Type", "Valid From", "Valid To",
        "Lineage Key",
    ],
}

# Columns that can never match, even between two runs of the legacy job itself.
# Each one needs a reason the dashboard can show.
IDENTITY_REASON = ("Identity key handed out by SQL Server. Identity numbers are not rolled back, "
                   "so two runs of the legacy job on the same input give different keys. "
                   "Every other column of these rows is still compared.")
CLOCK_REASON = ("Set to SYSDATETIME(), the clock time the job ran. "
                "It differs on every run, legacy or Spark.")

# Per job, because a column is only ignored where that job writes it: the Sale job never
# touches Dimension.City, so there every column of Dimension.City is compared.
IGNORED = {
    "sale": {
        "Fact.Sale": [{"column": "Sale Key", "reason": IDENTITY_REASON}],
        "Integration.Lineage": [{"column": "Data Load Completed", "reason": CLOCK_REASON}],
    },
    "city": {
        "Dimension.City": [{"column": "City Key", "reason": IDENTITY_REASON}],
        "Integration.Lineage": [{"column": "Data Load Completed", "reason": CLOCK_REASON}],
    },
    "movement": {
        "Fact.Movement": [{"column": "Movement Key", "reason": IDENTITY_REASON}],
        "Integration.Lineage": [{"column": "Data Load Completed", "reason": CLOCK_REASON}],
    },
}

# Columns diff() uses to pair rows when explaining a FAIL. None = no stable key once the
# identity column is ignored, so a FAIL is explained with whole rows only.
KEYS = {
    "Integration.Sale_Staging": ["Sale Staging Key"],
    "Fact.Sale": None,
    "Integration.Lineage": ["Lineage Key"],
    "Integration.ETL Cutoff": ["Table Name"],
    "Dimension.City": None,
    "Dimension.Customer": ["Customer Key"],
    "Dimension.Employee": ["Employee Key"],
    "Dimension.Stock Item": ["Stock Item Key"],
    "Integration.City_Staging": ["City Staging Key"],
    "Fact.Movement": ["WWI Stock Item Transaction ID"],
    "Integration.Movement_Staging": ["Movement Staging Key"],
    "Dimension.Supplier": ["Supplier Key"],
    "Dimension.Transaction Type": ["Transaction Type Key"],
}

# Real row counts of the Sale snapshot (DEVLOG, 31 Oct). Counts were identical before and after.
SALE_ROWS = {
    "Dimension.City": 116295,
    "Dimension.Customer": 403,
    "Dimension.Employee": 213,
    "Dimension.Stock Item": 672,
    "Fact.Sale": 228265,
    "Integration.ETL Cutoff": 14,
    "Integration.Lineage": 15,
    "Integration.Sale_Staging": 5224,
}
SALE_TABLES = [
    "Integration.Sale_Staging", "Fact.Sale", "Integration.Lineage", "Integration.ETL Cutoff",
    "Dimension.City", "Dimension.Customer", "Dimension.Employee", "Dimension.Stock Item",
]


def ignored_for(job, table):
    return IGNORED[job].get(table, [])


def compared_cols(job, table):
    """reconcile() compares the shared columns minus the ignored ones, sorted by name."""
    ignored = {i["column"] for i in ignored_for(job, table)}
    return sorted(set(COLUMNS[table]) - ignored)


def reconcile_result(job, table, only_a=(), only_b=(), explanation=None):
    """Same keys reconcile() returns. Lists hold at most a few examples (see "counts")."""
    only_a, only_b = list(only_a), list(only_b)
    passed = not only_a and not only_b
    return {
        "status": "pass" if passed else "fail",
        "compared_cols": compared_cols(job, table),
        "only_a": only_a,
        "only_b": only_b,
        "cols_only_a": [],
        "cols_only_b": [],
        "explanation": explanation,
    }


def table_entry(job, table, rows_legacy, rows_spark, result, counts=None):
    entry = {
        "table": table,
        "key_cols": KEYS[table],
        "ignored": ignored_for(job, table),
        "rows_legacy": rows_legacy,
        "rows_spark": rows_spark,
        "result": result,
    }
    if counts:
        entry["counts"] = counts
    return entry


def passing(job, table, rows):
    return table_entry(job, table, rows, rows, reconcile_result(job, table))


def not_compared(job, table, rows_legacy=None):
    return table_entry(job, table, rows_legacy, None, None)


def lineage_entry(table, column, sources, rule):
    return {"table": table, "column": column, "sources": sources, "rule": rule}


def window_lookup(dim, key, wwi_id):
    return (f"Looks up {dim} by {wwi_id}, picking the version that was valid when the sale "
            f"was last modified (earliest Valid From wins). No match gives 0, meaning 'unknown'. "
            f"Key column: {key}.")


# Hand-derived from legacy_jobs/wwi/MigrateStagedSaleData.sql. The planned lineage step
# should generate this; until then it is written out here, and labelled as such in the UI.
SALE_LINEAGE = [
    lineage_entry("Integration.Sale_Staging", "City Key",
                  ["Dimension.City.City Key", "Integration.Sale_Staging.WWI City ID",
                   "Integration.Sale_Staging.Last Modified When"],
                  window_lookup("Dimension.City", "City Key", "WWI City ID")),
    lineage_entry("Integration.Sale_Staging", "Customer Key",
                  ["Dimension.Customer.Customer Key", "Integration.Sale_Staging.WWI Customer ID",
                   "Integration.Sale_Staging.Last Modified When"],
                  window_lookup("Dimension.Customer", "Customer Key", "WWI Customer ID")),
    lineage_entry("Integration.Sale_Staging", "Bill To Customer Key",
                  ["Dimension.Customer.Customer Key", "Integration.Sale_Staging.WWI Bill To Customer ID",
                   "Integration.Sale_Staging.Last Modified When"],
                  window_lookup("Dimension.Customer", "Customer Key", "WWI Bill To Customer ID")),
    lineage_entry("Integration.Sale_Staging", "Stock Item Key",
                  ["Dimension.Stock Item.Stock Item Key", "Integration.Sale_Staging.WWI Stock Item ID",
                   "Integration.Sale_Staging.Last Modified When"],
                  window_lookup("Dimension.Stock Item", "Stock Item Key", "WWI Stock Item ID")),
    lineage_entry("Integration.Sale_Staging", "Salesperson Key",
                  ["Dimension.Employee.Employee Key", "Integration.Sale_Staging.WWI Salesperson ID",
                   "Integration.Sale_Staging.Last Modified When"],
                  window_lookup("Dimension.Employee", "Employee Key", "WWI Salesperson ID")),
    lineage_entry("Fact.Sale", "Sale Key", [],
                  "New identity number from SQL Server for each inserted row."),
    lineage_entry("Fact.Sale", "City Key, Customer Key, Bill To Customer Key, Stock Item Key, Salesperson Key",
                  ["Integration.Sale_Staging (same columns, after the lookups above)"],
                  "Copied from staging after the key lookups. Rows for every staged invoice are "
                  "deleted first, then reinserted."),
    lineage_entry("Fact.Sale", "Invoice Date Key ... Total Chiller Items (14 columns)",
                  ["Integration.Sale_Staging (same columns)"],
                  "Copied straight from staging."),
    lineage_entry("Fact.Sale", "Lineage Key",
                  ["Integration.Lineage.Lineage Key"],
                  "The newest Lineage row for 'Sale' that has no Data Load Completed yet."),
    lineage_entry("Integration.Lineage", "Data Load Completed", [],
                  "SYSDATETIME() on that one lineage row: the clock time the job finished."),
    lineage_entry("Integration.Lineage", "Was Successful", [], "Set to 1 on that one lineage row."),
    lineage_entry("Integration.ETL Cutoff", "Cutoff Time",
                  ["Integration.Lineage.Source System Cutoff Time"],
                  "Copied from the lineage row, on the 'Sale' row only."),
]


# ---------------------------------------------------------------------------
# real.json: only what has really been run
# ---------------------------------------------------------------------------

REAL_NOTES = [
    "Integration.Sale_Staging: the PySpark translation in jobs_pyspark/sale.py matched the legacy "
    "output on all 5,224 rows and 26 columns (owner's Mac, Oct 2026).",
    "The other seven Sale tables, and the City and Movement jobs, have not been compared yet.",
    "No holdout data exists yet, so nothing is verified on data the AI never saw.",
    "Timings, attempt start times and Spark row counts for the uncompared tables were not recorded.",
]


def real_results():
    sale_tables = [passing("sale", "Integration.Sale_Staging", 5224)]
    sale_tables += [not_compared("sale", t, SALE_ROWS[t]) for t in SALE_TABLES[1:]]
    sale = {
        "id": "sale",
        "name": "Sale",
        "proc": "Integration.MigrateStagedSaleData",
        "source_file": "legacy_jobs/wwi/MigrateStagedSaleData.sql",
        "summary": "Looks up five dimension keys for each staged sale line, then replaces "
                   "those invoices in Fact.Sale and closes the load in the lineage log.",
        "status": "in_progress",
        "max_attempts": None,
        "legacy_sql": read("legacy_jobs/wwi/MigrateStagedSaleData.sql"),
        "attempts": [{
            "number": 1,
            "started_at": None,
            "seconds": None,
            "code": read("jobs_pyspark/sale.py"),
            "error": None,
            "error_stage": None,
            "feedback": None,
            "runs": {"dev": {"tables": sale_tables}, "holdout": None},
        }],
        "lineage": SALE_LINEAGE,
    }
    city = not_started_job("city", "City", "Integration.MigrateStagedCityData",
                           "legacy_jobs/wwi/MigrateStagedCityData.sql",
                           "Closes off the current version of each changed city and inserts the "
                           "new versions, keeping the full history.")
    movement = not_started_job("movement", "Movement", "Integration.MigrateStagedMovementData",
                               "legacy_jobs/wwi/MigrateStagedMovementData.sql",
                               "Looks up four dimension keys, then MERGEs stock movements into "
                               "Fact.Movement: update the ones that exist, insert the rest.")
    return {
        "contract_version": 1,
        "sample": False,
        "generated_at": "2026-11-04T21:00:00Z",
        "title": "Real runs so far",
        "notes": REAL_NOTES,
        "datasets": DATASETS,
        "jobs": [sale, city, movement],
    }


def not_started_job(job_id, name, proc, source, summary):
    return {
        "id": job_id, "name": name, "proc": proc, "source_file": source, "summary": summary,
        "status": "not_started", "max_attempts": None, "legacy_sql": read(source), "attempts": [],
    }


DATASETS = {
    "dev": {
        "label": "Dev data",
        "ai_can_see": True,
        "description": "The data the AI may learn from. When an attempt fails here, a summary of "
                       "the differences goes back to the AI for the next attempt.",
    },
    "holdout": {
        "label": "Holdout data",
        "ai_can_see": False,
        "description": "A different slice of data the AI never sees: not in prompts, not in error "
                       "feedback, not in the folder the AI runs in. Only checked once an attempt "
                       "passes on dev data.",
    },
}


# ---------------------------------------------------------------------------
# sample.json: the demo story. Everything here except the Sale row counts is invented.
# ---------------------------------------------------------------------------

rng = random.Random(20261113)  # fixed seed, so the file only changes when this script does

STOCK_ITEMS = [  # (WWI Stock Item ID, description, package, unit price, tax rate, chiller?)
    (220, "Chocolate frogs 250g", "Bag", "4.10", "15.000", True),
    (164, "USB food flash drive - chocolate bar", "Each", "32.00", "15.000", False),
    (100, "Developer joke mug - that's a hardware problem (Black)", "Each", "13.00", "15.000", False),
    (85, "DBA joke mug - mind if I join you? (White)", "Each", "13.00", "15.000", False),
    (195, "Halloween zombie mask (Light Brown) L", "Each", "18.00", "15.000", False),
    (174, "Black and orange fragile despatch tape 48mm x 75m", "Each", "3.70", "15.000", False),
    (205, "Ride on vintage American toy coupe (Red) 1/12 scale", "Each", "285.00", "15.000", False),
    (210, "Shipping carton (Brown) 500x310x310mm", "Each", "2.74", "15.000", False),
    (225, "White chocolate snow balls 250g", "Bag", "4.10", "15.000", True),
    (36, "Furry gorilla with big eyes slippers (Black) S", "Each", "32.00", "15.000", False),
]


def money(x):
    return f"{x:.2f}"


def sale_line(staging_key, invoice_id, day, city_key, wwi_city):
    """One plausible Integration.Sale_Staging row, as a dict."""
    item_id, desc, package, price, tax, chiller = rng.choice(STOCK_ITEMS)
    qty = rng.choice([1, 2, 3, 5, 9, 10, 24, 60, 72, 108])
    excl = float(price) * qty
    tax_amt = round(excl * 0.15, 2)
    customer = rng.randint(1, 1061)
    salesperson = rng.choice([2, 3, 6, 7, 8, 13, 14, 15, 16, 20])
    return {
        "Sale Staging Key": staging_key,
        "City Key": city_key,
        "Customer Key": rng.randint(1, 402),
        "Bill To Customer Key": 1 if customer < 400 else 202,
        "Stock Item Key": item_id + rng.choice([0, 0, 227, 454]) if item_id < 200 else item_id,
        "Invoice Date Key": f"2016-05-{day:02d}",
        "Delivery Date Key": f"2016-05-{min(day + 1, 31):02d}",
        "Salesperson Key": rng.randint(1, 213),
        "WWI Invoice ID": invoice_id,
        "Description": desc,
        "Package": package,
        "Quantity": qty,
        "Unit Price": price,
        "Tax Rate": tax,
        "Total Excluding Tax": money(excl),
        "Tax Amount": money(tax_amt),
        "Profit": money(excl * rng.choice([0.25, 0.4, 0.5])),
        "Total Including Tax": money(excl + tax_amt),
        "Total Dry Items": 0 if chiller else qty,
        "Total Chiller Items": qty if chiller else 0,
        "WWI City ID": wwi_city,
        "WWI Customer ID": customer,
        "WWI Bill To Customer ID": 1 if customer < 400 else 401,
        "WWI Stock Item ID": item_id,
        "WWI Salesperson ID": salesperson,
        "Last Modified When": f"2016-05-{day:02d} 12:00:00",
    }


def as_tuple(job, row, table):
    """A whole row in reconcile()'s format: values in compared_cols order."""
    return [row[c] for c in compared_cols(job, table)]


def fact_row(staging_row):
    row = {c: staging_row.get(c) for c in COLUMNS["Fact.Sale"]}
    row["Lineage Key"] = 14
    return row


def sale_attempt2_runs():
    """Attempt 2 'optimised' the city lookup to current versions only, so sales made before a
    city's latest change found no match and got City Key 0. Counts are invented."""
    wrong_rows = 1190
    examples = []
    used = set()
    while len(examples) < 8:
        key = rng.randint(1, 5224)
        if key in used:
            continue
        used.add(key)
        day = rng.randint(6, 31)
        invoice = 67700 + rng.randint(0, 1603)
        wwi_city = rng.randint(1, 38186)
        right_key = rng.randint(1, 116295)
        examples.append(sale_line(key, invoice, day, right_key, wwi_city))
    examples.sort(key=lambda r: r["Sale Staging Key"])

    t = "Integration.Sale_Staging"
    legacy = [as_tuple("sale", r, t) for r in examples]
    spark = [as_tuple("sale", dict(r, **{"City Key": 0}), t) for r in examples]
    changed = [{"key": [r["Sale Staging Key"]], "col": "City Key", "a": r["City Key"], "b": 0}
               for r in examples]
    staging = table_entry("sale", t, 5224, 5224, reconcile_result("sale", t, legacy, spark, {
        "cols_only_a": [], "cols_only_b": [], "rows_only_a": [], "rows_only_b": [],
        "changed": changed, "dupes_a": [], "dupes_b": [],
    }), counts={"only_a": wrong_rows, "only_b": wrong_rows, "changed": wrong_rows})

    f = "Fact.Sale"
    fact_legacy = [as_tuple("sale", fact_row(r), f) for r in examples[:6]]
    fact_spark = [as_tuple("sale", dict(fact_row(r), **{"City Key": 0}), f) for r in examples[:6]]
    fact = table_entry("sale", f, 228265, 228265, reconcile_result("sale", f, fact_legacy, fact_spark),
                       counts={"only_a": wrong_rows, "only_b": wrong_rows})

    tables = [staging, fact] + [passing("sale", x, SALE_ROWS[x]) for x in SALE_TABLES[2:]]
    return {"dev": {"tables": tables, "seconds": 74.8}, "holdout": None}


SALE_HOLDOUT_ROWS = {  # invented: a different month of staged sales
    "Dimension.City": 116295, "Dimension.Customer": 403, "Dimension.Employee": 213,
    "Dimension.Stock Item": 672, "Fact.Sale": 228265, "Integration.ETL Cutoff": 14,
    "Integration.Lineage": 15, "Integration.Sale_Staging": 4987,
}

SALE_ATTEMPT1_ERROR = """Traceback (most recent call last):
  File "migrator/run_spark.py", line 104, in main
    changed = run(spark, dict(tables))
  File "jobs_pyspark/sale.py", line 9, in run
    spark.sql(\"\"\"
pyspark.errors.exceptions.captured.AnalysisException: [UNSUPPORTED_FEATURE.TABLE_OPERATION] The feature is not supported: Table `Integration_Sale_Staging` does not support UPDATE TABLE. Please check the current catalog and namespace to make sure the qualified table name is expected, and also check the catalog implementation which is configured by "spark.sql.catalog". SQLSTATE: 0A000"""


def sale_attempt2_code():
    """jobs_pyspark/sale.py with one planted 'optimisation' that breaks history lookups."""
    code = read("jobs_pyspark/sale.py")
    old = '    s = lookup(s, city, "WWI City ID", "City Key", "WWI City ID", "City Key")\n'
    new = ('    # Dimension.City is large, so only look at current city versions\n'
           '    current_city = city.filter(F.col("Valid To") == F.lit("9999-12-31 23:59:59.9999999").cast("timestamp"))\n'
           '    s = lookup(s, current_city, "WWI City ID", "City Key", "WWI City ID", "City Key")\n')
    assert old in code, "jobs_pyspark/sale.py changed: update sale_attempt2_code()"
    return code.replace(old, new)


def sample_sale():
    att2 = sale_attempt2_runs()
    ex = att2["dev"]["tables"][0]["result"]["explanation"]["changed"][:3]
    examples = "\n".join(f"  Sale Staging Key {c['key'][0]}: expected City Key {c['a']}, got {c['b']}"
                         for c in ex)
    return {
        "id": "sale",
        "name": "Sale",
        "proc": "Integration.MigrateStagedSaleData",
        "source_file": "legacy_jobs/wwi/MigrateStagedSaleData.sql",
        "summary": "Looks up five dimension keys for each staged sale line, then replaces "
                   "those invoices in Fact.Sale and closes the load in the lineage log.",
        "status": "verified",
        "max_attempts": 4,
        "legacy_sql": read("legacy_jobs/wwi/MigrateStagedSaleData.sql"),
        "attempts": [
            {
                "number": 1, "started_at": "2026-11-08T09:14:02Z", "seconds": 52.3,
                "code": (SAMPLES / "sale_attempt1.py").read_text(),
                "error": SALE_ATTEMPT1_ERROR, "error_stage": "running the job",
                "feedback": "Attempt 1 crashed while running the job:\n"
                            "AnalysisException: Table `Integration_Sale_Staging` does not support UPDATE TABLE.\n"
                            "Spark DataFrames have no UPDATE. Rebuild the table with joins instead.",
                "runs": {"dev": None, "holdout": None},
            },
            {
                "number": 2, "started_at": "2026-11-08T09:15:31Z", "seconds": 131.6,
                "code": sale_attempt2_code(),
                "error": None, "error_stage": None,
                "feedback": "Attempt 2 ran, but 2 of 8 tables differ from the legacy output on dev data.\n"
                            "Integration.Sale_Staging: 1,190 rows differ, all in column City Key.\n"
                            + examples + "\n"
                            "Fact.Sale: 1,190 rows differ (the same sale lines, inserted from staging).",
                "runs": att2,
            },
            {
                "number": 3, "started_at": "2026-11-08T09:18:20Z", "seconds": 214.9,
                "code": read("jobs_pyspark/sale.py"),
                "error": None, "error_stage": None, "feedback": None,
                "runs": {
                    "dev": {"seconds": 71.2,
                            "tables": [passing("sale", t, SALE_ROWS[t]) for t in SALE_TABLES]},
                    "holdout": {"seconds": 69.5,
                                "tables": [passing("sale", t, SALE_HOLDOUT_ROWS[t]) for t in SALE_TABLES]},
                },
            },
        ],
        "lineage": SALE_LINEAGE,
    }


CITY_TABLES = ["Dimension.City", "Integration.City_Staging", "Integration.Lineage", "Integration.ETL Cutoff"]
CITY_DEV = {"Dimension.City": 116412, "Integration.City_Staging": 117,
            "Integration.Lineage": 15, "Integration.ETL Cutoff": 14}
CITY_HOLDOUT = {"Dimension.City": 116389, "Integration.City_Staging": 94,
                "Integration.Lineage": 15, "Integration.ETL Cutoff": 14}

CITY_NAMES = [("Abbeville", "Louisiana", 12257), ("Beaver Creek", "Minnesota", 297),
              ("Cuyamungue", "New Mexico", 479), ("Ganado", "Texas", 2003),
              ("Lake Arthur", "Louisiana", 2738), ("Sylvanite", "Montana", 103)]


def city_row(wwi_id, name, state, pop, valid_from, valid_to):
    return {
        "WWI City ID": wwi_id, "City": name, "State Province": state, "Country": "United States",
        "Continent": "North America", "Sales Territory": "Southeast", "Region": "Americas",
        "Subregion": "Northern America", "Location": "POINT (-92.13 29.97)",
        "Latest Recorded Population": pop, "Valid From": valid_from, "Valid To": valid_to,
        "Lineage Key": 9,
    }


def city_attempt1_runs():
    """Attempt 1 closed off every history row of a changed city, not only the open one."""
    t = "Dimension.City"
    legacy, spark = [], []
    for i, (name, state, pop) in enumerate(CITY_NAMES):
        wwi_id = 1000 + i * 3127
        row = city_row(wwi_id, name, state, pop - 40, "2013-01-01 00:00:00", "2015-07-01 16:00:00")
        legacy.append(as_tuple("city", row, t))
        spark.append(as_tuple("city", dict(row, **{"Valid To": "2016-05-31 16:00:00"}), t))
    entry = table_entry("city", t, CITY_DEV[t], CITY_DEV[t], reconcile_result("city", t, legacy, spark),
                        counts={"only_a": 63, "only_b": 63})
    tables = [entry] + [passing("city", x, CITY_DEV[x]) for x in CITY_TABLES[1:]]
    return {"dev": {"tables": tables, "seconds": 58.0}, "holdout": None}


def sample_city():
    return {
        "id": "city", "name": "City", "proc": "Integration.MigrateStagedCityData",
        "source_file": "legacy_jobs/wwi/MigrateStagedCityData.sql",
        "summary": "Closes off the current version of each changed city and inserts the new "
                   "versions, keeping the full history.",
        "status": "verified", "max_attempts": 4,
        "legacy_sql": read("legacy_jobs/wwi/MigrateStagedCityData.sql"),
        "attempts": [
            {
                "number": 1, "started_at": "2026-11-08T10:02:44Z", "seconds": 97.4,
                "code": (SAMPLES / "city_attempt1.py").read_text(),
                "error": None, "error_stage": None,
                "feedback": "Attempt 1 ran, but 1 of 4 tables differs from the legacy output on dev data.\n"
                            "Dimension.City: 63 rows have no exact match on either side.\n"
                            "Example: WWI City ID 1000 (Abbeville), Valid From 2013-01-01: expected "
                            "Valid To 2015-07-01 16:00:00, got 2016-05-31 16:00:00.",
                "runs": city_attempt1_runs(),
            },
            {
                "number": 2, "started_at": "2026-11-08T10:04:39Z", "seconds": 176.1,
                "code": (SAMPLES / "city_attempt2.py").read_text(),
                "error": None, "error_stage": None, "feedback": None,
                "runs": {
                    "dev": {"seconds": 57.1, "tables": [passing("city", t, CITY_DEV[t]) for t in CITY_TABLES]},
                    "holdout": {"seconds": 55.8,
                                "tables": [passing("city", t, CITY_HOLDOUT[t]) for t in CITY_TABLES]},
                },
            },
        ],
    }


MOVE_TABLES = ["Fact.Movement", "Integration.Movement_Staging", "Integration.Lineage",
               "Integration.ETL Cutoff", "Dimension.Stock Item", "Dimension.Customer",
               "Dimension.Supplier", "Dimension.Transaction Type"]
MOVE_DEV = {"Fact.Movement": 237891, "Integration.Movement_Staging": 1842, "Integration.Lineage": 15,
            "Integration.ETL Cutoff": 14, "Dimension.Stock Item": 672, "Dimension.Customer": 403,
            "Dimension.Supplier": 28, "Dimension.Transaction Type": 15}
MOVE_HOLDOUT = dict(MOVE_DEV, **{"Fact.Movement": 237406, "Integration.Movement_Staging": 1357})

MOVE_ATTEMPT1_ERROR = """Traceback (most recent call last):
  File "migrator/run_spark.py", line 104, in main
    changed = run(spark, dict(tables))
  File "jobs_pyspark/movement.py", line 15, in run
    spark.sql(f\"\"\"
pyspark.errors.exceptions.captured.AnalysisException: [UNSUPPORTED_FEATURE.TABLE_OPERATION] The feature is not supported: Table `Fact_Movement` does not support MERGE INTO TABLE. Please check the current catalog and namespace to make sure the qualified table name is expected, and also check the catalog implementation which is configured by "spark.sql.catalog". SQLSTATE: 0A000"""


def movement_holdout_runs():
    """Holdout re-stages movements that already exist in Fact.Movement, so the MERGE's
    'WHEN MATCHED' branch runs. Attempt 2 forgot to set Lineage Key there."""
    t = "Fact.Movement"
    changed, legacy, spark = [], [], []
    for i in range(6):
        txn = 236120 + i * 211 + rng.randint(0, 40)
        row = {"Date Key": f"2016-05-{10 + i:02d}", "Stock Item Key": rng.randint(1, 672),
               "Customer Key": rng.choice([0, 0, rng.randint(1, 402)]), "Supplier Key": 0,
               "Transaction Type Key": 10, "WWI Stock Item Transaction ID": txn,
               "WWI Invoice ID": 67810 + i * 37, "WWI Purchase Order ID": None,
               "Quantity": -rng.choice([1, 5, 10, 24, 60]), "Lineage Key": 14}
        legacy.append(as_tuple("movement", row, t))
        spark.append(as_tuple("movement", dict(row, **{"Lineage Key": 9}), t))
        changed.append({"key": [txn], "col": "Lineage Key", "a": 14, "b": 9})
    entry = table_entry("movement", t, MOVE_HOLDOUT[t], MOVE_HOLDOUT[t], reconcile_result("movement", t, legacy, spark, {
        "cols_only_a": [], "cols_only_b": [], "rows_only_a": [], "rows_only_b": [],
        "changed": changed, "dupes_a": [], "dupes_b": [],
    }), counts={"only_a": 37, "only_b": 37, "changed": 37})
    tables = [entry] + [passing("movement", x, MOVE_HOLDOUT[x]) for x in MOVE_TABLES[1:]]
    return {"seconds": 88.3, "tables": tables}


def sample_movement():
    return {
        "id": "movement", "name": "Movement", "proc": "Integration.MigrateStagedMovementData",
        "source_file": "legacy_jobs/wwi/MigrateStagedMovementData.sql",
        "summary": "Looks up four dimension keys, then MERGEs stock movements into Fact.Movement: "
                   "update the ones that exist, insert the rest.",
        "status": "failed", "max_attempts": 4,
        "stop_reason": "Passed on dev data but failed on holdout data. Holdout differences are "
                       "never sent to the AI, so the loop stops here and a person takes over.",
        "legacy_sql": read("legacy_jobs/wwi/MigrateStagedMovementData.sql"),
        "attempts": [
            {
                "number": 1, "started_at": "2026-11-08T11:20:05Z", "seconds": 47.9,
                "code": (SAMPLES / "movement_attempt1.py").read_text(),
                "error": MOVE_ATTEMPT1_ERROR, "error_stage": "running the job",
                "feedback": "Attempt 1 crashed while running the job:\n"
                            "AnalysisException: Table `Fact_Movement` does not support MERGE INTO TABLE.\n"
                            "Spark DataFrames have no MERGE. Rebuild the table with joins instead.",
                "runs": {"dev": None, "holdout": None},
            },
            {
                "number": 2, "started_at": "2026-11-08T11:21:12Z", "seconds": 263.0,
                "code": (SAMPLES / "movement_attempt2.py").read_text(),
                "error": None, "error_stage": None, "feedback": None,
                "runs": {
                    "dev": {"seconds": 91.6, "tables": [passing("movement", t, MOVE_DEV[t]) for t in MOVE_TABLES]},
                    "holdout": movement_holdout_runs(),
                },
            },
        ],
    }


def sample_results():
    return {
        "contract_version": 1,
        "sample": True,
        "generated_at": "2026-11-08T11:26:40Z",
        "title": "Demo story",
        "notes": [
            "Invented for the demo. Only the Sale snapshot row counts and the legacy SQL are real.",
            "Attempt timelines, mismatches, timings, the holdout slice and every City and Movement "
            "number are made up to show what the dashboard will display.",
        ],
        "datasets": DATASETS,
        "jobs": [sample_sale(), sample_city(), sample_movement()],
    }


def write(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write("sample.json", sample_results())
    write("manifest.json", {
        "default": "real",
        "files": [
            {"id": "real", "label": "Real runs (test bench)", "path": "real.json"},
            {"id": "sample", "label": "Demo story (sample)", "path": "sample.json"},
        ],
    })
