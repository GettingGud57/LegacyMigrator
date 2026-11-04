#!/usr/bin/env bash
# bench.sh: take a fresh machine to a ready test bench, in one command.
#
#   1. starts Docker (Linux only, if the daemon isn't running)
#   2. creates .env with a random password, if there isn't one
#   3. starts SQL Server 2022 with docker compose and waits until it answers
#   4. downloads both WideWorldImporters backups and checks their SHA-256
#   5. restores them (skipped if they're already there, unless --reset)
#   6. installs ODBC Driver 18 (Linux; on a Mac it tells you the brew commands)
#   7. makes .venv and installs requirements.txt
#   8. checks Python can reach the warehouse
#
# Usage, from the repo root:
#   scripts/bench.sh           safe to rerun; only does what's missing
#   scripts/bench.sh --reset   also restores both databases from the backups again
#
# Works on Linux (x86_64) and on the Mac (Apple chip, Docker Desktop with Rosetta on).
set -euo pipefail
cd "$(dirname "$0")/.."

RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

URL=https://github.com/Microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0
CACHE="${BENCH_CACHE:-$HOME/.cache/legacymigrator}"
# SHA-256 of the two release files. Microsoft doesn't publish checksums for these, so these are
# the values we got on 2026-11-04. A mismatch means the download is broken or the file changed.
SHA_DW=e2f4a37c2db3aa494ca8f7bee2f52372b3d2cceac2ec7e3aa3b140bd1e77bee5
SHA_SHOP=e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124

