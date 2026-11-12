# DEVLOG: EXL Data & AI Hackathon, Challenge 03

Submission due 13 Nov (email to Monika Rawal). Finalists announced by 19 Nov. Finale 23 Nov, O'Connor Centre.

---

## 2026-10-30: Decisions

- **Team:** me + my brother (team of 2 is allowed).
- **Challenge 03** (legacy SQL/SAS ETL → PySpark). Why: success is measurable (row-for-row match with the legacy output), it's EXL's core insurance/data work, and it probably scares off more teams than 04.
- **Fallback:** Challenge 02 if 03 isn't confirmed by EXL, or if SQL Server can't run locally.
- **Core idea:** the AI never grades its own work. Every translated job is checked against the real output of the legacy job, on a dev dataset (AI can fix against it) and a holdout dataset (AI never sees it).
- **Test set:**
  1. Insurance-style T-SQL jobs written by my brother without seeing the tool.
  2. Microsoft's WideWorldImporters ETL procedures, code nobody on the team wrote.
- **Honest limit (goes in the Responsible AI note):** passing means old and new agreed on every dataset we tested, not a mathematical proof. Proving two queries equivalent is undecidable in general. Recommend a parallel run on production data before switching off a legacy job.
- **Structure:** Python pipeline (`run_legacy`, `translate`, `run_spark`, `diff`, `lineage`, `loop`) + React/FastAPI review app, sharing a `results.json` contract. `diff.py` and `loop.py` hand-written.

## 2026-10-30: sqlglot probe on Microsoft's procedures

- 13 `Integration.MigrateStaged*` procedures, ~1,000 lines, 141 statements.
- sqlglot can't parse a whole procedure as-is, but parses all 141 statements once the `CREATE PROCEDURE ... BEGIN/END` wrapper is stripped.
- Transpiling to Spark with strict errors on reported **141/141 success**, but the output keeps T-SQL-only syntax (`UPDATE ... FROM ... JOIN`, `DELETE s FROM ...`) that Spark rejects. Silent failure from a standard tool. Pitch material.
- The diff will need a per-job list of columns to ignore: the procedures write `SYSDATETIME()` timestamps, lineage keys and identity keys that can never match between runs.
- Picked 3 Microsoft procedures: **City** (history table), **Sale** (lookups + delete/reinsert), **Movement** (only one using `MERGE`).

## 2026-10-31 00:20–00:53: SQL Server on the Mac (M-series, 16 GB)

```
softwareupdate --install-rosetta --agree-to-license
```
- Docker Desktop (Apple Silicon). Resources: 4 CPU, 4.3 GB RAM, 1 GB swap. Resource Saver on (5 min).
```
docker run --platform linux/amd64 -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=<SA_PASSWORD>" \
  -e "MSSQL_MEMORY_LIMIT_MB=2048" -p 1433:1433 --name sql2022 -d mcr.microsoft.com/mssql/server:2022-latest
```
- **Broke:** container died ~8 min after starting. `exit=139` (segfault), `oom=false`.
- **Fixed:** Docker Settings → General → *Use Rosetta for x86_64/amd64 emulation on Apple Silicon*. Stayed up 12+ hours after.
- **Gotcha:** clicking the Docker app icon does nothing when it's already running. Use the menu-bar whale, or `osascript -e 'quit app "Docker"'` then `open -a Docker`.
- Check: `SELECT @@version` → SQL Server 2022 16.0.4305.5, Developer Edition, Linux.

## 2026-10-31 14:00–15:18: Microsoft databases + first legacy run

- Restored both backups into the container:
  - `WideWorldImportersDW-Full.bak` (warehouse). Logical files: `WWI_Primary`, `WWI_UserData`, `WWI_Log`, `WWIDW_InMemory_Data_1`.
  - `WideWorldImporters-Full.bak` (shop). Same, but `WWI_InMemory_Data_1`.
