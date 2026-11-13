# LegacyMigrator

LegacyMigrator translates legacy T-SQL jobs into PySpark and checks each translation row by row against the real legacy job output.
It is our entry for EXL Data & AI Hackathon Challenge 03.

## What it does

**The Problem:** Modernizing legacy SQL to PySpark at scale using AI is fast, but enterprise migrations stall because validating translated scripts is manual, slow, and error-prone.
AI often outputs plausible code that silently fails edge cases or subtle business logic.

**The Solution:** LegacyMigrator catches hallucination risks by separating code generation from execution.
The AI translates T-SQL using schema definitions alone; the only data it ever sees is the diff report from a failed dev attempt.
A loop runs the translated script against real snapshot inputs.
A human-written judge compares the output against the T-SQL ground truth, so the AI never marks its own homework.
If the script crashes or doesn't match, the loop feeds the error or the data diffs back to the model, for up to 3 attempts by default.
An unseen holdout dataset can check for data-specific overfitting.

**So far:** all 15 jobs pass on the first attempt, each on a dev batch and on a holdout batch the translator never saw:
- All 13 of Microsoft's `MigrateStaged...Data` procedures for the WideWorldImporters warehouse.
  They follow four patterns: history tables that keep every old version of a row (City, Customer, Employee, Payment Method, Stock Item, Supplier, Transaction Type), fact loads (Sale, Order, Purchase, Transaction), a `MERGE` that updates or inserts (Movement), and an empty-and-reload (Stock Holding).
  City also passes a 13-month batch in which 1,535 cities changed twice.
- `MigrateStagedClaimData` and `MigrateStagedPremiumData` (insurance test jobs on synthetic data, with planted edge cases): dev June 2025, holdout September 2025.

Each job's holdout batch is described in `jobs/<job>.json`.
Some holdouts are small because their source tables are small: Supplier and Payment Method have 1 row, and Transaction Type has 2.

To check that a PASS means something, we also break translations on purpose: the judge catches all 22 planted bugs, in the City, Claim, Premium, Movement and Stock Holding translations.

Every job also has a column-level lineage map in `lineage/<job>.md`, saying which source columns feed each column the job writes.
Claude drafts each map, and `lineage.py` checks it without AI: all 15 maps cover every column, cite only columns that exist, and agree with the keys and ignored columns in `jobs/<job>.json` and with the tables each job really changed.
Those checks can't prove a map right, so each map still says it needs a human review.

## How it works

```
                    snapshots/<job>/before/
                (the tables before the job ran)
                |                             |
    legacy job on SQL Server         PySpark translation
         (run_legacy.py)               (run_spark.py)
                |                             |
     snapshots/<job>/after/        snapshots/<job>/spark/
        (the answer key)         (the translation's output)
                \                             /
                 diff.reconcile (hand-written)
                               |
                         PASS or FAIL
```

1. `run_legacy.py` runs the legacy job on SQL Server inside a transaction.
   It saves every table the job touches before and after the job runs, then rolls back, so the database is left unchanged.
2. `translate.py` sends the legacy SQL and the table schemas to Claude, which writes a PySpark job.
   It gets no tools and no data, only column names and types, plus the error or diff report on a retry (step 5).
3. `run_spark.py` checks the translated file for cheats, then runs it on the same `before/` tables.
4. `diff.reconcile` compares the legacy output with the Spark output, table by table.
5. `loop.py` repeats steps 2 to 4.
   If a translation crashes or fails the comparison, the next attempt gets the error or the diff report as feedback.
   Optionally, it then runs the final translation once on a holdout snapshot that the translator never sees.
6. `lineage.py` asks Claude, in a separate call with the same inputs as the translator, to map every column the job writes to its source columns.
   It checks the map without AI, cross-checks it against `jobs/<job>.json` and the dev snapshot, and writes `lineage/<job>.md` for people to review.
   Lineage never affects a PASS or FAIL.

## Prerequisites

| Requirement | Tested version | Why it's needed |
| :--- | :--- | :--- |
| **macOS on Apple Silicon** | `26.6` | The only platform tested. Not tested on Linux or Windows. |
| **Python** | `3.10.4` | Runs the tool. 3.10 is the oldest version the packages in `requirements.txt` support. |
| **Java** | Amazon Corretto `17` | PySpark runs on Java. Spark 4 dropped Java 8 and 11, so use 17. |
| **Docker Desktop** | `29.9.2` | Runs SQL Server 2022 (`mcr.microsoft.com/mssql/server:2022-latest`), which executes the legacy jobs. On Apple Silicon, turn on Docker's Rosetta setting or SQL Server crashes after a few minutes ([SETUP step 2](SETUP.md#2-docker-desktop)). |
| **Microsoft ODBC Driver 18 + unixODBC** | `18.7.1.1` / `2.3.14` | Lets Python (`pyodbc`) talk to SQL Server. A plain `brew install` isn't enough, so follow [SETUP step 8](SETUP.md#8-odbc-driver-lets-python-talk-to-sql-server). |
| **Anthropic API key** | `claude-sonnet-5-5` (default model) | `translate.py` calls Claude to write the PySpark. Each call costs money, and the tool prints the cost after every call. |

