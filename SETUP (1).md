# LegacyMigrator: how it works and how to set it up

Read part 1 first. It explains what all the pieces are, so the setup steps in part 2 make sense.

---

## Part 1: How it works

### The idea

Companies have old jobs that run every night and fill up report tables. They want to move those jobs onto new machines (Spark). Our tool translates each old job into PySpark, then **checks** the translation:

1. Start from the exact same tables.
2. Run the old job. Save the result. That's the answer key.
3. Run the new PySpark job. Save its result.
4. Compare the two results. If they match, the translation is right.

The AI never decides whether it got it right. The old job's real output does.

### Why the old jobs exist: shop vs warehouse

A company's **live system** (the "shop") stores each sale split across lots of tables, like drawers:

- Receipts drawer: receipt #1043, date, which customer
- Receipt lines drawer: 3 × chocolate frogs, 1 × USB drive
- Customers drawer: customer #832 lives in Cork
- Products drawer: chocolate frogs are chilled

That's good for running the shop (every fact is written once), but bad for reports. "How much did we sell in Cork last month?" means opening every drawer for every receipt, on the same system customers are buying from. And when a customer moves, the shop overwrites their old city, so history is lost.

So every night, jobs copy the data into a **warehouse** built for reports:

- **One flat row per item sold**, with everything on it. This is called denormalizing.
- **A separate system**, so reports don't slow down sales.
- **Keeps history**: "lived in Cork until March, Dublin since" (the `Valid From` / `Valid To` columns).

The warehouse layout is a **star schema**:
- `Fact.Sale` is the fact table: one row per item sold, with the numbers.
- `Dimension.Customer`, `Dimension.City`, `Dimension.[Stock Item]`, `Dimension.Employee` are dimension tables: the who, where and what.

### What we're using

Microsoft's free sample databases, **WideWorldImporters**:

| Database | What it is |
|---|---|
| `WideWorldImporters` | the shop (live system) |
| `WideWorldImportersDW` | the warehouse (already full: 228,265 sales) |

Both come as `.bak` backup files that we restore into SQL Server.

### The legacy job we test first: `Integration.MigrateStagedSaleData`

It lives inside the warehouse database. It never reads the shop directly. It works from a **waiting table** (staging), `Integration.Sale_Staging`, like a chef who only cooks from the tray on the counter.

Tiny example. Staging before the job:

| sale | customer | customer number |
|---|---|---|
| 1 | Anna | *empty* |
| 2 | Ben | *empty* |

After the job:

| sale | customer | customer number |
|---|---|---|
| 1 | Anna | 7 |
| 2 | Ben | 9 |

The real job does this for five columns (`City Key`, `Customer Key`, `Bill To Customer Key`, `Stock Item Key`, `Salesperson Key`), then:
- deletes the old copies of those sales from `Fact.Sale` and inserts fresh ones
- marks the load as finished in `Integration.Lineage` (the logbook)

**Same number of rows before and after, different contents.** Row counts won't show what changed. Comparing row by row will.

### Why staging is empty, and what `scripts/load_sale_staging.sql` does

The staging table is **memory-only** (`DURABILITY = SCHEMA_ONLY`). Its contents are throwaway, so SQL Server never saves them to disk, which means **every SQL Server restart empties it.**

In Microsoft's real setup, a Windows-only tool (SSIS) fills the tray each night. We don't have that on a Mac, so `load_sale_staging.sql` does the delivery:

