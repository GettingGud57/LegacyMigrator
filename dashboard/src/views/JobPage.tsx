import { useEffect } from 'react';
import type { Attempt, Job, ResultsFile, TableResult } from '../types';
import {
  OUTCOME_LABEL, attemptHeadline, attemptOutcome, errorLine, holdoutState, jobView, num, seconds, tableVerdict,
  verdictSentence,
} from '../model';
import { TABS, go, href, type Route, type Tab } from '../router';
import { HoldoutBadge, Icon, OUTCOME_TONE, OutcomeMark, StatusPill, TableVerdictTag } from '../ui';
import { CodeView } from './CodeView';
import { Ignored, RunTables } from './TableResults';

type JobRoute = Extract<Route, { page: 'job' }>;

const TAB_LABEL: Record<Tab, string> = { results: 'Results', code: 'Code', evidence: 'Evidence', lineage: 'Lineage' };

export function JobPage({ data, route }: { data: ResultsFile; route: JobRoute }) {
  const index = data.jobs.findIndex((j) => j.id === route.jobId);
  const job = data.jobs[index];
  const attempt = job && (route.attempt ? job.attempts[route.attempt - 1] : job.attempts[job.attempts.length - 1]);
  const number = attempt?.number ?? null;
  const tabs = TABS.filter((t) => t !== 'lineage' || job?.lineage?.length);

  useEffect(() => {
    if (!job) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement).closest('input, textarea, select')) return;
      const to = (r: Partial<JobRoute>) => go({ page: 'job', jobId: job.id, attempt: number, tab: route.tab, ...r });
      const n = job.attempts.length;
      if (e.key === 'ArrowLeft' && number && number > 1) to({ attempt: number - 1 });
      else if (e.key === 'ArrowRight' && number && number < n) to({ attempt: number + 1 });
      else if (e.key === '[' && index > 0) go({ page: 'job', jobId: data.jobs[index - 1].id, attempt: null, tab: 'results' });
      else if (e.key === ']' && index < data.jobs.length - 1) go({ page: 'job', jobId: data.jobs[index + 1].id, attempt: null, tab: 'results' });
      else if (/^[1-4]$/.test(e.key) && tabs[Number(e.key) - 1]) to({ tab: tabs[Number(e.key) - 1] });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [job, number, route.tab, index, data.jobs, tabs]);

  if (!job) {
    return (
      <div className="page">
        <p>No job called <code>{route.jobId}</code> in this results file. <a href="#/">Back to all jobs</a></p>
      </div>
    );
  }

  const v = jobView(job);
  const tab = tabs.includes(route.tab) ? route.tab : 'results';

  return (
    <div className="page job-page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <a href="#/"><Icon name="back" size={15} /> All jobs</a>
        <span className="muted">{index + 1} of {data.jobs.length}</span>
      </nav>

      <header className="job-head">
        <div>
          <h1>{job.name}</h1>
          <p className="job-meta"><code>{job.proc}</code>{job.source_file && <span className="muted"> · {job.source_file}</span>}</p>
          {job.summary && <p className="job-summary">{job.summary}</p>}
        </div>
        <StatusPill status={v.shown} big />
      </header>

      {v.warning && (
        <div className="callout callout-warn" role="alert"><Icon name="warn" /> <span>{v.warning}</span></div>
      )}

      <section className={`verdict tone-${v.shown}`} aria-label="Verdict">
        <p className="verdict-text">{verdictSentence(job)}</p>
        <div className="verdict-foot">
          <HoldoutBadge state={holdoutState(job)} />
          {job.stop_reason && <span className="muted">{job.stop_reason}</span>}
        </div>
      </section>

      {job.attempts.length > 0 && attempt && (
        <>
          <Timeline job={job} current={attempt.number} tab={tab} />

          <div className="tabs" role="tablist" aria-label="Attempt details">
            {tabs.map((t, i) => (
              <a
                key={t}
                role="tab"
                aria-selected={tab === t}
                href={href({ page: 'job', jobId: job.id, attempt: route.attempt, tab: t })}
                className="tab"
              >
                {TAB_LABEL[t]} <kbd className="hide-phone">{i + 1}</kbd>
              </a>
            ))}
          </div>

          <div className="tab-body" role="tabpanel">
            {tab === 'results' && <ResultsTab data={data} job={job} attempt={attempt} />}
            {tab === 'code' && <CodeView job={job} attempt={attempt} />}
            {tab === 'evidence' && <EvidenceTab attempt={attempt} />}
            {tab === 'lineage' && <LineageTab job={job} />}
          </div>
        </>
      )}

      {job.attempts.length === 0 && <NotStarted job={job} />}
    </div>
  );
}

