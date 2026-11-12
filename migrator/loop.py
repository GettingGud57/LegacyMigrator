"""
loop.py: translate a legacy job, run it, judge it, and retry with feedback until it passes.

    for attempt in 1..N:
        1. translate   -> snapshots/<job>/loop/attempt_N.py   (translate.py, one Claude call)
        2. run it      -> snapshots/<job>/spark/              (run_spark.py, in its own process)
             crashed or rejected?  feedback = the error, next attempt
        3. judge       -> PASS or FAIL                        (diff.reconcile, legacy after vs spark)
             PASS?  stop
             FAIL?  feedback = the diff report, next attempt
    afterwards (--holdout): if the dev batch passed, run that code once on the holdout and show the
    result to humans only. Holdout results never go back to the translator.

Only a translation that passed everything it was checked on replaces jobs_pyspark/<job>.py,
so a failed run never overwrites one that worked.

loop.py never decides PASS or FAIL itself: every verdict comes from diff.reconcile.
Which columns are keys and which are ignored comes from jobs/<job>.json, chosen by a human.

Every attempt's code and feedback from the latest run is kept in snapshots/<job>/loop/,
with summary.txt saying what happened and what to do next.

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


def judge_tables(job, spec):
    """Every table in snapshots/<job>/after/ through diff.reconcile. Gives back (failed tables, report).

    The before/ snapshot goes in too, so diff can check that rows the legacy job
    left alone also come out of Spark unchanged.
    """
    before_dir = Path("snapshots") / job / "before"
    after_dir = Path("snapshots") / job / "after"
    spark_dir = Path("snapshots") / job / "spark"
    tables = sorted(after_dir.glob("*.parquet"))
    if not tables:
        sys.exit(f"No legacy output in {after_dir}/. Run: python migrator/run_legacy.py {job}")

    failed = []
    report = []
    for f in tables:
        name = f.stem
        spark_file = spark_dir / f.name
        if not spark_file.exists():
            failed.append(name)
            report.append(f"=== {name}: FAIL, the job produced no output for this table")
            continue
        result = diff.reconcile(
            diff.load(f),
            diff.load(spark_file),
            spec["keys"].get(name),
            list(spec.get("ignore", {}).get(name, {})),
            before_rows=diff.load(before_dir / f.name),
        )
        if result["status"] != "pass":
            failed.append(name)
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                diff.print_verdict(result)
            report.append(f"=== {name} (A = legacy output, B = your output)\n{text.getvalue()}")
    return failed, "\n".join(report)


def judge(job, spec):
    """Like judge_tables, but gives back (passed, report)."""
    failed, report = judge_tables(job, spec)
    return not failed, report


def describe_error(error):
    """One line for the summary: what kind of failure it was, and the error's last line."""
    if "Job rejected before running" in error:
        kind = "rejected by cheat.py"
    elif "did not finish within" in error:
        kind = "timed out"
    else:
        kind = "crashed"
    last_line = next((line.strip() for line in reversed(error.splitlines()) if line.strip()), "")
    return f"{kind}: {last_line[:160]}"


def failure_summary(job, history, log_dir, job_path, had_job_file):
    """What a developer needs after a failed run: what happened, where the evidence is, what next."""
    attempts_run = len(history)
    if had_job_file:
        kept = f"{job_path}: unchanged. A failed attempt never overwrites it."
    else:
        kept = f"{job_path}: not created, because no attempt passed."
    return "\n".join([
        f"{job}: FAIL after {attempts_run} attempt(s). Nothing was marked as migrated.",
        "",
        "What happened:",
        *[f"   {line}" for line in history],
        "",
        f"Evidence, in {log_dir}/:",
        "   attempt_N.py     the code each attempt ran",
        "   feedback_N.txt   the error or diff report each attempt got back",
        "",
        kept,
        "",
        "Next steps:",
        f"   1. Read the last report: {log_dir / f'feedback_{attempts_run}.txt'}",
        f"   2. Try more attempts: python migrator/loop.py {job} --attempts 5",
        f"   3. Or fix it by hand: copy the closest attempt to {job_path}, edit it, then judge it with",
        f"      python migrator/loop.py {job} --from-existing --attempts 1",
    ])


def holdout_failure_summary(job, holdout, attempt_path, log_dir, job_path):
    """The dev batch passed but the holdout didn't: the translation fits the dev data, not the logic."""
    return "\n".join([
        f"{job}: FAIL on the holdout {holdout}. It passed the dev batch, but not data it never saw,",
        "so treat it as not migrated.",
        "",
        f"Holdout report: above, and in {log_dir / 'holdout_report.txt'} (for humans only).",
        "Never paste it into a translation prompt: the holdout only stays blind if the AI never sees it.",
        f"The code that passed dev: {attempt_path}. {job_path} was left unchanged.",
        "",
        "Next steps:",
        "   1. Read the holdout report to see which case the dev batch didn't cover.",
        "   2. Fix the translation by hand, or add that case to a new dev batch and pick a new holdout.",
    ])


