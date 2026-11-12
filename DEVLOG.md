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
  - [ ] Bookmarked (12 Nov, mutation test): ignored columns are dropped entirely, so a City translation that never fills in `Data Load Completed` still passes. Compare ignored columns as filled vs empty instead of skipping them.

## 12 Nov: City passes, and a mutation test of the judge

- `city`: PASS on attempt 1 (dev July 2015, 9,628 staged rows) and on the holdout (July 2014, 13,079 rows). One Claude call, $0.03.
- Cities rarely change (shop DB changes only in Jan 2013, Jul 2013, Jul 2014, Jul 2015), so the City batches are those months, not the month before the last load.
- Mutation test: 5 deliberately broken copies of `city.py`, judged on the dev data. Caught: does nothing, forgets the cutoff update, closes all versions instead of the current one. Not caught:
  - MAX instead of MIN `Valid From`: every staged row in a batch has the same `Valid From`, so the data can't tell them apart. Needs a batch where cities change twice (a window covering Jul 2014 and Jul 2015 has 1,535 such cities).
  - Never filling in `Data Load Completed`: the `diff.py` blind spot above.
- Deck: "the judge caught 3 of 5 planted bugs; the 2 it missed showed exactly what to strengthen".
- [ ] **6 Nov:** one job translated to PySpark and reconciled end to end. Miss → pull out, time goes to LeetCode
- [x] 10 Nov: holdout check + retry loop working, demo-able (done 12 Nov: `sale` passes the dev month, May 2016, and the holdout month, April 2016)
- [ ] 12 Nov: deck, diagram, Responsible AI note, 3-min video drafted
- [ ] 13 Nov: submitted

## Bookmarked (12 Nov): making the tool work for more databases

- Only `run_legacy.py` and `scripts/` are tied to SQL Server and WideWorldImporters.
  `translate.py`, `run_spark.py`, `diff.py`, `cheat.py` and `loop.py` only read Parquet snapshots and `jobs/<job>.json`, so they work for any source once snapshots exist.
- [x] (done 12 Nov) When adding City: move the job list (database, procedure, staging script, tables) out of `run_legacy.py` into each `jobs/<job>.json`, so a new job is a JSON file plus a staging script, with no Python edits.
- Next-steps slide, not before submission: one capture adapter per source system (Oracle, SAS, ...) that writes the same `before/` and `after/` Parquet files, and the SQL dialect in the translator prompt as a setting instead of hard-coded "SQL Server".
  Wait for City and Movement to show what really varies between jobs before generalising.
- Deck wording: "Only one component touches the legacy system; everything else works on standard Parquet snapshots." Don't claim "handles many databases": only one database is tested.
- Holdout split: by month, because these jobs process monthly batches (City and Movement use the same cutoff pattern).
  Without dates: split by ID range or group, use a second copy of the database, or hand-made edge cases. Each batch always gets its own legacy run and answer key.