/** The demo moment: the AI gets it wrong, the system catches it, the fix gets verified. */
function Timeline({ job, current, tab }: { job: Job; current: number; tab: Tab }) {
  return (
    <section className="timeline-wrap" aria-labelledby="tl-title">
      <div className="section-head">
        <h2 id="tl-title">Attempts</h2>
        <p className="muted hide-phone">Use ← → to step through</p>
      </div>
      <ol className="timeline">
        {job.attempts.map((a, i) => {
          const o = attemptOutcome(a);
          const next = job.attempts[i + 1];
          return (
            <li key={a.number} className="tl-item">
              <a
                className={`tl-node tone-${OUTCOME_TONE[o]} ${a.number === current ? 'is-current' : ''}`}
                href={href({ page: 'job', jobId: job.id, attempt: a.number, tab })}
                aria-current={a.number === current ? 'step' : undefined}
              >
                <span className="tl-top">
                  <span className="tl-n">Attempt {a.number}</span>
                  <span className="tl-time muted">{seconds(a.seconds)}</span>
                </span>
                <span className="tl-outcome"><OutcomeMark outcome={o} size={18} /> {OUTCOME_LABEL[o]}</span>
                <span className="tl-line">{attemptHeadline(a)}</span>
                <span className="tl-checks">
                  <RunChip label="Dev" run={a.runs.dev} />
                  <RunChip label="Holdout" run={a.runs.holdout} lock />
                </span>
              </a>
              {next && (
                <span className="tl-link" aria-hidden>
                  <span className="tl-link-line" />
                  <span className="tl-link-text">{!a.feedback ? 'retried' : o === 'crashed' ? 'error sent back' : 'differences sent back'}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function RunChip({ label, run, lock = false }: { label: string; run: Attempt['runs']['dev']; lock?: boolean }) {
  let state: 'pass' | 'fail' | 'none' | 'part' = 'none';
  if (run) {
    const vs = run.tables.map(tableVerdict);
    state = vs.includes('fail') ? 'fail' : vs.every((x) => x === 'pass') ? 'pass' : 'part';
  }
  const text = { pass: 'match', fail: 'differs', none: 'not run', part: 'partial' }[state];
  return (
    <span className={`run-chip rc-${state}`}>
      {lock && <Icon name="lock" size={12} />}
      {label}: {text}
    </span>
  );
}

function ResultsTab({ data, job, attempt }: { data: ResultsFile; job: Job; attempt: Attempt }) {
  const o = attemptOutcome(attempt);
  return (
    <div className="results-tab">
      <p className="attempt-lead">
        <OutcomeMark outcome={o} /> <strong>Attempt {attempt.number}: {OUTCOME_LABEL[o].toLowerCase()}.</strong>{' '}
        {attemptHeadline(attempt)}.
        {attempt.started_at && <span className="muted"> Started {new Date(attempt.started_at).toUTCString().replace(' GMT', ' UTC')}.</span>}
      </p>

      {attempt.error && (
        <div className="error-box">
          <p className="error-title">
            <Icon name="crash" /> It crashed{attempt.error_stage ? ` while ${attempt.error_stage}` : ''}, so there was nothing to compare.
          </p>
          <p className="error-line"><code>{errorLine(attempt.error)}</code></p>
          <details>
            <summary>Full error</summary>
            <pre className="trace">{attempt.error}</pre>
          </details>
        </div>
      )}

      {/* keyed by attempt so failing tables open fresh each time you switch attempts */}
      {attempt.runs.dev && <RunTables key={`d${attempt.number}`} run={attempt.runs.dev} dataset={data.datasets.dev} kind="dev" />}
      {attempt.runs.holdout && <RunTables key={`h${attempt.number}`} run={attempt.runs.holdout} dataset={data.datasets.holdout} kind="holdout" />}
      {!attempt.error && attempt.runs.dev && !attempt.runs.holdout && (
        <p className="muted holdout-wait">
          <Icon name="lock" size={15} /> Holdout data is only checked once an attempt matches every table on dev data.
        </p>
      )}

      {attempt.feedback && (
        <div className="feedback">
          <h3>What the AI was told for attempt {attempt.number + 1}</h3>
          <p className="muted small">Word for word. Feedback only ever describes dev data, never holdout.</p>
          <pre>{attempt.feedback}</pre>
        </div>
      )}
      {!attempt.feedback && attempt.number < job.attempts.length && (
        <p className="muted">No feedback was recorded for this attempt.</p>
      )}
    </div>
  );
}

function EvidenceTab({ attempt }: { attempt: Attempt }) {
  const runs = (['dev', 'holdout'] as const).filter((k) => attempt.runs[k]);
  return (
    <div className="evidence">
      <section className="panel how-decided">
        <h3>How the verdict is decided</h3>
        <ol>
          <li>Both versions start from the same snapshot of every table the job touches (<code>snapshots/&lt;job&gt;/before/</code>).</li>
          <li>The old procedure runs on SQL Server and its output is saved: that's the answer key (<code>after/</code>). The new PySpark code runs on the same snapshot (<code>spark/</code>).</li>
          <li>
            For each table, <code>diff.reconcile()</code> turns every row into a tuple of the compared columns and counts them
            on each side, like two bags of marbles. A table passes only if both bags hold exactly the same rows, the
            same number of times each, and neither side has extra columns. Row order doesn't matter; duplicates do.
          </li>
          <li>Key columns are never used to decide. They only help explain a failure by pairing rows up.</li>
          <li>A column is only left out if it can't match even between two runs of the old job itself, and each one says why.</li>
        </ol>
        <p className="muted small">
          Passing means old and new agreed on every row of every dataset tested. It isn't a mathematical proof that
          the two programs are the same on all possible data, which is why there is a holdout set.
        </p>
      </section>

      {runs.length === 0 && <p className="muted">This attempt crashed before any comparison ran.</p>}
      {runs.map((k) => (
        <section key={k} className="ev-run">
          <h3>{k === 'dev' ? 'Dev data' : 'Holdout data'}</h3>
          {attempt.runs[k]!.tables.map((t) => <EvidenceTable key={t.table} t={t} />)}
        </section>
      ))}
    </div>
  );
}

function EvidenceTable({ t }: { t: TableResult }) {
  const r = t.result;
  return (
    <article className="ev-table">
      <header>
        <TableVerdictTag verdict={tableVerdict(t)} />
        <code className="tname">{t.table}</code>
        <span className="muted">
          old {t.rows_legacy != null ? num(t.rows_legacy) : '?'} rows · new {t.rows_spark != null ? num(t.rows_spark) : '?'} rows
        </span>
      </header>
      {r ? (
        <>
          <p className="small"><strong>{r.compared_cols.length} columns compared:</strong></p>
          <ul className="chips">{r.compared_cols.map((c) => <li key={c}>{c}</li>)}</ul>
          <p className="small muted">
            Pairing key for explanations: {t.key_cols ? t.key_cols.join(', ') : 'none (no stable key, so differences are shown as whole rows)'}.
            {' '}Rows with no twin: {num(t.counts?.only_a ?? r.only_a.length)} old, {num(t.counts?.only_b ?? r.only_b.length)} new.
          </p>
        </>
      ) : (
        <p className="small muted">Not compared yet.</p>
      )}
      <Ignored t={t} />
      <details className="raw">
        <summary>Raw result from the file</summary>
        <pre>{JSON.stringify(t, null, 2)}</pre>
      </details>
    </article>
  );
}

function LineageTab({ job }: { job: Job }) {
  const byTable = new Map<string, NonNullable<Job['lineage']>>();
  for (const l of job.lineage ?? []) byTable.set(l.table, [...(byTable.get(l.table) ?? []), l]);
  return (
    <div className="lineage">
      <p className="callout"><Icon name="warn" size={16} /> <span>Derived by hand from the legacy SQL. The planned lineage step will generate this automatically.</span></p>
      {[...byTable.entries()].map(([table, cols]) => (
        <section key={table} className="lin-table">
          <h3><code>{table}</code></h3>
          <ul>
            {cols.map((c) => (
              <li key={c.column} className="lin-row">
                <div className="lin-src">
                  {c.sources.length ? c.sources.map((s) => <code key={s}>{s}</code>) : <span className="muted">computed in the job</span>}
                </div>
                <div className="lin-arrow" aria-hidden><Icon name="arrow" size={16} /></div>
                <div className="lin-col"><strong>{c.column}</strong><span className="muted">{c.rule}</span></div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function NotStarted({ job }: { job: Job }) {
  return (
    <section className="panel">
      <h2>Legacy code waiting to be translated</h2>
      <p className="muted">Nothing has been translated or compared yet. This is the old procedure the AI will work from.</p>
      <CodeView job={job} attempt={{ number: 0, code: '# not translated yet', started_at: null, seconds: null, error: null, runs: { dev: null, holdout: null } }} />
    </section>
  );
}