def run(job, attempts=3, holdout=None, from_existing=False, model=translate.DEFAULT_MODEL):
    spec = load_spec(job)
    job_path = Path("jobs_pyspark") / f"{job}.py"
    had_job_file = job_path.exists()
    log_dir = Path("snapshots") / job / "loop"
    shutil.rmtree(log_dir, ignore_errors=True)  # history of this run only, no leftovers
    log_dir.mkdir(parents=True)

    passed = False
    feedback = None
    history = []  # one line per attempt, for the summary
    for attempt in range(1, attempts + 1):
        print(f"\n=== attempt {attempt} of {attempts} ===")
        attempt_path = log_dir / f"attempt_{attempt}.py"

        if attempt == 1 and from_existing and had_job_file:
            print(f"1. Using existing {job_path}")
            code = job_path.read_text()
        else:
            print(f"1. Translating {spec['legacy_sql']}" + (" with feedback" if feedback else ""))
            try:
                code = translate.translate(job, spec["legacy_sql"], model, feedback)
            except translate.TranslationError as e:
                # Not the translation's fault (API down, key missing, ...): retrying won't help
                sys.exit(f"Translation failed: {e}")
        attempt_path.write_text(code)

        # Each attempt runs from snapshots/<job>/loop/, so jobs_pyspark/<job>.py is only
        # replaced once a translation has passed (below).
        print(f"2. Running {attempt_path} on snapshots/{job}/before/")
        error = run_spark(job, attempt_path)
        if error:
            print("   crashed or rejected:\n" + error)
            history.append(f"attempt {attempt}: {describe_error(error)}")
            problem = f"Running it failed with this error:\n{error}"
        else:
            print(f"3. Judging snapshots/{job}/spark/ against snapshots/{job}/after/")
            failed, report = judge_tables(job, spec)
            if not failed:
                passed = True
                history.append(f"attempt {attempt}: PASS")
                print("   PASS: every table matches the legacy output")
                break
            history.append(f"attempt {attempt}: FAIL in {', '.join(failed)}")
            print("   FAIL\n" + report)
            problem = f"Comparing its output with the legacy output found these differences:\n{report}"

        feedback = f"Your previous translation:\n```\n{code}```\n\n{problem}"
        (log_dir / f"feedback_{attempt}.txt").write_text(feedback)

    if not passed:
        summary = failure_summary(job, history, log_dir, job_path, had_job_file)
        if holdout:
            summary += f"\n\nHoldout {holdout}: skipped, because the translation didn't pass the dev batch."
        print("\n" + summary)
        (log_dir / "summary.txt").write_text(summary + "\n")
        return False

    print(f"\n{job}: PASS after {attempt} attempt(s).")
    summary = [f"{job}: PASS after {attempt} attempt(s).", *history]

    if holdout:
        # Shown to humans only. Nothing from here is ever passed to translate.
        print(f"\n=== holdout: {attempt_path} on snapshots/{holdout}/ (never shown to the translator) ===")
        error = run_spark(holdout, attempt_path)
        if error:
            print("   crashed or rejected:\n" + error)
            holdout_failed, holdout_report = True, error
        else:
            failed, holdout_report = judge_tables(holdout, spec)
            holdout_failed = bool(failed)
            print("   FAIL" if holdout_failed else "   PASS")
            if holdout_report:
                print(holdout_report)
        if holdout_failed:
            (log_dir / "holdout_report.txt").write_text(holdout_report + "\n")
            text = holdout_failure_summary(job, holdout, attempt_path, log_dir, job_path)
            print("\n" + text)
            (log_dir / "summary.txt").write_text("\n".join(summary) + "\n\n" + text + "\n")
            return False
        summary.append(f"holdout {holdout}: PASS")

    if not job_path.exists() or job_path.read_text() != code:
        job_path.write_text(code)
    print(f"Final code: {job_path}")
    summary.append(f"Final code: {job_path}")
    (log_dir / "summary.txt").write_text("\n".join(summary) + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Translate, run and judge a legacy job, retrying with feedback.")
    parser.add_argument("job", help="job name, e.g. sale (needs jobs/<job>.json and snapshots/<job>/)")
    parser.add_argument("--attempts", type=int, default=3, help="most translations to try (default 3)")
    parser.add_argument("--holdout", help="snapshot name to check the final job on, e.g. sale_holdout")
    parser.add_argument("--from-existing", action="store_true",
                        help="judge the current jobs_pyspark/<job>.py as attempt 1 instead of translating")
    parser.add_argument("--model", default=translate.DEFAULT_MODEL, choices=sorted(translate.PRICES))
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    # Keep progress lines in order with translate.py's stderr cost line, also when piped to a log
    sys.stdout.reconfigure(line_buffering=True)
    passed = run(args.job, args.attempts, args.holdout, args.from_existing, args.model)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
