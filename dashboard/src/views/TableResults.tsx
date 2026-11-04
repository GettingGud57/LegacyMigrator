import { useState } from 'react';
import type { Cell, Dataset, Run, TableResult } from '../types';
import {
  changedColumns, changedCount, formatCell, num, pairRows, plural, rowsWrong, seconds, summarizeRun, tableVerdict,
} from '../model';
import { Icon, TableVerdictTag } from '../ui';

/** Every table of one run (dev or holdout), failing tables first and opened. */
export function RunTables({ run, dataset, kind }: { run: Run; dataset: Dataset; kind: 'dev' | 'holdout' }) {
  const s = summarizeRun(run);
  const order = { fail: 0, pass: 1, not_compared: 2 };
  const tables = [...run.tables].sort((a, b) => order[tableVerdict(a)] - order[tableVerdict(b)]);
  return (
    <section className={`run run-${kind}`} aria-label={dataset.label}>
      <header className="run-head">
        <h3>
          {kind === 'holdout' && <Icon name="lock" size={18} />}
          {dataset.label}
          <span className={`ai-sees ${dataset.ai_can_see ? '' : 'ai-blind'}`}>
            <Icon name={dataset.ai_can_see ? 'eye' : 'lock'} size={13} />
            {dataset.ai_can_see ? 'AI sees the differences' : 'AI never sees this data'}
          </span>
        </h3>
        <p className="muted">
          {s.passed} of {s.tables} tables match{s.failed ? `, ${s.failed} differ` : ''}
          {s.compared < s.tables ? `, ${s.tables - s.compared} not compared yet` : ''} · {num(s.rowsCompared)} rows
          compared{run.seconds != null ? ` · ${seconds(run.seconds)}` : ''}
        </p>
      </header>
      <ul className="tables">
        {tables.map((t) => <TableRow key={t.table} t={t} />)}
      </ul>
    </section>
  );
}

function TableRow({ t }: { t: TableResult }) {
  const v = tableVerdict(t);
  const [open, setOpen] = useState(v === 'fail');
  const r = t.result;
  const wrong = rowsWrong(t);
  return (
    <li className={`table-row v-${v}`}>
      <button className="table-line" aria-expanded={open} onClick={() => setOpen(!open)} disabled={v === 'not_compared' && !t.ignored.length}>
        <TableVerdictTag verdict={v} />
        <code className="tname">{t.table}</code>
        <span className="tstat">
          {v === 'not_compared' && <span className="muted">{t.rows_legacy != null ? `${num(t.rows_legacy)} rows waiting` : 'waiting'}</span>}
          {v === 'pass' && <>{num(t.rows_legacy ?? 0)} rows · {r!.compared_cols.length} columns, all identical</>}
          {v === 'fail' && <span className="bad">{plural(wrong.a, 'row')} of {num(t.rows_legacy ?? 0)} wrong</span>}
          {t.ignored.length > 0 && <span className="ign-chip" title="Columns left out of the comparison">{t.ignored.length} ignored</span>}
        </span>
        <span className="chev" aria-hidden>{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="table-detail">
          {v === 'fail' && <Mismatches t={t} />}
          {v === 'pass' && (
            <p>
              Every one of the {num(t.rows_legacy ?? 0)} rows the old system produced has an identical twin in the new
              output, across all {r!.compared_cols.length} compared columns, and there are no extra rows.
            </p>
          )}
          {v === 'not_compared' && <p className="muted">Not compared yet. Planned check below.</p>}
          <Ignored t={t} />
        </div>
      )}
    </li>
  );
}

export function Ignored({ t }: { t: TableResult }) {
  if (!t.ignored.length) return null;
  return (
    <div className="ignored">
      <h4>Left out of the comparison</h4>
      <ul>
        {t.ignored.map((i) => (
          <li key={i.column}><code>{i.column}</code> <span>{i.reason}</span></li>
        ))}
      </ul>
    </div>
  );
}

function keyText(keyCols: string[] | null, key: Cell[]): string {
  if (!keyCols) return key.map(formatCell).join(', ');
  return keyCols.map((k, i) => `${k} ${formatCell(key[i])}`).join(', ');
}

