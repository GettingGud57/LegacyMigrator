// The results file, as described in docs/results-contract.md (contract version 1).
// Field names match the JSON exactly, so this file doubles as a checklist for loop.py.

export type JobStatus = 'verified' | 'failed' | 'retrying' | 'in_progress' | 'not_started';

/** A single cell value after json.dump(..., default=str): Decimals and datetimes arrive as text. */
export type Cell = string | number | boolean | null;

export interface ResultsFile {
  contract_version: number;
  sample: boolean;
  generated_at: string;
  title?: string;
  notes?: string[];
  datasets: { dev: Dataset; holdout: Dataset };
  jobs: Job[];
}

export interface Dataset {
  label: string;
  ai_can_see: boolean;
  description: string;
}

export interface Job {
  id: string;
  name: string;
  proc: string;
  source_file?: string;
  summary?: string;
  status: JobStatus;
  stop_reason?: string | null;
  max_attempts?: number | null;
  legacy_sql: string;
  attempts: Attempt[];
  lineage?: LineageEntry[];
}

export interface Attempt {
  number: number;
  started_at: string | null;
  seconds: number | null;
  code: string;
  error: string | null;
  error_stage?: string | null;
  feedback?: string | null;
  runs: { dev: Run | null; holdout: Run | null };
}

export interface Run {
  tables: TableResult[];
  seconds?: number;
}

export interface TableResult {
  table: string;
  key_cols: string[] | null;
  ignored: { column: string; reason: string }[];
  rows_legacy: number | null;
  rows_spark: number | null;
  /** Exactly what diff.reconcile() returned, long lists cut short. null = not compared yet. */
  result: ReconcileResult | null;
  /** Full list sizes before they were cut. */
  counts?: { only_a?: number; only_b?: number; changed?: number };
}

export interface ReconcileResult {
  status: 'pass' | 'fail';
  compared_cols: string[];
  only_a: Cell[][];
  only_b: Cell[][];
  cols_only_a: string[];
  cols_only_b: string[];
  explanation: Explanation | null;
}

export interface Explanation {
  cols_only_a: string[];
  cols_only_b: string[];
  rows_only_a: Cell[][];
  rows_only_b: Cell[][];
  changed: { key: Cell[]; col: string; a: Cell; b: Cell }[];
  dupes_a: Cell[][];
  dupes_b: Cell[][];
}

export interface LineageEntry {
  table: string;
  column: string;
  sources: string[];
  rule: string;
}

export interface Manifest {
  default: string;
  files: { id: string; label: string; path: string }[];
}
