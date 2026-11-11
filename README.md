
# LegacyMigrator

 LegacyMigrator translates legacy T-SQL jobs into Pyspark and checks each translation row by row against the real legacy job output.
It is our entry for EXL Data & AI Hackathon Challenge 03.

## What it does

The Problem: Modernizing legacy SQL to PySpark at scale using AI is fast, but enterprise migrations stall because validating translated scripts is manual, slow, and error-prone. AI often outputs plausible code that silently fails edge cases or subtle business logic.


The Solution: LegacyMigrator catches hallucination risks by separating code generation from execution. The AI I translates T-SQL using schema definitions alone, with zero access to legacy target outputs. A human-written engine grades the output so the AI never marks its own homework. The engine runs the translated script against real snapshot inputs, compares the output against the T-SQL ground truth, and feeds execution errors or data diffs back to the model for up to 3 attempts default. An unseen holdout dataset can check for data-specific overfitting.

So far: Microsoft's MigrateStagedSaleData, 8 tables, PASS




## How it works


```
            snapshots/<job>/before/   (the tables before the job ran)
                        |                             |
          legacy job on SQL Server     PySpark translation
             (run_legacy.py)             (run_spark.py)
                        |                             |
        snapshots/<job>/after/           snapshots/<job>/spark/
      (the answer key)                 (the translation's output)
                        \                 /
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

Setup
Follow these 4 steps to set up your local development environment.
1. Clone and enter the repository
Bash
git clone <repo-URL>
cd LegacyMigrator
2. Configure SQL Server, databases, and ODBC drivers
Follow Steps 1 through 8 in SETUP.md. This covers:
Rosetta configuration for Apple Silicon
Launching SQL Server via Docker (docker compose up -d)
Downloading and restoring the sample Microsoft databases
Installing unixODBC and Microsoft ODBC Driver 18 via Homebrew
3. Create your .env configuration
Create a file named .env in the root of the project directory.
Important: .env is .gitignored—never commit secret keys or credentials to source control.
Bash
MSSQL_SERVER=localhost,1433
MSSQL_USER=sa
MSSQL_PASSWORD=YourStrong!Password123
ANTHROPIC_API_KEY=sk-ant-api03-...
JAVA_HOME=/Library/Java/JavaVirtualMachines/openjdk-17.jdk/Contents/Home
SPARK_LOCAL_IP=127.0.0.1
4. Create a Python environment and install packages
Bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
Note: Remember to run source .venv/bin/activate again whenever you open a new terminal window.

Variable
Value to show
What it's for
MSSQL_SERVER
localhost,1433
Host and port where SQL Server listens for connections (used by run_legacy.py).
MSSQL_USER
sa
SQL Server administrative login name.
MSSQL_PASSWORD
<your-password>
Set during Step 3 of SETUP.md. Requires uppercase, lowercase, a number, and a special character.
ANTHROPIC_API_KEY
<your-api-key>
API key from console.anthropic.com. Used by translate.py to prompt Claude.
JAVA_HOME
<path-to-java-17>
Target installation path for Java 17. Run /usr/libexec/java_home -v 17 on macOS and paste the printed path. Used by run_spark.py.
SPARK_LOCAL_IP
127.0.0.1
Binds PySpark execution locally to loopback, preventing Spark from guessing external network interfaces.



## Run it

Step
Command
Expected Output & Success State
1. Snapshot Legacy Job
python migrator/run_legacy.py sale
• Return Code: 0

• Logs: Shows table row counts (e.g., Fact.Sale 228265 228265).

• Artifacts: Writes snapshots/sale/before/ and snapshots/sale/after/.
2. Run Translation Loop
python migrator/loop.py sale
• Logs: sale: PASS after 1 attempt(s)

• Artifacts: Generates fully verified PySpark code at jobs_pyspark/sale.py.



## Project layout



```
LegacyMigrator/
├── legacy_jobs/wwi/     Microsoft's WideWorldImporters T-SQL procedures (MIT licence): the code being migrated
├── jobs/                One spec per job: its legacy SQL file, key columns and ignored columns, chosen by a human
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
| Claude Code | Helped build the tool. It wrote `migrator/loop.py` and `migrator/run_spark.py`, and helped edit `migrator/translate.py`. |

What the AI did not do:
- `migrator/diff.py`, the judge that decides PASS or FAIL, is written by hand.
- The key and ignored columns in `jobs/<job>.json` are chosen by a human.
- The rules Claude Code had to follow while building the tool are in [AGENTS.md](AGENTS.md).

### Existing code and data

| What | Source | Licence |
|---|---|---|
| Legacy procedures in `legacy_jobs/wwi/` | Microsoft's WideWorldImporters samples ([sql-server-samples](https://github.com/ms)) | MIT, see`legacy_jobs/wwi/LICENSE-microsoft.txt` |
| WideWorldImporters databases | The same  a fictional company, no real personal data | Public sample data |
| Python packages | PySpark, pyarrow, anthnv | Apache-2.0, Apache-2.0, Apache-2.0,MIT, BSD-3-Clause |
| SQL Server 2022 Developer Edition | Micrage | Free for development and testing |