/** The differences in plain words first, then the raw rows. */
function Mismatches({ t }: { t: TableResult }) {
  const r = t.result!;
  const changes = r.explanation?.changed ?? [];
  const wrong = rowsWrong(t);
  const total = changedCount(t);
  const cols = changedColumns(t);
  return (
    <div className="mismatch">
      <p className="mismatch-lead">
        <strong>{plural(wrong.a, 'row')}</strong> of the old system's output {wrong.a === 1 ? 'has' : 'have'} no identical
        row in the new output, and the new output has <strong>{plural(wrong.b, 'row')}</strong> the old one doesn't.
        {cols.length > 0 && <> The differences are in <strong>{cols.join(', ')}</strong>.</>}
      </p>
      {r.cols_only_a.length > 0 && <p className="bad">Columns missing from the new output: {r.cols_only_a.join(', ')}</p>}
      {r.cols_only_b.length > 0 && <p className="bad">Extra columns in the new output: {r.cols_only_b.join(', ')}</p>}

      {changes.length > 0 && (
        <>
          <h4>Examples {total > changes.length && <span className="muted">(showing {changes.length} of {num(total)})</span>}</h4>
          <ul className="changes">
            {changes.map((c, i) => (
              <li key={i}>
                <span className="ch-key">{keyText(t.key_cols, c.key)}</span>
                <span className="ch-col">{c.col}</span>
                <span className="ch-vals">
                  <span className="ch-old"><span className="ch-who">old system said</span> <b>{formatCell(c.a)}</b></span>
                  <span className="ch-new"><span className="ch-who">new code said</span> <b>{formatCell(c.b)}</b></span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <WholeRows t={t} />
    </div>
  );
}

/** The rows reconcile() found with no twin, lined up so the differing cells stand out. */
function WholeRows({ t }: { t: TableResult }) {
  const r = t.result!;
  const [open, setOpen] = useState(!r.explanation);
  if (!r.only_a.length && !r.only_b.length) return null;
  const pairs = pairRows(r.only_a, r.only_b);
  const total = Math.max(rowsWrong(t).a, rowsWrong(t).b);
  // Show the columns that differ first, then the rest, so the eye lands on the problem.
  const diffCols = new Set(pairs.flatMap((p) => p.diff));
  const colOrder = [...r.compared_cols.keys()].sort((a, b) => Number(diffCols.has(b)) - Number(diffCols.has(a)));
  return (
    <details className="whole" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>
        Whole rows with no identical twin
        <span className="muted"> ({r.only_a.length + r.only_b.length} kept as examples{total > r.only_a.length ? ` of ${num(total)} per side` : ''})</span>
      </summary>
      <p className="muted small">
        These are the rows that decided the verdict. To make them easier to read, each old row is shown next to the
        most similar new row, and the cells that differ are marked. That pairing is only for reading; it doesn't
        change the verdict.
      </p>
      <div className="grid-scroll" tabIndex={0}>
        <table className="rows">
          <thead>
            <tr>
              <th scope="col">Side</th>
              {colOrder.map((c) => <th key={c} scope="col" className={diffCols.has(c) ? 'is-diff' : ''}>{r.compared_cols[c]}</th>)}
            </tr>
          </thead>
          <tbody>
            {pairs.map((p, i) => (
              <PairRows key={i} pair={p} colOrder={colOrder} />
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PairRows({ pair, colOrder }: { pair: ReturnType<typeof pairRows>[number]; colOrder: number[] }) {
  const d = new Set(pair.diff);
  return (
    <>
      {pair.a && (
        <tr className={`side-a ${pair.b ? 'paired' : ''}`}>
          <th scope="row">Old</th>
          {colOrder.map((c) => <td key={c} className={d.has(c) ? 'cell-diff' : ''}>{formatCell(pair.a![c])}</td>)}
        </tr>
      )}
      {pair.b && (
        <tr className={`side-b ${pair.a ? 'paired' : ''}`}>
          <th scope="row">New</th>
          {colOrder.map((c) => <td key={c} className={d.has(c) ? 'cell-diff' : ''}>{formatCell(pair.b![c])}</td>)}
        </tr>
      )}
    </>
  );
}