- **Gotcha:** pasting several commands at once split the `docker cp` line. Run them one at a time.
- Before: `Fact.Sale` = 228,265 rows. `Integration.Sale_Staging` = 0.
- **Gotcha:** staging tables are `MEMORY_OPTIMIZED` with `DURABILITY = SCHEMA_ONLY`, so they empty on every SQL Server restart. Reload before every run.
- **Gotcha:** can't insert across databases straight into an in-memory table. Go through a temp table.
- `scripts/load_sale_staging.sql` replaces Microsoft's Windows-only SSIS step: pulls a month of sales from the shop DB with `Integration.GetSaleUpdates`, loads staging, opens a lineage record.
  - Result: lineage key 14. Staged 5,224 lines from 1,604 invoices. Window 2016-05-06 12:31:17 → 2016-06-06 12:31:17.
- Ran `Integration.MigrateStagedSaleData`: return code 0, `Fact.Sale` still 228,265 (the reloaded invoices were deleted and reinserted).
- **Reset:** rerun the warehouse restore with `, REPLACE`.

## 2026-10-31 15:20–17:50: Repo + Python harness

- Repo created (private until submission), branch renamed to `main`.
- **Folder split:** `legacy_jobs/` holds the code being migrated, `scripts/` holds test setup. The tool will translate everything in `legacy_jobs/`, so helpers must never sit there.
- ODBC Driver 18 via Homebrew.
  - **Broke:** `Refusing to load formula ... untrusted tap`. **Fixed:** `brew trust microsoft/mssql-release`.
  - **Broke:** `OpenSSL library could not be loaded`. `/opt/homebrew/opt/openssl` pointed at OpenSSL 4, and the driver only supports 1.x or 3. **Fixed:** `ln -sfn /opt/homebrew/opt/openssl@3 /opt/homebrew/opt/openssl`. A `brew upgrade` may flip it back.
- `migrator/run_legacy.py`: loads staging, opens a transaction, saves every table the job touches ("before"), runs the job, saves again ("after"), rolls back. The database is unchanged, so it can rerun any time.
  - Staging is loaded **outside** the transaction: one transaction can't touch an in-memory table and a second database.
  - Saved as Parquet with pyarrow: decimals stay exact, and the year-9999 `Valid To` dates don't overflow.
  - `geography` columns (`Dimension.City.Location`) are read as text, because pyodbc can't read them.
