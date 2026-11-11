"""
loop.py: translate a legacy job, run it, judge it, and retry with feedback until it passes.

    for attempt in 1..N:
        1. translate   -> jobs_pyspark/<job>.py      (translate.py, one Claude call)
        2. run it      -> snapshots/<job>/spark/     (run_spark.py, in its own process)
             crashed or rejected?  feedback = the error, next attempt
        3. judge       -> PASS or FAIL               (diff.reconcile, legacy after vs spark)
             PASS?  stop
             FAIL?  feedback = the diff report, next attempt
    afterwards (--holdout): run the final job once on the holdout and show the result
    to humans only. Holdout results never go back to the translator.

loop.py never decides PASS or FAIL itself: every verdict comes from diff.reconcile.
Which columns are keys and which are ignored comes from jobs/<job>.json, chosen by a human.

Every attempt's code and feedback from the latest run is kept in snapshots/<job>/loop/.

Usage (from the repo root):
    python migrator/loop.py sale
    python migrator/loop.py sale --attempts 3 --holdout sale_holdout
    python migrator/loop.py sale --from-existing     # judge jobs_pyspark/sale.py first, no API call
"""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import diff  # the hand-written judge, next to this file
import translate

RUN_SPARK = Path(__file__).parent / "run_spark.py"
SPARK_TIMEOUT = 15 * 60  # seconds; a translation that hangs counts as a failed attempt
MAX_ERROR_CHARS = 6000  # keep feedback short enough to be useful in the prompt


def load_spec(job):
    path = Path("jobs") / f"{job}.json"
    if not path.exists():
        sys.exit(f"No job spec at {path}. Write one with legacy_sql, keys and ignore.")
    return json.loads(path.read_text())


def run_spark(job, job_path):
    """Run the PySpark job on snapshots/<job>/before/. Gives back None if it ran, else the error."""
    try:
        proc = subprocess.run(
            [sys.executable, str(RUN_SPARK), job, str(job_path)],
            capture_output=True, text=True, timeout=SPARK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return f"The job did not finish within {SPARK_TIMEOUT // 60} minutes."
    if proc.returncode == 0:
        return None
    error = proc.stderr.strip() or proc.stdout.strip()
    return error[-MAX_ERROR_CHARS:]  # the end of a traceback is the useful part


def judge(job, spec):
    """Every table in snapshots/<job>/after/ through diff.reconcile. Gives back (passed, report)."""
    after_dir = Path("snapshots") / job / "after"
    spark_dir = Path("snapshots") / job / "spark"
    tables = sorted(after_dir.glob("*.parquet"))
    if not tables:
        sys.exit(f"No legacy output in {after_dir}/. Run: python migrator/run_legacy.py {job}")

    passed = True
    report = []
    for f in tables:
        name = f.stem
        spark_file = spark_dir / f.name
        if not spark_file.exists():
            passed = False
            report.append(f"=== {name}: FAIL, the job produced no output for this table")
            continue
        result = diff.reconcile(
            diff.load(f),
            diff.load(spark_file),
            spec["keys"].get(name),
            list(spec.get("ignore", {}).get(name, {})),
        )
        if result["status"] != "pass":
            passed = False
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                diff.print_verdict(result)
            report.append(f"=== {name} (A = legacy output, B = your output)\n{text.getvalue()}")
    return passed, "\n".join(report)


def print_table_verdicts(job, spec):
    passed, report = judge(job, spec)
    print("   PASS" if passed else "   FAIL")
    if report:
        print(report)
    return passed


def run(job, attempts=3, holdout=None, from_existing=False, model=translate.DEFAULT_MODEL):
    spec = load_spec(job)
    job_path = Path("jobs_pyspark") / f"{job}.py"
    log_dir = Path("snapshots") / job / "loop"
    shutil.rmtree(log_dir, ignore_errors=True)  # history of this run only, no leftovers
    log_dir.mkdir(parents=True)

    passed = False
    feedback = None
    for attempt in range(1, attempts + 1):
        print(f"\n=== attempt {attempt} of {attempts} ===")

        if attempt == 1 and from_existing and job_path.exists():
            print(f"1. Using existing {job_path}")
            code = job_path.read_text()
        else:
            print(f"1. Translating {spec['legacy_sql']}" + (" with feedback" if feedback else ""))
            try:
                code = translate.translate(job, spec["legacy_sql"], model, feedback)
            except translate.TranslationError as e:
                # Not the translation's fault (API down, key missing, ...): retrying won't help
                sys.exit(f"Translation failed: {e}")
            job_path.write_text(code)
        (log_dir / f"attempt_{attempt}.py").write_text(code)

        print(f"2. Running {job_path} on snapshots/{job}/before/")
        error = run_spark(job, job_path)
        if error:
            print("   crashed or rejected:\n" + error)
            problem = f"Running it failed with this error:\n{error}"
        else:
            print(f"3. Judging snapshots/{job}/spark/ against snapshots/{job}/after/")
            passed, report = judge(job, spec)
            if passed:
                print("   PASS: every table matches the legacy output")
                break
            print("   FAIL\n" + report)
            problem = f"Comparing its output with the legacy output found these differences:\n{report}"

        feedback = f"Your previous translation:\n```\n{code}```\n\n{problem}"
        (log_dir / f"feedback_{attempt}.txt").write_text(feedback)

    print(f"\n{job}: {'PASS' if passed else 'FAIL'} after {attempt} attempt(s). Final code: {job_path}")

    if holdout:
        # Shown to humans only. Nothing from here is ever passed to translate.
        print(f"\n=== holdout: {job_path} on snapshots/{holdout}/ (never shown to the translator) ===")
        error = run_spark(holdout, job_path)
        if error:
            print("   crashed or rejected:\n" + error)
            holdout_passed = False
        else:
            holdout_passed = print_table_verdicts(holdout, spec)
        passed = passed and holdout_passed

    return passed


def main():
    parser = argparse.ArgumentParser(description="Translate, run and judge a legacy job, retrying with feedback.")
    parser.add_argument("job", help="job name, e.g. sale (needs jobs/<job>.json and snapshots/<job>/)")
    parser.add_argument("--attempts", type=int, default=3, help="most translations to try (default 3)")
    parser.add_argument("--holdout", help="snapshot name to check the final job on, e.g. sale_holdout")
    parser.add_argument("--from-existing", action="store_true",
                        help="judge the current jobs_pyspark/<job>.py as attempt 1 instead of translating")
    parser.add_argument("--model", default=translate.DEFAULT_MODEL, choices=sorted(translate.PRICES))
    args = parser.parse_args()
    # Keep progress lines in order with translate.py's stderr cost line, also when piped to a log
    sys.stdout.reconfigure(line_buffering=True)
    passed = run(args.job, args.attempts, args.holdout, args.from_existing, args.model)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