## Setup

Follow these 4 steps to set up your local development environment.

1. Clone and enter the repository:
   ```
   git clone <repo-URL>
   cd LegacyMigrator
   ```
2. Configure SQL Server, the databases and the ODBC driver by following steps 1 to 8 in [SETUP.md](SETUP.md).
   This covers:
   - Rosetta configuration for Apple Silicon
   - Launching SQL Server via Docker (`docker compose up -d`)
   - Downloading and restoring the sample Microsoft databases
   - Installing unixODBC and Microsoft ODBC Driver 18 via Homebrew
3. Create a file named `.env` in the root of the project directory.
   `.env` is git-ignored, so secret keys and credentials never reach source control. Never commit it.
   ```
   MSSQL_SERVER=localhost,1433
   MSSQL_USER=sa
   MSSQL_PASSWORD=<your-password>
   ANTHROPIC_API_KEY=<your-api-key>
   JAVA_HOME=<path-to-java-17>
   SPARK_LOCAL_IP=127.0.0.1
   ```

   | Variable | Value | What it's for |
   |---|---|---|
   | `MSSQL_SERVER` | `localhost,1433` | Host and port where SQL Server listens for connections (used by `run_legacy.py`). |
   | `MSSQL_USER` | `sa` | SQL Server administrative login name. |
   | `MSSQL_PASSWORD` | your own password | Set during step 3 of [SETUP.md](SETUP.md). Requires uppercase, lowercase, a number, and a special character. |
   | `ANTHROPIC_API_KEY` | your API key | API key from console.anthropic.com. Used by `translate.py` to prompt Claude. |
   | `JAVA_HOME` | path to Java 17 | Run `/usr/libexec/java_home -v 17` on macOS and paste the printed path. Used by `run_spark.py`. |
   | `SPARK_LOCAL_IP` | `127.0.0.1` | Binds PySpark execution locally to loopback, preventing Spark from guessing external network interfaces. |
4. Create a Python environment and install packages:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Run `source .venv/bin/activate` again whenever you open a new terminal window.
5. Optional, for the insurance jobs: build the two synthetic databases, then create the two procedures in the warehouse.
   Rebuilding drops and recreates both databases, so it also resets them:
   ```
   python scripts/insurance/run_sql.py scripts/insurance/create_insurance.sql
   python scripts/insurance/run_sql.py legacy_jobs/insurance/MigrateStagedClaimData.sql InsuranceDW
   python scripts/insurance/run_sql.py legacy_jobs/insurance/MigrateStagedPremiumData.sql InsuranceDW
   ```

## Run it

The commands below use the `sale` job.
The other 14 jobs are the files in `jobs/` (such as `city`, `movement` and `claim`), each with a `<job>_holdout` batch.


1. Snapshot the legacy job (SQL Server must be running):
   ```
   python migrator/run_legacy.py sale
   ```
   Success: `return code: 0`, and table row counts such as `Fact.Sale 228265 228265`.
   It writes `snapshots/sale/before/` and `snapshots/sale/after/`.
2. Run the translation loop:
   ```
   python migrator/loop.py sale
   ```
   Success: `sale: PASS after 1 attempt(s).`, then `Final code: jobs_pyspark/sale.py` as the last line.
   The number of attempts can vary between runs, because the AI doesn't write the same code every time.
   If every attempt fails, the loop prints what happened in each attempt, where the evidence is and what to try next, and saves that to `snapshots/sale/loop/summary.txt`.
   A failed run never overwrites a translation that passed.
3. Optional: check the final translation on a holdout month the translator never sees.
   The first command needs SQL Server running, the second doesn't:
   ```
   python migrator/run_legacy.py sale_holdout
   python migrator/loop.py sale --from-existing --holdout sale_holdout
   ```
   Success: `PASS` under the `=== holdout ... (never shown to the translator) ===` line.
4. Optional: draft and check the job's column-level lineage.
   The first command calls Claude, the second only reruns the checks on the saved map:
   ```
   python migrator/lineage.py sale
   python migrator/lineage.py sale --check
   ```
   Success: `structure: ok` and `disagrees, for a human to resolve: 0`, and the map is in `lineage/sale.md`.

## Project layout

