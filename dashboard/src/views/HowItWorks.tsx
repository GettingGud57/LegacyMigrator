import { useMemo, useState } from 'react';
import type { ResultsFile } from '../types';
import { highlightLines } from '../code';
import { Icon } from '../ui';

/** Output of scripts/sqlglot_probe.py */
export interface Probe {
  summary: { sqlglot_version: string; statements: number; sqlglot_succeeded: number; spark_parse_rejected: number; note: string };
  statements: { file: string; kind: string; tsql: string; transpiled: string | null; sqlglot_error: string | null; spark_error: string | null }[];
}

const STEPS = [
  {
    title: 'The old job',
    body: 'Every night a company runs hundreds of old SQL Server jobs that fill its report tables. We take one, plus a snapshot of every table it reads or writes.',
    tag: 'T-SQL',
  },
  {
    title: 'AI translation',
    body: 'An AI rewrites the job for Spark, the platform the company is moving to. It sees the old code and the table layouts. That\'s it.',
    tag: 'PySpark',
  },
  {
    title: 'Same data, both jobs',
    body: 'Both jobs run on the identical starting snapshot. The old job\'s real output is the answer key. Nobody types it in; the old system produces it.',
    tag: 'Run',
  },
  {
    title: 'Compare every row',
    body: 'Every row and column of the new output must match the old one exactly. If not, the differences go back to the AI and it tries again.',
    tag: 'Check',
  },
];

export function HowItWorks({ data, probe }: { data: ResultsFile; probe: Probe | null }) {
  return (
    <div className="page how">
      <section className="hero">
        <p className="eyebrow">How it works</p>
        <h1 className="headline"><span className="headline-text">The AI never grades its own work.</span></h1>
        <p className="hero-sub">
          It's easy to make an AI write code that looks right. The hard part is knowing it <em>is</em> right. So the
          AI only translates. The old system's real output decides.
        </p>
      </section>

      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s.title} className="step">
            <span className="step-n">{i + 1}</span>
            <span className="step-tag">{s.tag}</span>
            <h2>{s.title}</h2>
            <p>{s.body}</p>
          </li>
        ))}
      </ol>

      <FlowDiagram />

      <section className="split">
        <div className="panel">
          <h2><Icon name="eye" /> {data.datasets.dev.label}</h2>
          <p>{data.datasets.dev.description}</p>
        </div>
        <div className="panel panel-lock">
          <h2><Icon name="lock" /> {data.datasets.holdout.label}</h2>
          <p>{data.datasets.holdout.description}</p>
          <p className="muted small">
            Think of it as an exam with questions the student has never seen. Passing the practice test you got
            feedback on proves less than passing that.
          </p>
        </div>
      </section>

      {probe && <TranspilerPanel probe={probe} />}

      <section className="panel">
        <h2>What a pass does and doesn't mean</h2>
        <p>
          A pass means the old and new job produced exactly the same rows on every dataset we tested, including one
          the AI never saw. It isn't a mathematical proof that the two are identical on every possible input (in
          general that can't be proved for any two programs). Before switching off a real legacy job, run both side
          by side on production data for a while.
        </p>
      </section>
    </div>
  );
}

