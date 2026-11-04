// Everything the dashboard concludes, worked out from the evidence in the results file.
// The only verdict it takes as given is reconcile()'s per-table "pass"/"fail".
// A job's own "status" field is checked against that evidence, never trusted blindly.

import type { Attempt, Cell, Job, JobStatus, ResultsFile, Run, TableResult } from './types';

export type TableVerdict = 'pass' | 'fail' | 'not_compared';

/** What happened in one attempt. */
export type Outcome =
  | 'crashed' // the code threw an error, nothing was compared
  | 'mismatch' // ran, but at least one table differs on dev data
  | 'incomplete' // ran, everything compared so far matches, some tables not compared yet
  | 'passed_dev' // every table matches on dev data, holdout not checked
  | 'failed_holdout' // matched dev, differs on holdout
  | 'verified'; // every table matches on dev and holdout

/** Status as shown. 'unconfirmed' = the file says verified but the evidence doesn't back it. */
export type ShownStatus = JobStatus | 'unconfirmed';

export function tableVerdict(t: TableResult): TableVerdict {
  // A failed extra check (e.g. the Spark output file is missing) fails the table even with no result
  const extraFailed = (t.extra_checks ?? []).some((c) => c.status === 'fail');
  if (!t.result) return extraFailed ? 'fail' : 'not_compared';
  if (t.result.status === 'fail') return 'fail';
  return (t.extra_checks ?? []).every((c) => c.status === 'pass') ? 'pass' : 'fail';
}

export interface RunSummary {
  tables: number;
  compared: number;
  passed: number;
  failed: number;
  rowsCompared: number;
}

export function summarizeRun(run: Run | null): RunSummary {
  const s: RunSummary = { tables: 0, compared: 0, passed: 0, failed: 0, rowsCompared: 0 };
  for (const t of run?.tables ?? []) {
    s.tables++;
    const v = tableVerdict(t);
    if (v === 'not_compared') continue;
    s.compared++;
    s.rowsCompared += t.rows_legacy ?? 0;
    if (v === 'pass') s.passed++;
    else s.failed++;
  }
  return s;
}

function allPass(run: Run | null): boolean {
  const s = summarizeRun(run);
  return s.tables > 0 && s.passed === s.tables;
}

export function attemptOutcome(a: Attempt): Outcome {
  if (a.error) return 'crashed';
  const dev = summarizeRun(a.runs.dev);
  if (dev.failed > 0) return 'mismatch';
  if (!allPass(a.runs.dev)) return 'incomplete';
  if (!a.runs.holdout) return 'passed_dev';
  if (summarizeRun(a.runs.holdout).failed > 0) return 'failed_holdout';
  return allPass(a.runs.holdout) ? 'verified' : 'passed_dev';
}

export function lastAttempt(job: Job): Attempt | undefined {
  return job.attempts[job.attempts.length - 1];
}

export interface JobView {
  shown: ShownStatus;
  /** Set when the file's status disagrees with the evidence. */
  warning: string | null;
}

export function jobView(job: Job): JobView {
  const last = lastAttempt(job);
  const evidenceVerified = !!last && attemptOutcome(last) === 'verified';
  if (job.status === 'verified' && !evidenceVerified) {
    return {
      shown: 'unconfirmed',
      warning:
        'The results file says this job is verified, but its latest attempt did not pass every ' +
        'table on both dev and holdout data. The dashboard does not show it as verified.',
    };
  }
  if (job.status === 'not_started' && job.attempts.length > 0) {
    return { shown: 'in_progress', warning: 'The results file says "not started" but lists attempts.' };
  }
  return { shown: job.status, warning: null };
}

export function holdoutState(job: Job): 'passed' | 'failed' | 'not_run' {
  for (let i = job.attempts.length - 1; i >= 0; i--) {
    const h = job.attempts[i].runs.holdout;
    if (!h) continue;
    const s = summarizeRun(h);
    if (s.failed > 0) return 'failed';
    if (allPass(h)) return 'passed';
  }
  return 'not_run';
}

/** "rows wrong" for a table: answer-key rows with no identical twin in the new output. */
export function rowsWrong(t: TableResult): { a: number; b: number } {
  const r = t.result;
  if (!r) return { a: 0, b: 0 };
  return { a: t.counts?.only_a ?? r.only_a.length, b: t.counts?.only_b ?? r.only_b.length };
}

