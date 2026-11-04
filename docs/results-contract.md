# The results file (contract version 1)

The dashboard reads one JSON file per pipeline run.
`loop.py` (hand-written, not built yet) will write it.
This page says exactly what goes in it.

The short version: for every job, store each attempt's code and error, and for every table store what `diff.reconcile()` already returns.
Almost everything else is a name or a number you already have.

## Why it looks like this

- **It stores evidence, not conclusions.** A table's verdict is `result.status` straight from `reconcile()`. The dashboard works out each attempt's outcome from the tables, and it checks the job's `status` against that evidence. If a job says `"verified"` but its last attempt didn't pass every table on dev and holdout, the dashboard shows a warning and refuses to show it as verified. `scripts/check_results.py` applies the same rule.
- **`reconcile()` output goes in unchanged**, except that long lists are cut to a few examples (see "Cutting long lists"). No renaming, no reshaping, so there's nothing to get wrong.
- **One file, plain `json.dump`.** No database, no server. The dashboard is a static website, so it can be hosted anywhere or opened from a laptop at the venue with no internet.
- **Real and sample data can never be confused.** Every file says `"sample": true` or `false`. The dashboard shows a "Sample data" banner whenever it's `true`.

## Top level

| Field | Type | What it is |
|---|---|---|
| `contract_version` | int | Always `1` for this version. |
| `sample` | bool | `true` if any number in the file is invented. The UI shows a banner. |
| `generated_at` | string | When the file was written, ISO 8601 UTC, e.g. `"2026-11-08T11:26:40Z"`. |
| `title` | string | Optional. Short name for the run, shown in the header. |
| `notes` | list of strings | Optional. Shown under the banner. Use it to say what's real and what isn't. |
| `datasets` | object | `{"dev": Dataset, "holdout": Dataset}`, see below. |
| `jobs` | list of Job | One per legacy job. |

**Dataset:** `{"label": "Dev data", "ai_can_see": true, "description": "..."}`.
`ai_can_see` must be `false` for holdout.

## Job

| Field | Type | What it is |
|---|---|---|
| `id` | string | Short, used in links: `#/job/sale`. Must be unique. |
| `name` | string | Shown big, e.g. `"Sale"`. |
| `proc` | string | The legacy procedure, e.g. `"Integration.MigrateStagedSaleData"`. |
| `source_file` | string | Path of the `.sql` file in the repo. |
| `summary` | string | One plain sentence: what the job does. |
| `status` | string | One of `verified`, `failed`, `retrying`, `in_progress`, `not_started`. |
| `stop_reason` | string or null | Optional. Why the loop stopped, in plain words. |
| `max_attempts` | int or null | The loop's attempt limit. |
| `legacy_sql` | string | The whole `.sql` file, as text. |
| `attempts` | list of Attempt | In order. Empty if not started. |
| `lineage` | list of Lineage | Optional. Where each output column comes from. |

What each `status` means:

| Status | When to use it |
|---|---|
| `verified` | The latest attempt passed every table on dev **and** holdout data. |
| `failed` | The loop gave up: out of attempts, or it failed on holdout (holdout diffs never go back to the AI, so nothing can be retried). |
| `retrying` | An attempt failed on dev data and another one is coming. |
| `in_progress` | Checks are still running, or not every table has been compared yet. |
| `not_started` | No attempts yet. |

## Attempt

| Field | Type | What it is |
|---|---|---|
| `number` | int | 1, 2, 3... in order. |
| `started_at` | string or null | ISO 8601 UTC. |
| `seconds` | number or null | Wall time for the whole attempt: translate + run + compare. |
| `code` | string | The PySpark file this attempt produced, as text. |
| `error` | string or null | The traceback if it crashed, else `null`. |
| `error_stage` | string or null | Where it crashed, e.g. `run_spark.py`'s `"running the job"`. |
| `feedback` | string or null | Exactly what was sent back to the AI after this attempt. Must only describe dev data. `null` if nothing was sent. |
| `runs` | object | `{"dev": Run or null, "holdout": Run or null}`. `null` means that dataset wasn't run. A crashed attempt has both `null`. |

