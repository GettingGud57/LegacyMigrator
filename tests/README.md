# Tests

These tests came out of a bug review of the pipeline.
The full write-up, with examples and fix hints, is `docs/reports/review.html`.

There are two kinds of test:

- **Lock-in tests** check things that already work, so they stay working.
  They pass today.
- **Bug tests** are marked `@pytest.mark.bug`.
  Each one describes one finding from the review.
  They fail today, and each should pass once its bug is fixed.
  Treat the list of failing bug tests as a to-do list.

No test needs SQL Server.
The Spark tests need Java, like `run_spark.py` does.

## Running them

Install the test tools once, inside your venv:

```
pip install pytest hypothesis pyspark pyarrow python-dotenv
```

From the repo folder:

```
python -m pytest -m "not spark"
```

That's the fast set, about 20 seconds.

```
python -m pytest
```

That's everything, about 3 minutes, because each Spark test starts Spark.

Handy variations:

```
python -m pytest -m bug                 # only the to-do list
python -m pytest -m "not bug"           # only the lock-in tests (should all pass)
python -m pytest tests/test_diff.py -v  # one file, one line per test
python -m pytest -k Finding3            # one finding
```

## What each failing test means

The finding numbers match the report.
They're in order of how much damage the bug does to the claim "the old system's output decides".

| Finding | Test | What it means |
|---|---|---|
| 1 | `test_diff.py::TestFinding1_EveryTableIsCompared` | `python migrator/diff.py` only compares `Integration.Sale_Staging`. Fact.Sale, Lineage and ETL Cutoff are never checked, and a missing output file goes unnoticed. |
| 2 | `test_diff.py::TestFinding2_TypesAreCompared` | Column types are never compared. `decimal(18,2)` vs `decimal(38,6)`, int vs double, bit vs int all pass if the values look equal. |
| 3 | `test_diff.py::TestFinding3_IgnoredColumnsStillGetChecked` | Ignoring a column skips it completely, so a translation that never fills it in still passes. The second test in the class must keep passing after the fix. |
| 4 | `test_run_spark.py::test_finding4_failed_run_leaves_no_old_output` | When a job crashes, the previous run's `spark/` output is left behind, so `diff.py` can grade stale results. |
| 5 | `test_diff.py::TestFinding5_EmptyTables` | Two empty tables always pass, even with completely different columns. |
| 6 | `test_run_spark.py::test_finding6_job_cannot_copy_the_answer_key` | A generated job can read `snapshots/<job>/after/` and return it, and it gets PASS. |
| 7 | `test_translate.py::test_finding7_claude_gets_no_tools` | `claude -p` still has its file and shell tools while translating. |
| 8 | `test_run_legacy.py::TestFinding8_DeclaredTypesAreKept` and `test_run_spark.py::TestFinding8_GuessedTypesBreakTheTranslation` | `run_legacy` guesses Parquet types from the values instead of using the SQL types. All-NULL columns become type `null`, empty tables lose every type, and `sale.py` crashes on a price bigger than any already in Fact.Sale. |
| 9 | `test_run_spark.py::test_finding9_result_does_not_depend_on_laptop_timezone` | Run in Dublin, the Sale job's `Cutoff Time` comes out an hour early. Results depend on the laptop's timezone. |
| 12 | `test_diff.py::TestFinding12_ExplanationDoesNotCrash` | If the Spark output lost the key column, `reconcile` crashes with `KeyError` instead of printing FAIL. |
| 13 | `test_setup.py::test_finding13_requirements_file_exists` | `requirements.txt` is missing, but SETUP step 9 uses it. |

Findings 10 and 11 have no test, because they can only show up on a real SQL Server.
The report explains how to check them on your Mac.

## Order to fix things in

Some fixes depend on others:

1. Fix finding 8 (real SQL types in `run_legacy`) **before** finding 2 (compare types in `diff.py`).
   Today the types in `after/` are guesses, so a strict type check would fail for the wrong reasons.
2. After both are fixed, expect `Integration.Sale_Staging` to start failing.
   `sale.py` casts the key columns to `long` (64-bit), but the SQL columns are `int` (32-bit).
   That's a real difference the checker should catch, and the retry loop should fix it.
   Don't hand-edit `jobs_pyspark/sale.py`.

## When you change a function's name or arguments

The helpers in `tests/conftest.py` are the one place the tests call into `migrator/`:

- `verdict_for_files(a, b, key_cols, ignore_cols)` returns `"pass"` or `"fail"` for two Parquet files.
  If you change how `diff.py` loads files or decides PASS/FAIL, change this function so it calls your new code.
- `run_spark_cli(workdir, job_file)` runs `run_spark.py` the way you do by hand.

A few tests call `diff.reconcile(rows_a, rows_b, key_cols=..., ignore_cols=...)` directly.
If you add a new argument for volatile columns (finding 3), update the call in that test.

`tests/snapshot_builder.py` has a `FakeCursor` that stands in for pyodbc.
It understands the `sys.columns` query in `run_legacy.select_list()`, including extra fields like `c.precision` and `c.scale`, and `cursor.description` carries precision and scale the way pyodbc's does.
If your fix for finding 8 asks the database something else, teach `FakeCursor` about it.

## The property tests

`test_diff_properties.py` uses Hypothesis.
It makes hundreds of random little tables, applies a change that definitely matters (edit a cell, drop a row, duplicate a row, swap two values), and checks `reconcile` says FAIL.
It also checks that shuffling rows never matters.
If one fails, Hypothesis prints the smallest table it could find that breaks it.