step() { printf '\n== %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

sha256() {
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# sqlcmd inside the container. The password comes from the container's own environment,
# so it never appears on a command line.
sql() {
  docker exec sql2022 bash -c 'SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -h -1 -W "$@"' _ "$@"
}

step "1. Docker"
if ! docker info >/dev/null 2>&1; then
  if [ "$(uname)" = Linux ] && command -v dockerd >/dev/null; then
    echo "   starting dockerd in the background (log: /tmp/dockerd.log)"
    (nohup dockerd >/tmp/dockerd.log 2>&1 &)
    for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
  fi
  docker info >/dev/null 2>&1 || die "Docker isn't running. On a Mac, start Docker Desktop (menu-bar whale)."
fi
echo "   ok"

step "2. .env"
if [ ! -f .env ]; then
  # Upper, lower, digit and symbol, as SQL Server requires. No $ or spaces.
  pw="Bench_$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')A1!"
  printf 'MSSQL_SERVER=localhost,1433\nMSSQL_USER=sa\nMSSQL_PASSWORD=%s\nSPARK_LOCAL_IP=127.0.0.1\n' "$pw" > .env
  echo "   created .env with a random password"
else
  echo "   using the existing .env"
fi
git check-ignore -q .env || die ".env is not ignored by git. Fix .gitignore before going on."
set -a; . ./.env; set +a

step "3. SQL Server"
docker compose up -d
printf '   waiting for SQL Server to answer'
for _ in $(seq 1 60); do
  sql -Q "SELECT 1" >/dev/null 2>&1 && break
  printf '.'; sleep 2
done
echo
sql -Q "SELECT 1" >/dev/null 2>&1 || die "SQL Server didn't come up. Try: docker logs sql2022"
echo "   $(sql -Q "SET NOCOUNT ON; SELECT SERVERPROPERTY('ProductVersion')") is up"

step "4. Backups (cached in $CACHE)"
mkdir -p "$CACHE"
fetch() {  # file, expected sha256
  local f="$CACHE/$1"
  if [ -f "$f" ] && [ "$(sha256 "$f")" = "$2" ]; then echo "   $1 already downloaded"; return; fi
  echo "   downloading $1"
  curl -fsSL --retry 4 -o "$f.part" "$URL/$1"
  [ "$(sha256 "$f.part")" = "$2" ] || { rm -f "$f.part"; die "$1: checksum doesn't match. Download again."; }
  mv "$f.part" "$f"
  echo "   $1 checksum ok"
}
fetch WideWorldImportersDW-Full.bak "$SHA_DW"
fetch WideWorldImporters-Full.bak "$SHA_SHOP"

step "5. Restore"
restore() {  # database, backup file, in-memory logical name, file prefix
  local exists
  exists=$(sql -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = '$1'")
  if [ "$exists" = 1 ] && [ $RESET = 0 ]; then echo "   $1 already restored (use --reset to restore again)"; return; fi
  docker exec sql2022 mkdir -p /var/opt/mssql/backup
  docker cp "$CACHE/$2" "sql2022:/var/opt/mssql/backup/$2"
  docker exec -u root sql2022 chown mssql "/var/opt/mssql/backup/$2"
  echo "   restoring $1"
  sql -Q "IF DB_ID('$1') IS NOT NULL ALTER DATABASE [$1] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
          RESTORE DATABASE [$1] FROM DISK='/var/opt/mssql/backup/$2' WITH REPLACE,
          MOVE 'WWI_Primary' TO '/var/opt/mssql/data/$4.mdf',
          MOVE 'WWI_UserData' TO '/var/opt/mssql/data/${4}_UserData.ndf',
          MOVE 'WWI_Log' TO '/var/opt/mssql/data/$4.ldf',
          MOVE '$3' TO '/var/opt/mssql/data/${4}_InMemory';
          ALTER DATABASE [$1] SET MULTI_USER;" | grep -E "successfully|Msg" || true
}
restore WideWorldImportersDW WideWorldImportersDW-Full.bak WWIDW_InMemory_Data_1 WWIDW
restore WideWorldImporters   WideWorldImporters-Full.bak   WWI_InMemory_Data_1   WWI
sales=$(sql -d WideWorldImportersDW -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM Fact.Sale")
echo "   Fact.Sale has $sales rows (a fresh restore has 228265)"

step "6. ODBC Driver 18"
if command -v odbcinst >/dev/null && odbcinst -q -d 2>/dev/null | grep -q "ODBC Driver 18"; then
  echo "   already installed"
elif [ "$(uname)" = Linux ] && command -v apt-get >/dev/null; then
  . /etc/os-release
  curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor --yes -o /usr/share/keyrings/microsoft-prod.gpg
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/$VERSION_ID/prod $VERSION_CODENAME main" \
    > /etc/apt/sources.list.d/mssql-release.list
  apt-get update -qq
  ACCEPT_EULA=Y DEBIAN_FRONTEND=noninteractive apt-get install -y -qq msodbcsql18 unixodbc-dev >/dev/null
  echo "   installed"
else
  die "Install ODBC Driver 18 first. On a Mac: see step 8 of 'SETUP (1).md' (brew tap, brew trust, brew install msodbcsql18, openssl@3 link)."
fi

step "7. Python"
PY=""
for cand in python3.10 python3.11 python3.12 python3.13 python3; do
  if command -v "$cand" >/dev/null && "$cand" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then PY=$cand; break; fi
done
[ -n "$PY" ] || die "Need Python 3.10 or newer."
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo "   $(.venv/bin/python --version) with $(.venv/bin/pip freeze | tr '\n' ' ')"
command -v java >/dev/null || echo "   WARNING: no java on PATH. PySpark needs Java 17 or 21."

step "8. Python can reach the warehouse"
.venv/bin/python - <<'EOF'
import os, pyodbc
from dotenv import load_dotenv
load_dotenv(".env")  # explicit path: find_dotenv() fails for a script read from stdin
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.environ['MSSQL_SERVER']};DATABASE=WideWorldImportersDW;"
    f"UID={os.environ['MSSQL_USER']};PWD={{{os.environ['MSSQL_PASSWORD']}}};"
    "Encrypt=yes;TrustServerCertificate=yes")
print("   ok:", conn.cursor().execute("SELECT COUNT(*) FROM Fact.Sale").fetchone()[0], "rows in Fact.Sale")
EOF

printf '\nBench ready. Next:\n  source .venv/bin/activate\n  python migrator/run_legacy.py sale\n  python migrator/run_spark.py sale jobs_pyspark/sale.py\n  python migrator/check.py sale\n'