Showing `feedback` word for word is deliberate: anyone can check the AI was never told anything about holdout data.

## Run

| Field | Type | What it is |
|---|---|---|
| `tables` | list of TableResult | One per table the job touches, including tables it should leave alone. |
| `seconds` | number | Optional. Time to run Spark and compare. |

Include the tables the job shouldn't change too (e.g. the `Dimension.*` tables for Sale).
They're cheap to compare and prove the job didn't touch them.

## TableResult

| Field | Type | What it is |
|---|---|---|
| `table` | string | Same name as the snapshot file, e.g. `"Integration.Sale_Staging"`. |
| `key_cols` | list or null | The `key_cols` you passed to `reconcile()`. `null` if the table has no stable key. |
| `ignored` | list | `[{"column": "Sale Key", "reason": "..."}]`. Every ignored column needs a reason. Empty list if none. |
| `rows_legacy` | int or null | Rows in the legacy `after/` table (the answer key). |
| `rows_spark` | int or null | Rows in the `spark/` table. |
| `result` | object or null | What `reconcile(after_rows, spark_rows, key_cols, ignore_cols)` returned. `null` = not compared yet. |
| `counts` | object | Optional. Full list sizes before cutting: `{"only_a": 1190, "only_b": 1190, "changed": 1190}`. |
| `extra_checks` | list | Optional. Stricter checks on top of `reconcile()`: `[{"name": "unique_key", "status": "pass", "detail": "plain sentence"}]`. The table only passes if `result.status` and every extra check pass. |

A is always the legacy `after/` output and B is always the Spark output.
Pass them to `reconcile()` in that order.

`result` has the keys `reconcile()` returns:

| Key | What it is |
|---|---|
| `status` | `"pass"` or `"fail"`. **This is the verdict.** |
| `compared_cols` | Every column that was compared, sorted. The values in `only_a`/`only_b` are in this order. |
| `only_a`, `only_b` | Whole rows (lists of values) with no identical twin on the other side. |
| `cols_only_a`, `cols_only_b` | Columns one side has and the other doesn't. |
| `explanation` | `null` on PASS. On FAIL with `key_cols`, what `diff()` returned: `rows_only_a`, `rows_only_b` (keys), `changed` (`[{"key": [...], "col": "...", "a": old, "b": new}]`), `dupes_a`, `dupes_b`, `cols_only_a`, `cols_only_b`. |

## Lineage (optional)

`{"table": "Fact.Sale", "column": "Lineage Key", "sources": ["Integration.Lineage.Lineage Key"], "rule": "plain sentence"}`.
The planned lineage step will produce this.
Until then the dashboard labels it "derived by hand from the SQL".

## Writing it from Python

`reconcile()` returns tuples, `Decimal`s and `datetime`s.
`json.dump` turns tuples into lists by itself, and `default=str` turns the other two into text, which keeps every digit (`Decimal("12.50")` becomes `"12.50"`):

```python
with open("dashboard/public/data/results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
```

### Cutting long lists

A FAIL on `Fact.Sale` can have 200,000 rows in `only_a`.
Keep the first few as examples, and record the full sizes in `counts`, before cutting:

```python
counts = {"only_a": len(result["only_a"]), "only_b": len(result["only_b"])}
result["only_a"] = result["only_a"][:20]
result["only_b"] = result["only_b"][:20]
if result["explanation"]:
    counts["changed"] = len(result["explanation"]["changed"])
    result["explanation"]["changed"] = result["explanation"]["changed"][:50]
```

The dashboard says "showing 20 of 1,190" when `counts` is bigger than the list.

### Then check it

```
python scripts/check_results.py dashboard/public/data/results.json
```