export function changedCount(t: TableResult): number {
  return t.counts?.changed ?? t.result?.explanation?.changed.length ?? 0;
}

/** Columns that appear in the shown cell-level differences, most frequent first. */
export function changedColumns(t: TableResult): string[] {
  const counts = new Map<string, number>();
  for (const c of t.result?.explanation?.changed ?? []) counts.set(c.col, (counts.get(c.col) ?? 0) + 1);
  return [...counts.entries()].sort((x, y) => y[1] - x[1]).map(([col]) => col);
}

// ---------------------------------------------------------------------------
// Plain-language text
// ---------------------------------------------------------------------------

const nf = new Intl.NumberFormat('en-US');
export const num = (n: number) => nf.format(n);
export const plural = (n: number, one: string, many = one + 's') => `${num(n)} ${n === 1 ? one : many}`;

export function formatCell(v: Cell): string {
  if (v === null) return 'NULL';
  // Shown exactly as stored: IDs and keys must not get thousands separators
  if (typeof v === 'number') return String(v);
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return v;
}

export function seconds(s: number | null | undefined): string {
  if (s == null) return '-';
  if (s < 60) return `${s.toFixed(0)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

/** The last line of a Python traceback, without the module path, cut to something readable. */
export function errorLine(error: string): string {
  const lines = error.trim().split('\n').filter((l) => l.trim());
  let last = lines[lines.length - 1] ?? error;
  last = last.replace(/^[\w.]+\.(\w+(Exception|Error)):/, '$1:');
  last = last.replace(/\s*Please check the current catalog.*$/, '');
  last = last.replace(/\[[A-Z_.]+\]\s*/, '').replace('The feature is not supported: ', '');
  last = last.replace(/\s*SQLSTATE: \w+$/, '');
  return last;
}

function failingTables(run: Run | null): TableResult[] {
  return (run?.tables ?? []).filter((t) => tableVerdict(t) === 'fail');
}

function describeFailure(t: TableResult): string {
  const { a } = rowsWrong(t);
  const cols = changedColumns(t);
  const where = cols.length ? ` in ${cols.join(', ')}` : '';
  return `${plural(a, 'row')} wrong${where}`;
}

/** One short line for the attempt timeline. */
export function attemptHeadline(a: Attempt): string {
  const o = attemptOutcome(a);
  switch (o) {
    case 'crashed':
      return `Crashed: ${errorLine(a.error ?? '')}`;
    case 'mismatch': {
      const bad = failingTables(a.runs.dev);
      return `${bad[0].table}: ${describeFailure(bad[0])}` + (bad.length > 1 ? ` (+${plural(bad.length - 1, 'more table')})` : '');
    }
    case 'incomplete': {
      const s = summarizeRun(a.runs.dev);
      return `${s.compared} of ${s.tables} tables compared, all match`;
    }
    case 'passed_dev':
      return 'Matched every row on dev data';
    case 'failed_holdout': {
      const bad = failingTables(a.runs.holdout);
      return `Matched dev, but on holdout ${bad[0].table}: ${describeFailure(bad[0])}`;
    }
    case 'verified':
      return 'Matched every row on dev and holdout data';
  }
}

export const OUTCOME_LABEL: Record<Outcome, string> = {
  crashed: 'Crashed',
  mismatch: 'Wrong values',
  incomplete: 'Partly checked',
  passed_dev: 'Passed dev',
  failed_holdout: 'Failed holdout',
  verified: 'Passed',
};

/** The one big sentence at the top of a job page. */
export function verdictSentence(job: Job): string {
  const v = jobView(job);
  const last = lastAttempt(job);
  const n = job.attempts.length;
  switch (v.shown) {
    case 'not_started':
      return 'Not started. No translation of this job has been checked yet.';
    case 'unconfirmed':
      return 'Not verified. The file claims it is, but the evidence below does not back that up.';
    case 'verified': {
      const dev = summarizeRun(last!.runs.dev);
      const hold = summarizeRun(last!.runs.holdout);
      return (
        `Verified. On attempt ${last!.number}, the new code gave exactly the same output as the old system: ` +
        `${num(dev.rowsCompared)} rows on dev data and ${num(hold.rowsCompared)} rows on holdout data the AI never saw.`
      );
    }
    case 'failed': {
      if (last && attemptOutcome(last) === 'failed_holdout') {
        const bad = failingTables(last.runs.holdout);
        const w = rowsWrong(bad[0]).a;
        return (
          `Not verified. The new code matched on dev data, but got ${plural(w, 'row')} of ${bad[0].table} wrong ` +
          `on holdout data the AI never saw.`
        );
      }
      return `Not verified. After ${plural(n, 'attempt')} the new code still doesn't match the old system.`;
    }
    case 'retrying':
      return `Not there yet. Attempt ${n} didn't match the old system, and the AI is trying again with the differences.`;
    case 'in_progress': {
      if (!last) return 'In progress. Nothing has been compared yet.';
      const s = summarizeRun(last.runs.dev);
      if (s.failed > 0) return `In progress. ${s.failed} of ${s.tables} tables differ from the old system so far.`;
      return (
        `Partly checked. ${s.compared} of ${s.tables} tables compared so far, and ${s.compared === 1 ? 'it matches' : 'all match'} ` +
        `the old system exactly (${plural(s.rowsCompared, 'row')}). The rest haven't been compared yet.`
      );
    }
  }
}