```
LegacyMigrator/
├── legacy_jobs/           The code being migrated
│   ├── wwi/               Microsoft's WideWorldImporters T-SQL procedures (MIT licence)
│   └── insurance/         Insurance test jobs written for this project
├── jobs/                  One spec per job: how to run its legacy job and extra batches (like the holdout), its key columns, and its ignored columns, each with a written reason
├── jobs_pyspark/          The PySpark translations (noop.py is a test job that changes nothing)
├── lineage/               Column-level lineage per job: a map for people (.md) and the same map as data (.json)
├── migrator/              The tool
│   ├── run_legacy.py      Runs a legacy job on SQL Server and saves before/after snapshots
│   ├── translate.py       Asks Claude to translate the legacy SQL into PySpark
│   ├── cheat.py           Rejects translations that try to cheat, for example by reading the answer files
│   ├── run_spark.py       Runs a translation on the before/ snapshot
│   ├── diff.py            The judge: compares the Spark output with the legacy output (hand-written)
│   ├── lineage.py         Asks Claude for each job's column-level lineage and checks the map without AI
│   └── loop.py            Translate, run, judge, and retry with feedback
├── scripts/               Test setup: loads each job's staging table, replacing Microsoft's Windows-only SSIS step
│   ├── make_wwi_jobs.py   Sets up the WideWorldImporters jobs: exports each procedure, writes its staging loader and an empty job spec
│   ├── column_evidence.py Prints the evidence for choosing a job's keys and ignored columns
│   ├── sqlglot_demo.py    Demo from the video: sqlglot converts a statement that Spark then rejects (needs `pip install sqlglot==30.31.0`, not in requirements.txt)
│   └── insurance/         Builds the synthetic insurance databases and their dev and holdout loaders
├── test/cheats/           A fake cheating translation that cheat.py must reject
├── snapshots/             Created by run_legacy.py and loop.py, git-ignored
├── docker-compose.yml     SQL Server 2022 container
├── requirements.txt       Python packages
├── SETUP.md               Full setup walkthrough
├── DEVLOG.md              Development log
└── AGENTS.md              Rules for AI coding agents working in this repo (CLAUDE.md points to it)
```

## AI tools and existing code

### AI tools

| Tool | Used for |
|---|---|
| Claude Sonnet 5.5 (`claude-sonnet-5-5`, Anthropic API) | Part of the tool: `translate.py` asks it to write each PySpark translation, and `lineage.py` asks it to draft each job's column-level lineage. It sees the legacy SQL and table schemas, plus the error or diff report of a failed dev attempt, and never the holdout. |
| Claude (used by a teammate) | Generated the synthetic insurance test databases, their dev and holdout loaders, and `scripts/insurance/run_sql.py`. |
| Claude Code and Claude chat (claude.ai) | Helped build the tool. They wrote `migrator/loop.py`, `migrator/run_spark.py`, `migrator/run_legacy.py`, `migrator/lineage.py`, `docker-compose.yml`, the `scripts/load_*_staging.sql` loaders, `scripts/make_wwi_jobs.py`, `scripts/column_evidence.py` and `SETUP.md`, helped edit `migrator/translate.py`, and helped write this README. |

What the AI did not do:
- `migrator/diff.py`, the judge that decides PASS or FAIL, is written by hand.
- `migrator/cheat.py`, the check that rejects cheating translations, is written by hand.
- No column is ignored without a written reason in `jobs/<job>.json`.
  A human set the rule: ignore only the clock time the job ran and the ID numbers SQL Server generates itself, because those differ on every run.
  For `jobs/sale.json`, Claude Code proposed the two ignored columns, and a human verified both: `Data Load Completed` is set to `SYSDATETIME()` (line 70 of the procedure), and the job never writes `Sale Key`, so SQL Server fills it in itself.
  For the 11 newest WideWorldImporters jobs, `scripts/column_evidence.py` listed every such column from the SQL and the database, a human approved applying the rule to all of them, and Claude Code wrote the reasons from that evidence.
- The rules Claude Code had to follow while building the tool are in [AGENTS.md](AGENTS.md).

### Existing code and data

| What | Source | Licence |
|---|---|---|
| Legacy procedures in `legacy_jobs/wwi/` | Microsoft's WideWorldImporters samples ([sql-server-samples](https://github.com/microsoft/sql-server-samples)) | MIT, see `legacy_jobs/wwi/LICENSE-microsoft.txt` |
| WideWorldImporters databases | The same Microsoft repo: data about a fictional company, no real personal data | Public sample data |
| Insurance test databases and loaders (`scripts/insurance/`) | Generated for this project by a teammate with Claude: synthetic, deterministic data, no real people | Ours |
| Insurance procedures (`legacy_jobs/insurance/`) | Written for this project by a teammate | Ours |
| Python packages | PySpark, pyarrow, anthropic, pyodbc, python-dotenv | Apache-2.0, Apache-2.0, Apache-2.0, MIT, BSD-3-Clause |
| SQL Server 2022 Developer Edition | Microsoft's official Docker image | Free for development and testing |