It prints `OK` or a list of problems, and refuses a `"verified"` the evidence doesn't support.

## Example

Trimmed from `dashboard/public/data/real.json` (the code and SQL strings are shortened here).
This is a real result: the Sale translation matched `Integration.Sale_Staging` exactly.

```json
{
  "contract_version": 1,
  "sample": false,
  "generated_at": "2026-11-04T21:00:00Z",
  "title": "Real runs so far",
  "notes": ["The other seven Sale tables, and the City and Movement jobs, have not been compared yet."],
  "datasets": {
    "dev": {"label": "Dev data", "ai_can_see": true, "description": "..."},
    "holdout": {"label": "Holdout data", "ai_can_see": false, "description": "..."}
  },
  "jobs": [
    {
      "id": "sale",
      "name": "Sale",
      "proc": "Integration.MigrateStagedSaleData",
      "source_file": "legacy_jobs/wwi/MigrateStagedSaleData.sql",
      "summary": "Looks up five dimension keys for each staged sale line, then replaces those invoices in Fact.Sale and closes the load in the lineage log.",
      "status": "in_progress",
      "max_attempts": null,
      "legacy_sql": "CREATE PROCEDURE Integration.MigrateStagedSaleData ...",
      "attempts": [
        {
          "number": 1,
          "started_at": null,
          "seconds": null,
          "code": "from pyspark.sql import functions as F ...",
          "error": null,
          "error_stage": null,
          "feedback": null,
          "runs": {
            "dev": {
              "tables": [
                {
                  "table": "Integration.Sale_Staging",
                  "key_cols": ["Sale Staging Key"],
                  "ignored": [],
                  "rows_legacy": 5224,
                  "rows_spark": 5224,
                  "result": {
                    "status": "pass",
                    "compared_cols": ["Bill To Customer Key", "City Key", "...24 more"],
                    "only_a": [],
                    "only_b": [],
                    "cols_only_a": [],
                    "cols_only_b": [],
                    "explanation": null
                  }
                },
                {
                  "table": "Fact.Sale",
                  "key_cols": null,
                  "ignored": [{"column": "Sale Key", "reason": "Identity key handed out by SQL Server. ..."}],
                  "rows_legacy": 228265,
                  "rows_spark": null,
                  "result": null
                }
              ]
            },
            "holdout": null
          }
        }
      ]
    }
  ]
}
```

A failing table, from `sample.json` (invented numbers):

```json
{
  "table": "Integration.Sale_Staging",
  "key_cols": ["Sale Staging Key"],
  "ignored": [],
  "rows_legacy": 5224,
  "rows_spark": 5224,
  "counts": {"only_a": 1190, "only_b": 1190, "changed": 1190},
  "result": {
    "status": "fail",
    "compared_cols": ["Bill To Customer Key", "City Key", "..."],
    "only_a": [[1, 41372, "..."]],
    "only_b": [[1, 0, "..."]],
    "cols_only_a": [],
    "cols_only_b": [],
    "explanation": {
      "cols_only_a": [], "cols_only_b": [],
      "rows_only_a": [], "rows_only_b": [],
      "changed": [{"key": [17], "col": "City Key", "a": 41372, "b": 0}],
      "dupes_a": [], "dupes_b": []
    }
  }
}
```

## Where the files go

The dashboard reads `dashboard/public/data/manifest.json` to find out which files to offer:

```json
{
  "default": "results",
  "files": [
    {"id": "results", "label": "Latest run", "path": "results.json"},
    {"id": "sample", "label": "Demo story", "path": "sample.json"}
  ]
}
```

Add an entry when you add a file.
`?data=<id>` in the address picks a file directly, e.g. `http://localhost:5173/?data=real`.

## Changing the contract

Add fields freely: the dashboard ignores ones it doesn't know.
Renaming or removing a field is a new `contract_version`, and the dashboard and `check_results.py` both need updating.