1. Picks a window: the last month of sales
2. Empties the tray
3. Asks the shop for those sales (`WideWorldImporters.Integration.GetSaleUpdates`, which joins 6 tables into flat rows)
4. Puts them on the tray (through a temp table, because SQL Server won't let one statement write to an in-memory table *and* read another database)
5. Writes "sales load started" in the logbook. The job looks for that note.
6. Prints how many rows it staged (about 5,224)

Why is it split into "deliver" and "process" instead of one big SQL? In real life the shop and warehouse are on **different servers**, copying is quick so the shop is only bothered briefly, and if processing crashes you can rerun it without touching the shop again. We don't redesign it. **Our job is to copy what the old code does, not fix it.**

### What `migrator/run_legacy.py` does: the photo machine

1. **Load staging** (runs `load_sale_staging.sql`)
2. **Start a transaction** (an "undo point")
3. **"Before" photo**: save every table the job touches
4. **Run the old job**
5. **"After" photo**: save the same tables again
6. **Roll back**: undo everything, so the database is exactly as it was and you can rerun any time

Photos are saved as Parquet files (a compact format that keeps decimals exact; Spark reads it natively):

```
snapshots/sale/before/   ← the input  (the new PySpark job will read this)
snapshots/sale/after/    ← the answer key
snapshots/sale/meta.json ← return code and row counts
```

**Why before *and* after?** Both chefs must get the identical basket of ingredients. Otherwise, if the dishes differ, you can't tell if the recipe was wrong or the ingredients were. Before = the basket. After = the old chef's dish.

Python makes nothing in the database. It's just the photographer.

### How the pieces connect

```
Your Mac                                     Docker container "sql2022" (Linux)
──────────────────────────────────           ──────────────────────────────────
migrator/run_legacy.py                       SQL Server 2022
  └ pyodbc + ODBC Driver 18 ──port 1433────▶   WideWorldImporters    (shop)
.env (password, never committed)               WideWorldImportersDW  (warehouse)
snapshots/ ◀── Parquet files                 /var/opt/mssql/backup/*.bak
```

- **Docker** runs SQL Server in a sealed Linux box on your Mac.
- **Port 1433** is the door. `-p 1433:1433` connects port 1433 on your Mac to port 1433 in the box, so Python connects to `localhost,1433` ("this Mac") and Docker passes it through.
- **Files** can't pass through the door. The box can't see your Mac's folders, so backups go in with `docker cp`.

### Folder layout

```
LegacyMigrator/
  .env                    password etc. NEVER committed
  .gitignore
  DEVLOG.md               what we did, day by day
  SETUP.md                this file
  docker-compose.yml      the SQL Server setup, as a file
  requirements.txt        Python packages
  legacy_jobs/            old code the tool migrates
    wwi/                  Microsoft's jobs (MIT licence, keep LICENSE-microsoft.txt)
    insurance/            our own insurance-style jobs
  scripts/                helpers that set up test data (never migrated)
    load_sale_staging.sql
  migrator/               the tool
    run_legacy.py
  snapshots/              generated, not committed
```

`legacy_jobs/` and `scripts/` are separate on purpose: the tool will translate everything in `legacy_jobs/`, and it must never try to "migrate" a helper script.

---

## Part 2: Set it up from scratch (Mac with Apple chip)

**Shortcut:** `scripts/bench.sh` does steps 3 to 9 in one go (and starts Docker on Linux).
It is safe to rerun and skips whatever is already done.
On the Mac you still need steps 1 and 2 first, and step 8 (the ODBC driver) if it isn't installed: the script stops and points here.
Then run the jobs as in step 10, or see `docs/reports/test-bench.html` for the full list of commands.


Run commands **one at a time**. Pasting several at once can split lines.

### 1. Rosetta (lets the Mac run Intel software; SQL Server needs it)
```
softwareupdate --install-rosetta --agree-to-license
```

### 2. Docker Desktop
Install the Apple Silicon version from docker.com. Then in Docker Desktop:
- **Settings → General**: turn on *Use Virtualization Framework* and **Use Rosetta for x86_64/amd64 emulation on Apple Silicon**. Without the Rosetta one, SQL Server crashes after a few minutes.
- **Settings → Resources**: memory 4 GB.
- Apply & Restart. Docker lives in the menu bar (whale icon); clicking the app icon often does nothing.

### 3. `.env` in the repo folder
```
MSSQL_SERVER=localhost,1433
MSSQL_USER=sa
MSSQL_PASSWORD=pick-your-own
```
The password needs upper case, lower case, a number and a symbol (avoid spaces and `$`). Check git ignores it:
```
git check-ignore .env
```
It must print `.env`.

Load the password into your terminal, so the commands below don't contain it:
```
set -a; source .env; set +a
```

### 4. Start SQL Server
```
docker compose up -d
```
Wait about 30 seconds, then check:
```
docker exec -it sql2022 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_PASSWORD" -C -Q "SELECT @@version"
```
It should print `Microsoft SQL Server 2022 ...`.

### 5. Download both databases
```
curl -L -o ~/Downloads/WideWorldImportersDW-Full.bak https://github.com/Microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImportersDW-Full.bak
```
```
curl -L -o ~/Downloads/WideWorldImporters-Full.bak https://github.com/Microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak
```

### 6. Copy them into the container
```
docker exec sql2022 mkdir -p /var/opt/mssql/backup
```
```
docker cp ~/Downloads/WideWorldImportersDW-Full.bak sql2022:/var/opt/mssql/backup/
```
```
docker cp ~/Downloads/WideWorldImporters-Full.bak sql2022:/var/opt/mssql/backup/
```
```
docker exec -u root sql2022 chown -R mssql /var/opt/mssql/backup
```

### 7. Restore them
Warehouse:
```
docker exec -it sql2022 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_PASSWORD" -C -Q "RESTORE DATABASE WideWorldImportersDW FROM DISK='/var/opt/mssql/backup/WideWorldImportersDW-Full.bak' WITH MOVE 'WWI_Primary' TO '/var/opt/mssql/data/WWIDW.mdf', MOVE 'WWI_UserData' TO '/var/opt/mssql/data/WWIDW_UserData.ndf', MOVE 'WWI_Log' TO '/var/opt/mssql/data/WWIDW.ldf', MOVE 'WWIDW_InMemory_Data_1' TO '/var/opt/mssql/data/WWIDW_InMemory'"
```
Shop:
```
docker exec -it sql2022 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_PASSWORD" -C -Q "RESTORE DATABASE WideWorldImporters FROM DISK='/var/opt/mssql/backup/WideWorldImporters-Full.bak' WITH MOVE 'WWI_Primary' TO '/var/opt/mssql/data/WWI.mdf', MOVE 'WWI_UserData' TO '/var/opt/mssql/data/WWI_UserData.ndf', MOVE 'WWI_Log' TO '/var/opt/mssql/data/WWI.ldf', MOVE 'WWI_InMemory_Data_1' TO '/var/opt/mssql/data/WWI_InMemory'"
```
Both should end with `RESTORE DATABASE successfully processed`. Check:
```
docker exec -it sql2022 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_PASSWORD" -C -d WideWorldImportersDW -Q "SELECT COUNT(*) AS sales FROM Fact.Sale"
```
It should print 228265.

### 8. ODBC driver (lets Python talk to SQL Server)
```
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
```
```
brew trust microsoft/mssql-release
```
```
HOMEBREW_ACCEPT_EULA=Y brew install msodbcsql18
```
```
brew install openssl@3
```
```
ln -sfn /opt/homebrew/opt/openssl@3 /opt/homebrew/opt/openssl
```
That last line matters: the driver only works with OpenSSL 1.x or 3, and Homebrew may point the plain `openssl` name at OpenSSL 4.

### 9. Python
```
python3 -m venv .venv
```
```
source .venv/bin/activate
```
```
pip install -r requirements.txt
```
Rerun `source .venv/bin/activate` in every new terminal.

### 10. Run it
From the repo folder:
```
python migrator/run_legacy.py sale
```
Expected:
```
1. Loading staging
    {'staged_rows': 5224, 'invoices': 1604, 'window_from': ..., 'window_to': ...}
2. Running the legacy job inside a transaction
3. Rolled back, database unchanged

   return code: 0
   ...
   Fact.Sale                      228265   228265
```

---

## Part 3: When things break

| Symptom | Cause | Fix |
|---|---|---|
| Container stops after a few minutes, `docker inspect sql2022 --format '{{.State.ExitCode}}'` shows `139` | SQL Server segfaults under Docker's default emulator | Turn on the Rosetta setting (step 2), then `docker start sql2022` |
| Clicking the Docker app does nothing | It's already running in the menu bar | Use the whale icon, or `osascript -e 'quit app "Docker"'` then `open -a Docker` |
| `docker cp requires 2 arguments` | Command got split when pasted | Paste one line at a time |
| `Refusing to load formula ... untrusted tap` | Newer Homebrew blocks third-party taps | `brew trust microsoft/mssql-release` |
| `OpenSSL library could not be loaded` | `/opt/homebrew/opt/openssl` points at OpenSSL 4 | `ln -sfn /opt/homebrew/opt/openssl@3 /opt/homebrew/opt/openssl`. A `brew upgrade` can undo this. |
| Staging table is empty | It's memory-only, so restarts wipe it | `run_legacy.py` reloads it every run. By hand: run `scripts/load_sale_staging.sql` |
| `Integration.Lineage` count goes up by 1 every run | Loading staging happens outside the rolled-back transaction | Harmless |
| Need the warehouse back to original | The job was run outside `run_legacy.py` | Rerun the warehouse restore with `, REPLACE` added at the end |

**Don't delete the container if you started it with plain `docker run`** (no volume). The databases live inside it. `docker compose` keeps them in a volume, so they survive.

Stop SQL Server when you're not using it, to free RAM:
```
docker stop sql2022
```
Start it again with `docker start sql2022` (or `docker compose up -d`).
