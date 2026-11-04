import { useEffect, useRef, useState } from 'react';
import type { ResultsFile } from '../types';
import {
  attemptHeadline, attemptOutcome, headline, holdoutState, jobView, lastAttempt, num, summarizeRun, totals,
} from '../model';
import { href } from '../router';
import { HoldoutBadge, Icon, OutcomeMark, StatusPill } from '../ui';

export function Overview({ data }: { data: ResultsFile }) {
  const h = headline(data);
  const t = totals(data);
  const [sel, setSel] = useState(-1);
  const rows = useRef<(HTMLAnchorElement | null)[]>([]);

  // j/k or arrows move through the job list, Enter opens (the rows are links, so Enter just works)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement).closest('input, textarea, select')) return;
      const n = data.jobs.length;
      let next = -1;
      if (e.key === 'ArrowDown' || e.key === 'j') next = sel < 0 ? 0 : Math.min(n - 1, sel + 1);
      else if (e.key === 'ArrowUp' || e.key === 'k') next = sel < 0 ? 0 : Math.max(0, sel - 1);
      else return;
      e.preventDefault();
      setSel(next);
      rows.current[next]?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [sel, data.jobs.length]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">Legacy SQL Server jobs being migrated to PySpark, each checked row for row against the old system's real output.</p>
        </div>
      </header>

      <section className="stats" aria-label="Totals">
        <div className="stat stat-main">
          <span className="stat-label">Verified on holdout data</span>
          <span className="stat-value" id="headline">
            <span className="headline-num">{h.verified}</span><span className="stat-of"> / {h.total} jobs</span>
          </span>
          <HeadlineBar data={data} />
          <span className="stat-note">Matched every row on dev data and on data the AI never saw</span>
        </div>
        <Kpi value={num(t.attempts)} label="Attempts" />
        <Kpi value={num(t.tablesChecked)} label="Table checks" />
        <Kpi value={num(t.rowsCompared)} label="Rows compared" />
        <Kpi value={num(t.ignoredCols)} label="Ignored columns" />
      </section>

      <section aria-labelledby="jobs-title">
        <div className="section-head">
          <h2 id="jobs-title">Jobs <span className="count">{data.jobs.length}</span></h2>
          <p className="muted small">Open a job to see each attempt and the rows that decided it · <kbd>j</kbd> <kbd>k</kbd> to move</p>
        </div>
        <div className="jobs" role="list">
          <div className="jobs-head" aria-hidden>
            <span>Job</span><span>Status</span><span>Attempts</span><span>Tables matched</span><span>Rows compared</span><span>Holdout</span>
          </div>
          {data.jobs.map((job, i) => {
            const v = jobView(job);
            const last = lastAttempt(job);
            const dev = summarizeRun(last?.runs.dev ?? null);
            const hold = summarizeRun(last?.runs.holdout ?? null);
            return (
              <a
                key={job.id}
                role="listitem"
                ref={(el) => { rows.current[i] = el; }}
                className={`job-row ${sel === i ? 'is-sel' : ''}`}
                href={href({ page: 'job', jobId: job.id, attempt: null, tab: 'results' })}
                onFocus={() => setSel(i)}
              >
                <span className="job-name">
                  <strong>{job.name}</strong>
                  <code className="proc">{job.proc}</code>
                  {last && <span className="job-last muted">Latest: {attemptHeadline(last)}</span>}
                  {!last && <span className="job-last muted">{job.summary}</span>}
                </span>
                <span className="cell" data-label="Status">
                  <StatusPill status={v.shown} />
                  {v.warning && <span className="warn-dot" title={v.warning}><Icon name="warn" size={15} title="Status not backed by evidence" /></span>}
                </span>
                <span className="cell" data-label="Attempts">
                  {job.attempts.length === 0 ? <span className="muted">none yet</span> : (
                    <span className="dots" aria-label={job.attempts.map((a) => `attempt ${a.number}: ${attemptOutcome(a)}`).join(', ')}>
                      {job.attempts.map((a) => <OutcomeMark key={a.number} outcome={attemptOutcome(a)} size={14} />)}
                      <span className="dots-n">{job.attempts.length}{job.max_attempts ? ` / ${job.max_attempts}` : ''}</span>
                    </span>
                  )}
                </span>
                <span className="cell num" data-label="Tables matched">
                  {dev.tables ? <span>{dev.passed} <span className="muted">/ {dev.tables}</span></span> : <span className="muted">-</span>}
                </span>
                <span className="cell num" data-label="Rows compared">
                  {dev.rowsCompared + hold.rowsCompared ? num(dev.rowsCompared + hold.rowsCompared) : <span className="muted">-</span>}
                </span>
                <span className="cell" data-label="Holdout"><HoldoutBadge state={holdoutState(job)} compact /></span>
                <span className="row-go" aria-hidden><Icon name="arrow" /></span>
              </a>
            );
          })}
        </div>
        <p className="muted small legend">
          <OutcomeMark outcome="crashed" size={13} /> crashed · <OutcomeMark outcome="mismatch" size={13} /> wrong values ·{' '}
          <OutcomeMark outcome="verified" size={13} /> matched. Tables matched and rows are from each job's latest
          attempt; rows count the old system's output on dev plus holdout data.
        </p>
      </section>

    </div>
  );
}

function Kpi({ value, label }: { value: string; label: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

/** One segment per job, in status order: the headline as a picture. */
function HeadlineBar({ data }: { data: ResultsFile }) {
  const order = ['verified', 'unconfirmed', 'in_progress', 'retrying', 'failed', 'not_started'];
  const jobs = [...data.jobs].sort((a, b) => order.indexOf(jobView(a).shown) - order.indexOf(jobView(b).shown));
  return (
    <div className="hbar" aria-hidden>
      {jobs.map((j) => (
        <a key={j.id} className={`hbar-seg tone-${jobView(j).shown}`} href={href({ page: 'job', jobId: j.id, attempt: null, tab: 'results' })} tabIndex={-1}>
          <span>{j.name}</span>
        </a>
      ))}
    </div>
  );
}