export const STATUS_LABEL: Record<ShownStatus, string> = {
  verified: 'Verified',
  failed: 'Failed',
  retrying: 'Retrying',
  in_progress: 'In progress',
  not_started: 'Not started',
  unconfirmed: 'Unconfirmed',
};

export interface Headline {
  verified: number;
  total: number;
}

export function headline(file: ResultsFile): Headline {
  return { verified: file.jobs.filter((j) => jobView(j).shown === 'verified').length, total: file.jobs.length };
}

export interface Totals {
  attempts: number;
  tablesChecked: number;
  rowsCompared: number;
  ignoredCols: number;
}

/** Totals across all jobs: attempts ever made, and the latest attempt's dev + holdout checks. */
export function totals(file: ResultsFile): Totals {
  const t: Totals = { attempts: 0, tablesChecked: 0, rowsCompared: 0, ignoredCols: 0 };
  for (const job of file.jobs) {
    t.attempts += job.attempts.length;
    const last = lastAttempt(job);
    if (!last) continue;
    for (const run of [last.runs.dev, last.runs.holdout]) {
      const s = summarizeRun(run);
      t.tablesChecked += s.compared;
      t.rowsCompared += s.rowsCompared;
    }
    t.ignoredCols += (last.runs.dev?.tables ?? []).reduce((n, tr) => n + tr.ignored.length, 0);
  }
  return t;
}

// ---------------------------------------------------------------------------
// Whole-row pairing, for reading only
// ---------------------------------------------------------------------------

export interface RowPair {
  a: Cell[] | null;
  b: Cell[] | null;
  /** Indexes into compared_cols where a and b differ. */
  diff: number[];
}

/**
 * Lines up each shown "only in old" row with the most similar shown "only in new" row, so a person
 * can see which cells differ. This never affects a verdict: reconcile() already decided, and these
 * rows are only the examples kept in the file.
 */
export function pairRows(onlyA: Cell[][], onlyB: Cell[][]): RowPair[] {
  const free = onlyB.map((_, i) => i);
  const pairs: RowPair[] = [];
  for (const a of onlyA) {
    let best = -1;
    let bestDiff: number[] = [];
    for (const i of free) {
      const d = a.map((v, c) => (v === onlyB[i][c] ? -1 : c)).filter((c) => c >= 0);
      if (best === -1 || d.length < bestDiff.length) {
        best = i;
        bestDiff = d;
      }
    }
    // Only call it a pair if most of the row agrees; otherwise show it alone.
    if (best !== -1 && bestDiff.length <= Math.max(1, Math.floor(a.length / 3))) {
      free.splice(free.indexOf(best), 1);
      pairs.push({ a, b: onlyB[best], diff: bestDiff });
    } else {
      pairs.push({ a, b: null, diff: [] });
    }
  }
  for (const i of free) pairs.push({ a: null, b: onlyB[i], diff: [] });
  return pairs;
}
