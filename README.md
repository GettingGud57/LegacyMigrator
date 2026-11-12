# LegacyMigrator

LegacyMigrator translates legacy T-SQL jobs into PySpark and checks each translation row by row against the real legacy job output.
It is our entry for EXL Data & AI Hackathon Challenge 03.

## What it does

**The Problem:** Modernizing legacy SQL to PySpark at scale using AI is fast, but enterprise migrations stall because validating translated scripts is manual, slow, and error-prone.
AI often outputs plausible code that silently fails edge cases or subtle business logic.

**The Solution:** LegacyMigrator catches hallucination risks by separating code generation from execution.
The AI translates T-SQL using schema definitions alone, with zero access to legacy target outputs.
A loop runs the translated script against real snapshot inputs.
A human-written judge compares the output against the T-SQL ground truth, so the AI never marks its own homework.
If the script crashes or doesn't match, the loop feeds the error or the data diffs back to the model, for up to 3 attempts by default.
An unseen holdout dataset can check for data-specific overfitting.

**So far:** 2 of Microsoft's procedures pass, each on a dev month and on a holdout month the translator never saw:
- `MigrateStagedSaleData`, 8 tables: dev May 2016, holdout April 2016.
- `MigrateStagedCityData`, a history table: dev July 2015, holdout July 2014.

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
   It gets no tools and never sees any data, only column names and types.
3. `run_spark.py` checks the translated file for cheats, then runs it on the same `before/` tables.
4. `diff.reconcile` compares the legacy output with the Spark output, table by table.
5. `loop.py` repeats steps 2 to 4.
   If a translation crashes or fails the comparison, the next attempt gets the error or the diff report as feedback.
   Optionally, it then runs the final translation once on a holdout snapshot that the translator never sees.

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

## Run it

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
   Success: the last line is `sale: PASS after 1 attempt(s). Final code: jobs_pyspark/sale.py`.
   The number of attempts can vary between runs, because the AI doesn't write the same code every time.
3. Optional: check the final translation on a holdout month the translator never sees.
   The first command needs SQL Server running, the second doesn't:
   ```
   python migrator/run_legacy.py sale_holdout
   python migrator/loop.py sale --from-existing --holdout sale_holdout
   ```
   Success: `PASS` under the `=== holdout ... (never shown to the translator) ===` line.

## Project layout

```
LegacyMigrator/
├── legacy_jobs/wwi/     Microsoft's WideWorldImporters T-SQL procedures (MIT licence): the code being migrated
├── jobs/                One spec per job: its legacy SQL file, key columns and ignored columns, each ignored column with a written reason
├── jobs_pyspark/        The PySpark translations (noop.py is a test job that changes nothing)
├── migrator/            The tool
│   ├── run_legacy.py    Runs a legacy job on SQL Server and saves before/after snapshots
│   ├── translate.py     Asks Claude to translate the legacy SQL into PySpark
│   ├── cheat.py         Rejects translations that try to cheat, for example by reading the answer files
│   ├── run_spark.py     Runs a translation on the before/ snapshot
│   ├── diff.py          The judge: compares the Spark output with the legacy output (hand-written)
│   └── loop.py          Translate, run, judge, and retry with feedback
├── scripts/             Test setup: loads a month of sales into staging, replacing Microsoft's Windows-only SSIS step
├── test/cheats/         A fake cheating translation that cheat.py must reject
├── snapshots/           Created by run_legacy.py and loop.py, git-ignored
├── docker-compose.yml   SQL Server 2022 container
├── requirements.txt     Python packages
├── SETUP.md             Full setup walkthrough
├── DEVLOG.md            Development log
└── AGENTS.md            Rules for AI coding agents working in this repo (CLAUDE.md points to it)
```

## AI tools and existing code

### AI tools

| Tool | Used for |
|---|---|
| Claude Sonnet 5.5 (`claude-sonnet-5-5`, Anthropic API) | Part of the tool: `translate.py` asks it to write each PySpark translation. It sees the legacy SQL and table schemas, never any data. |
| Claude Code and Claude chat (claude.ai) | Helped build the tool. They wrote `migrator/loop.py`, `migrator/run_spark.py`, `migrator/run_legacy.py`, `docker-compose.yml`, `scripts/load_sale_staging.sql` and `SETUP.md`, helped edit `migrator/translate.py`, and helped write this README. |

What the AI did not do:
- `migrator/diff.py`, the judge that decides PASS or FAIL, is written by hand.
- `migrator/cheat.py`, the check that rejects cheating translations, is written by hand.
- No column is ignored without a written reason in `jobs/<job>.json`, and a human checks each reason against the legacy SQL.
  For `jobs/sale.json`, Claude Code proposed the two ignored columns, and a human verified both: `Data Load Completed` is set to `SYSDATETIME()` (line 70 of the procedure), and the job never writes `Sale Key`, so SQL Server fills it in itself.
- The rules Claude Code had to follow while building the tool are in [AGENTS.md](AGENTS.md).

### Existing code and data

| What | Source | Licence |
|---|---|---|
| Legacy procedures in `legacy_jobs/wwi/` | Microsoft's WideWorldImporters samples ([sql-server-samples](https://github.com/microsoft/sql-server-samples)) | MIT, see `legacy_jobs/wwi/LICENSE-microsoft.txt` |
| WideWorldImporters databases | The same Microsoft repo: data about a fictional company, no real personal data | Public sample data |
| Python packages | PySpark, pyarrow, anthropic, pyodbc, python-dotenv | Apache-2.0, Apache-2.0, Apache-2.0, MIT, BSD-3-Clause |
| SQL Server 2022 Developer Edition | Microsoft's official Docker image | Free for development and testing |