/** Old and new lanes start from one snapshot and meet at the comparison. */
function FlowDiagram() {
  return (
    <figure className="flow">
      <svg viewBox="0 0 880 270" role="img" aria-labelledby="flow-t flow-d">
        <title id="flow-t">How a translation is checked</title>
        <desc id="flow-d">One snapshot of the input tables feeds both the old SQL Server job and the new PySpark job. Their outputs are compared row by row. A mismatch sends dev differences back to the AI; holdout differences never go back.</desc>
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" className="f-arrowhead" />
          </marker>
        </defs>
        <rect x="10" y="80" width="150" height="70" rx="10" className="f-box" />
        <text x="85" y="110" className="f-t">Input snapshot</text>
        <text x="85" y="130" className="f-s">before/</text>

        <rect x="240" y="20" width="210" height="64" rx="10" className="f-box f-old" />
        <text x="345" y="48" className="f-t">Old job, SQL Server</text>
        <text x="345" y="68" className="f-s">the answer key: after/</text>

        <rect x="240" y="146" width="210" height="64" rx="10" className="f-box f-new" />
        <text x="345" y="174" className="f-t">New job, PySpark</text>
        <text x="345" y="194" className="f-s">written by the AI: spark/</text>

        <rect x="530" y="80" width="170" height="70" rx="10" className="f-box f-cmp" />
        <text x="615" y="110" className="f-t">Compare</text>
        <text x="615" y="130" className="f-s">row for row</text>

        <rect x="770" y="20" width="100" height="56" rx="10" className="f-box f-ok" />
        <text x="820" y="53" className="f-t">Verified</text>
        <rect x="770" y="154" width="100" height="56" rx="10" className="f-box f-bad" />
        <text x="820" y="187" className="f-t">Differs</text>

        <path d="M160 105 C200 105 205 52 238 52" className="f-line" markerEnd="url(#ah)" />
        <path d="M160 125 C200 125 205 178 238 178" className="f-line" markerEnd="url(#ah)" />
        <path d="M450 52 C490 52 490 105 528 105" className="f-line" markerEnd="url(#ah)" />
        <path d="M450 178 C490 178 490 125 528 125" className="f-line" markerEnd="url(#ah)" />
        <path d="M700 105 C735 105 740 48 768 48" className="f-line" markerEnd="url(#ah)" />
        <path d="M700 125 C735 125 740 182 768 182" className="f-line" markerEnd="url(#ah)" />
        <path d="M820 212 C820 246 360 246 352 214" className="f-line f-dash" markerEnd="url(#ah)" />
        <text x="590" y="264" className="f-s f-loop">dev differences go back to the AI · holdout differences never do</text>
      </svg>
    </figure>
  );
}

function TranspilerPanel({ probe }: { probe: Probe }) {
  const rejected = probe.statements.filter((s) => s.spark_error);
  const [i, setI] = useState(() => Math.max(0, rejected.findIndex((s) => s.kind === 'DELETE')));
  const ex = rejected[i];
  const out = useMemo(() => (ex?.transpiled ? highlightLines(ex.transpiled, 'sql') : []), [ex]);
  const s = probe.summary;
  return (
    <section className="panel transpiler" aria-labelledby="tp-title">
      <h2 id="tp-title">Why not just use a SQL converter?</h2>
      <p>
        Tools like <strong>sqlglot</strong> convert SQL from one dialect to another. We ran it on the legacy jobs with
        strict error checking on. It said every statement converted fine. Then we asked Spark itself.
      </p>
      <div className="tp-stats">
        <div><span className="tp-num ok">{s.sqlglot_succeeded}/{s.statements}</span><span>statements sqlglot says it converted, no errors</span></div>
        <div><span className="tp-num bad">{s.spark_parse_rejected}/{s.statements}</span><span>of those, Spark refuses to even read</span></div>
        <div><span className="tp-num">141/141</span><span>"converted" across all 13 Microsoft procedures in our first probe</span></div>
      </div>
      <p className="muted small">
        A silent failure: the converter keeps T-SQL-only forms like <code>UPDATE … FROM</code> and <code>DELETE s FROM</code>.
        And a statement Spark can read can still give different answers. Only running both and comparing shows that.
      </p>
      {ex && (
        <div className="tp-example">
          <div className="tp-tabs" role="tablist" aria-label="Rejected statements">
            {rejected.map((r, k) => (
              <button key={k} role="tab" aria-selected={k === i} onClick={() => setI(k)}>
                {r.file.split('/').pop()!.replace('MigrateStaged', '').replace('Data.sql', '')} {r.kind}
              </button>
            ))}
          </div>
          <figure className="code-pane">
            <figcaption>
              <strong>sqlglot's "successful" Spark output</strong>
              <span className="muted">{ex.file}</span>
            </figcaption>
            <div className="code-scroll short" tabIndex={0}>
              <pre className="hljs"><code>
                {out.map((h, k) => (
                  <span className="ln" key={k}><span className="ln-no" aria-hidden>{k + 1}</span><span className="ln-code" dangerouslySetInnerHTML={{ __html: h || ' ' }} /></span>
                ))}
              </code></pre>
            </div>
          </figure>
          <p className="spark-says"><Icon name="cross" size={16} /> Spark: <code>{ex.spark_error}</code></p>
        </div>
      )}
      <p className="muted small">
        Real output of <code>scripts/sqlglot_probe.py</code> (sqlglot {s.sqlglot_version}, Spark's own SQL parser) on the 3 jobs in this repo.
        T-SQL variables were filled in first so they aren't what fails.
      </p>
    </section>
  );
}
