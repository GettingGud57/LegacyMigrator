"""
run_spark.py: run one PySpark job on a legacy job's "before" snapshot and save its output.

    snapshots/<job>/before/   the input (same tables the legacy job started from)
    snapshots/<job>/spark/    what the PySpark job produced, same file names as before/

The PySpark job is a Python file that defines:

    def run(spark, tables) -> dict

`tables` maps each table name (file name without .parquet) to a DataFrame.
`run` returns only the tables it changed. Every other table is saved as it was in before/.

Usage (from the repo root):
    python migrator/run_spark.py sale path/to/job.py
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from cheat import check_job

from dotenv import load_dotenv


def start_spark():
    # .env sets JAVA_HOME and SPARK_LOCAL_IP, which must be in place before the JVM starts
    load_dotenv(override=True)
    # Timestamps in the snapshots have no timezone. Spark's session is UTC, but collect()
    # and F.lit() convert Python datetimes using the process's local timezone, which shifts
    # values by the local UTC offset (an hour in Irish summer time). Run the whole process,
    # Python and the JVM it starts, in UTC so a timestamp round-trips unchanged.
    os.environ["TZ"] = "UTC"
    time.tzset()
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[*]")
        .appName("run_spark")
        .config("spark.sql.session.timeZone", "UTC")
        # Plain microsecond timestamps, the same encoding as the before/ and after/ files
        .config("spark.sql.parquet.outputTimestampType", "TIMESTAMP_MICROS")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def load_job(path):
    """Import the job file and return its run function."""
    spec = importlib.util.spec_from_file_location(f"spark_job_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "run", None)):
        raise TypeError(f"{path} does not define run(spark, tables)")
    return module.run


def check_result(result, tables):
    """run must return {existing table name: DataFrame}."""
    from pyspark.sql import DataFrame

    if not isinstance(result, dict):
        raise TypeError(f"run returned {type(result).__name__}, expected a dict")
    for name, df in result.items():
        if name not in tables:
            raise KeyError(f"run returned unknown table {name!r}. Known tables: {sorted(tables)}")
        if not isinstance(df, DataFrame):
            raise TypeError(f"run returned {type(df).__name__} for {name!r}, expected a DataFrame")


def write_parquet(df, path):
    """Write a DataFrame as one Parquet file (Spark itself always writes a folder of parts)."""
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        df.coalesce(1).write.mode("overwrite").parquet(tmp + "/out")
        parts = list(Path(tmp, "out").glob("part-*.parquet"))
        if len(parts) != 1:
            raise RuntimeError(f"expected one Parquet part for {path.name}, got {len(parts)}")
        shutil.move(parts[0], path)


def fail(stage, job_path):
    print(f"\nFAILED while {stage} ({job_path}):\n", file=sys.stderr)
    traceback.print_exc()
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python migrator/run_spark.py <job> path/to/job.py")
    job_name, job_path = sys.argv[1], Path(sys.argv[2])
    problems = check_job(job_path)
    if problems:
        sys.exit("Job rejected before running:\n" + "\n".join(problems))
    
    
    before_dir = Path("snapshots") / job_name / "before"
    out_dir = Path("snapshots") / job_name / "spark"
    files = sorted(before_dir.glob("*.parquet"))
    if not files:
        sys.exit(f"No Parquet files in {before_dir}/. Run: python migrator/run_legacy.py {job_name}")

    started = time.perf_counter()
    print("1. Starting Spark")
    spark = start_spark()

    print(f"2. Reading {before_dir}/")
    tables = {f.stem: spark.read.parquet(str(f)) for f in files}
    before_counts = {name: df.count() for name, df in tables.items()}

    print(f"3. Running {job_path}")
    job_started = time.perf_counter()
    try:
        run = load_job(job_path)
        changed = run(spark, dict(tables))
        check_result(changed, tables)
    except Exception:
        fail("running the job", job_path)

    print(f"4. Writing {out_dir}/")
    # Spark is lazy, so errors in the job's transformations often only surface here
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    spark_counts = {}
    try:
        for f in files:
            if f.stem in changed:
                write_parquet(changed[f.stem], out_dir / f.name)
                spark_counts[f.stem] = spark.read.parquet(str(out_dir / f.name)).count()
            else:
                # Not returned by the job: keep the original file byte for byte, so Spark's
                # re-encoding (column types, timestamps) can't make an untouched table look changed
                shutil.copyfile(f, out_dir / f.name)
                spark_counts[f.stem] = before_counts[f.stem]
    except Exception:
        fail(f"writing {f.name}, which runs the job's transformations", job_path)
    job_seconds = time.perf_counter() - job_started

    spark.stop()
    print(f"\n   {'table':28} {'before':>8} {'spark':>8}  changed")
    for name in before_counts:
        mark = "yes" if name in changed else ""
        print(f"   {name:28} {before_counts[name]:>8} {spark_counts[name]:>8}  {mark}")
    print(f"\n   job + write: {job_seconds:.1f}s, total: {time.perf_counter() - started:.1f}s")
    print(f"   saved to {out_dir}/")


if __name__ == "__main__":
    main()
