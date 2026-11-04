"""
Shared setup for the tests. pytest loads this file automatically.

If you change a function's name or arguments in migrator/, the helpers here
are the one place to update, so the tests keep checking the same behaviour.
"""
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "migrator"))  # so `import diff` finds migrator/diff.py
sys.path.insert(0, str(REPO / "tests"))

# run_legacy imports pyodbc at the top. The tests never talk to SQL Server, so if
# pyodbc isn't installed (it needs the ODBC driver), put a stand-in in its place.
try:
    import pyodbc  # noqa: F401
except ImportError:
    sys.modules["pyodbc"] = types.ModuleType("pyodbc")

import diff  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402


def verdict_for_files(path_a, path_b, key_cols=None, ignore_cols=()):
    """The PASS/FAIL that diff.py gives for two Parquet files. Returns "pass" or "fail"."""
    return diff.reconcile(diff.load(path_a), diff.load(path_b), key_cols, ignore_cols)["status"]


def write_parquet(path, arrow_table):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(arrow_table, path)
    return path


def run_spark_cli(workdir, job_file, job_name="sale", extra_env=None):
    """
    Run `python migrator/run_spark.py <job_name> <job_file>` with workdir as the
    current folder (so snapshots/ means workdir/snapshots/). Returns the finished process.
    """
    env = dict(os.environ)
    env.setdefault("TZ", "UTC")
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(REPO / "migrator" / "run_spark.py"), job_name, str(job_file)],
        cwd=workdir, env=env, capture_output=True, text=True, timeout=600,
    )


def spark_available():
    try:
        import pyspark  # noqa: F401
    except ImportError:
        return False
    return subprocess.run(["java", "-version"], capture_output=True).returncode == 0


needs_spark = pytest.mark.skipif(not spark_available(), reason="needs pyspark and Java")