- **First run:** return code 0. Row counts identical before and after for all 8 tables. Expected: the job changes *contents*, not counts (staging key columns go from NULL to filled, ~5k `Fact.Sale` rows deleted and reinserted, one lineage row marked complete).
- `Integration.Lineage` grows by 1 per run (staging load isn't rolled back). Harmless.
- Wrote `SETUP.md` (how it works + setup from scratch + troubleshooting) and `docker-compose.yml` (same SQL Server setup as a file, with a volume so data survives container removal).

---

## Checkpoints

- [x] SQL Server running locally (target 1 Nov, done 31 Oct)
- [x] One legacy job runs end to end (done 31 Oct)
- [ ] Email Paul: are 03 and 04 confirmed? Registration step? Sample jobs for 03?
- [ ] Brother briefed: writes legacy jobs blind, owns deck / video / diagram / Responsible AI note
- [x] Python harness: save before (input) and after (answer key) snapshots (done 31 Oct)
- [x] Repo + SETUP.md (done 31 Oct)
- [ ] `diff.py`, hand-written
  - [ ] Bookmarked (11 Nov): also compare column types, since today an int32 column that comes back as int64 with the same numbers still passes.
  - [x] (done 12 Nov) Bookmarked (12 Nov, mutation test): ignored columns are dropped entirely, so a City translation that never fills in `Data Load Completed` still passes. Compare ignored columns as filled vs empty instead of skipping them.

## 12 Nov: City passes, and a mutation test of the judge

- `city`: PASS on attempt 1 (dev July 2015, 9,628 staged rows) and on the holdout (July 2014, 13,079 rows). One Claude call, $0.03.
- Cities rarely change (shop DB changes only in Jan 2013, Jul 2013, Jul 2014, Jul 2015), so the City batches are those months, not the month before the last load.
- Mutation test: 5 deliberately broken copies of `city.py`, judged on the dev data. Caught: does nothing, forgets the cutoff update, closes all versions instead of the current one. Not caught:
  - MAX instead of MIN `Valid From`: every staged row in a batch has the same `Valid From`, so the data can't tell them apart. Needs a batch where cities change twice (a window covering Jul 2014 and Jul 2015 has 1,535 such cities).
  - Never filling in `Data Load Completed`: the `diff.py` blind spot above.
- Deck: "the judge caught 3 of 5 planted bugs; the 2 it missed showed exactly what to strengthen".
- Data gap closed the same day: new batch `city_twice` (June 2014 to July 2015, 22,707 staged rows, 1,535 cities with two different `Valid From` dates).
  The real `city.py` passes it; the MAX mutant now fails on 1,536 rows of `Dimension.City`. So 4 of 5 planted bugs are caught; the last one needs the `diff.py` fix.
- Jobs can now list any number of extra batches under `"batches"` in `jobs/<job>.json`; `run_legacy.py <job>_<batch>` snapshots one.

## 12 Nov: insurance jobs pass

- Teammate delivered two synthetic databases (`InsuranceOps` source, `InsuranceDW` warehouse, WideWorldImporters style), dev and holdout loaders, and the procedures `MigrateStagedClaimData` and `MigrateStagedPremiumData`.
  Installed in `scripts/insurance/` and `legacy_jobs/insurance/`. Their files reference `run_legacy.py`, so they were not written blind: never claim they were.
- Dev window June 2025 (135 claim lines, 188 premium transactions), holdout September 2025 (103, 215).
  Planted edge cases: claims edited at the exact second their customer or policy changed, a policy, customer and agent missing from the warehouse, a claim with no adjuster, 7-digit timestamps.
- `claim` and `premium`: PASS on attempt 1 and on the holdout. About $0.045 per translation.
- Mutation test, 9 broken copies on the dev data, all caught: does nothing (x2), boundary flipped to `>=` / `<` (x2), missing member as NULL instead of 0 (x2), forgets the delete, net = gross - tax, banker's rounding.
  Running total: 13 of 14 planted bugs caught; the miss is the ignored-column blind spot in `diff.py`.

## 12 Nov evening: stricter judge, 14 of 14

- `diff.py` now masks ignored columns (a filled value becomes a "present" marker instead of being dropped), checks that rows the legacy job left alone come out of Spark identical, and flags keys Spark repeats that the legacy output doesn't. `loop.py` passes the `before/` snapshot in.
- All 9 batches re-run with the current translations and the new judge: all PASS.
- City mutant 5 (never fills `Data Load Completed`) is now caught in `Integration.Lineage`. The new judge is strictly stricter, so the other 13 stay caught: 14 of 14.
- `loop.py` after a failure (12 Nov evening): attempts run from `snapshots/<job>/loop/attempt_N.py`, and only a translation that passed dev and its holdout replaces `jobs_pyspark/<job>.py`. The holdout is skipped after a dev FAIL. A failed run prints and saves `summary.txt`: each attempt's outcome (crashed, rejected by cheat.py, timed out, or FAIL in which tables), where the evidence is, the state of `jobs_pyspark/<job>.py`, and next steps. A holdout FAIL after a dev PASS gets its own message and `holdout_report.txt`, with a warning never to feed it to the translator. Tested end to end on City with deliberately broken code.
- [x] (done 12 Nov) Fix: `keys_ok` is set only inside `if before_rows is not None:`, so `reconcile()` without `before_rows` (diff.py's own `__main__`) raises `UnboundLocalError`. Move it above that `if`.
- [ ] Bookmarked: `run_legacy.py` lets Arrow infer snapshot types from the values (SQL `int` becomes int64, `decimal(18,2)` becomes `decimal(7,2)` sized to the batch), so a type check in `diff.py` would compare against guessed types. Build the snapshot schema from `sys.columns` first; needs every snapshot regenerated and every loop re-run.
- [ ] **6 Nov:** one job translated to PySpark and reconciled end to end. Miss → pull out, time goes to LeetCode
- [x] 10 Nov: holdout check + retry loop working, demo-able (done 12 Nov: `sale` passes the dev month, May 2016, and the holdout month, April 2016)
- [ ] 12 Nov: deck, diagram, Responsible AI note, 3-min video drafted
- [ ] 13 Nov: submitted

## 12 Nov night: all 13 Microsoft jobs, 15 of 15 pass

- `scripts/make_wwi_jobs.py` set up the 11 remaining WideWorldImporters jobs: it exports each `MigrateStaged...Data` procedure into `legacy_jobs/wwi/`, generates its staging loader from the database's own column lists, and writes `jobs/<job>.json` with empty keys and ignores.
  Microsoft's staging table misspells one Movement column (`Last Modifed When`), so the loader renames it.
- Batches: Movement, Order, Purchase and Transaction use the last month as dev and the month before as holdout.
  Employee, Stock Item, Supplier, Transaction Type and Payment Method use months with changes in the shop database.
  Customer and Stock Holding have only one batch of data, so they are split by ID: even IDs are dev, odd IDs are the holdout.
- Small tables give small holdouts: Supplier and Payment Method have 1 staged row, Transaction Type 2, Employee 7.
- `scripts/column_evidence.py <job>` prints the evidence for keys and ignores: clock columns with their line numbers, counter columns (IDENTITY or a sequence) the SQL never writes, and which tables changed.
  Every job has the same two: `Data Load Completed` (the clock) and the main table's own ID counter.
- Him approved the rule for all 11 (ignore the clock and the counter, nothing else) and picked `WWI Stock Item Transaction ID` as Movement's key; Claude Code wrote the reasons into the job files.
  Stock Holding's key is `Stock Item Key` (one row per product); its counter `Stock Holding Key` is ignored with its own reason: `TRUNCATE` restarts it at 1, but the insert has no `ORDER BY`, so which row gets which number is undefined.
- All 11 PASS on attempt 1, dev and holdout, $0.38 for the 11 translations ($0.028 to $0.051 each).
  A translation that changes nothing fails every one of the 22 batches, so each PASS reproduced real changes.
- Mutation test on the two new kinds of job, 8 broken copies, all caught on dev and on the holdout.
  Movement (`MERGE`): no update branch, inserts rows that already exist, update keeps the old lineage key, staging keys never written back.
  Stock Holding (empty and reload): forgets the `TRUNCATE`, looks up the oldest stock item version, swaps two quantity columns, never marks the load successful.
  Running total: 22 of 22.
- The 15 jobs follow four patterns: history tables (7), fact loads (4), a `MERGE` (Movement) and an empty-and-reload (Stock Holding).
  13 of the 15 share Microsoft's template, and the deck's limits slide says so.

## Bookmarked (12 Nov): making the tool work for more databases

- Only `run_legacy.py` and `scripts/` are tied to SQL Server and WideWorldImporters.
  `translate.py`, `run_spark.py`, `diff.py`, `cheat.py` and `loop.py` only read Parquet snapshots and `jobs/<job>.json`, so they work for any source once snapshots exist.
- [x] (done 12 Nov) When adding City: move the job list (database, procedure, staging script, tables) out of `run_legacy.py` into each `jobs/<job>.json`, so a new job is a JSON file plus a staging script, with no Python edits.
- Next-steps slide, not before submission: one capture adapter per source system (Oracle, SAS, ...) that writes the same `before/` and `after/` Parquet files, and the SQL dialect in the translator prompt as a setting instead of hard-coded "SQL Server".
  Wait for City and Movement to show what really varies between jobs before generalising.
- Deck wording: "Only one component touches the legacy system; everything else works on standard Parquet snapshots." Don't claim "handles many databases": only one database is tested.
- Holdout split: by month, because these jobs process monthly batches (City and Movement use the same cutoff pattern).
  Without dates: split by ID range or group, use a second copy of the database, or hand-made edge cases. Each batch always gets its own legacy run and answer key.
