"""
check_results.py: check that a results file follows docs/results-contract.md.

It checks the shape (every required field is there, with the right kind of value) and one
rule that matters more than the shape: a job may only say "verified" if its latest attempt
passed every table on both dev and holdout data. The dashboard applies the same rule, so a
status the evidence doesn't support shows up as a warning there too.

Usage (from the repo root):
    python scripts/check_results.py dashboard/public/data/sample.json [more files...]

Exits with code 1 if any file has problems.
"""
import json
import sys

JOB_STATUSES = {"verified", "failed", "retrying", "in_progress", "not_started"}
RESULT_KEYS = {"status", "compared_cols", "only_a", "only_b", "cols_only_a", "cols_only_b", "explanation"}
EXPLANATION_KEYS = {"cols_only_a", "cols_only_b", "rows_only_a", "rows_only_b", "changed", "dupes_a", "dupes_b"}


class Checker:
    def __init__(self):
        self.problems = []

    def need(self, obj, key, kinds, where):
        """Report a problem unless obj[key] exists and is one of the given types."""
        if not isinstance(obj, dict) or key not in obj:
            self.problems.append(f"{where}: missing '{key}'")
            return None
        value = obj[key]
        if not isinstance(value, kinds):
            names = "/".join("null" if k is type(None) else k.__name__ for k in kinds)
            self.problems.append(f"{where}.{key}: expected {names}, got {type(value).__name__}")
            return None
        return value

    def table(self, t, where):
        name = self.need(t, "table", (str,), where) or "?"
        where = f"{where}[{name}]"
        self.need(t, "key_cols", (list, type(None)), where)
        for i, ig in enumerate(self.need(t, "ignored", (list,), where) or []):
            self.need(ig, "column", (str,), f"{where}.ignored[{i}]")
            reason = self.need(ig, "reason", (str,), f"{where}.ignored[{i}]")
            if reason is not None and not reason.strip():
                self.problems.append(f"{where}.ignored[{i}]: every ignored column needs a reason")
        self.need(t, "rows_legacy", (int, type(None)), where)
        self.need(t, "rows_spark", (int, type(None)), where)
        result = self.need(t, "result", (dict, type(None)), where)
        if result is None:
            return
        missing = RESULT_KEYS - set(result)
        if missing:
            self.problems.append(f"{where}.result: missing {sorted(missing)} (store what reconcile() returns)")
            return
        if result["status"] not in ("pass", "fail"):
            self.problems.append(f"{where}.result.status: must be 'pass' or 'fail'")
        ignored = {ig.get("column") for ig in t.get("ignored") or []}
        overlap = ignored & set(result["compared_cols"])
        if overlap:
            self.problems.append(f"{where}: {sorted(overlap)} listed as ignored but also compared")
        lists_empty = not any(result[k] for k in ("only_a", "only_b", "cols_only_a", "cols_only_b"))
        counts = t.get("counts") or {}
        if counts.get("only_a") or counts.get("only_b"):
            lists_empty = False
        if (result["status"] == "pass") != lists_empty:
            self.problems.append(f"{where}: status '{result['status']}' doesn't match the row lists")
        ex = result["explanation"]
        if ex is not None:
            missing = EXPLANATION_KEYS - set(ex)
            if missing:
                self.problems.append(f"{where}.result.explanation: missing {sorted(missing)}")

    def run(self, run, where):
        if run is None:
            return
        for t in self.need(run, "tables", (list,), where) or []:
            self.table(t, f"{where}.tables")

    def job(self, job, where):
        job_id = self.need(job, "id", (str,), where) or "?"
        where = f"jobs[{job_id}]"
        for key in ("name", "proc", "legacy_sql"):
            self.need(job, key, (str,), where)
        status = self.need(job, "status", (str,), where)
        if status is not None and status not in JOB_STATUSES:
            self.problems.append(f"{where}.status: '{status}' is not one of {sorted(JOB_STATUSES)}")
        attempts = self.need(job, "attempts", (list,), where) or []
        for i, a in enumerate(attempts):
            aw = f"{where}.attempts[{i}]"
            number = self.need(a, "number", (int,), aw)
            if number is not None and number != i + 1:
                self.problems.append(f"{aw}.number: expected {i + 1}, got {number}")
            self.need(a, "code", (str,), aw)
            self.need(a, "error", (str, type(None)), aw)
            runs = self.need(a, "runs", (dict,), aw) or {}
            self.run(runs.get("dev"), f"{aw}.runs.dev")
            self.run(runs.get("holdout"), f"{aw}.runs.holdout")
            if a.get("error") and runs.get("dev"):
                self.problems.append(f"{aw}: has an error and dev results; a crashed attempt has no results")
        if status == "verified" and not verified_by_evidence(attempts):
            self.problems.append(f"{where}: says 'verified' but its latest attempt did not pass "
                                 "every table on both dev and holdout data")
        if status == "not_started" and attempts:
            self.problems.append(f"{where}: says 'not_started' but has attempts")

    def file(self, data):
        if self.need(data, "contract_version", (int,), "file") not in (None, 1):
            self.problems.append("file.contract_version: this checker knows version 1")
        self.need(data, "sample", (bool,), "file")
        jobs = self.need(data, "jobs", (list,), "file") or []
        ids = [j.get("id") for j in jobs if isinstance(j, dict)]
        if len(ids) != len(set(ids)):
            self.problems.append("file.jobs: job ids must be unique (they're used in links)")
        for i, job in enumerate(jobs):
            self.job(job, f"jobs[{i}]")


def all_pass(run):
    tables = (run or {}).get("tables") or []
    return bool(tables) and all((t.get("result") or {}).get("status") == "pass" for t in tables)


def verified_by_evidence(attempts):
    if not attempts:
        return False
    last = attempts[-1]
    runs = last.get("runs") or {}
    return not last.get("error") and all_pass(runs.get("dev")) and all_pass(runs.get("holdout"))


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/check_results.py results.json [more.json ...]")
    bad = 0
    for path in sys.argv[1:]:
        if path.endswith("manifest.json"):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        checker = Checker()
        checker.file(data)
        if checker.problems:
            bad += 1
            print(f"{path}: {len(checker.problems)} problem(s)")
            for p in checker.problems:
                print(f"  - {p}")
        else:
            jobs = data.get("jobs", [])
            print(f"{path}: OK ({len(jobs)} jobs, sample={data.get('sample')})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
