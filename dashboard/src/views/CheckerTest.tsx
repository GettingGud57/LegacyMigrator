import type { BugRun, PlantedBug, ResultsFile } from '../types';
import { Icon } from '../ui';

type Bucket = 'control' | 'dev' | 'holdout' | 'missed';

/** Which group a planted bug falls in, worked out from its two runs (not from the outcome text). */
function bucket(b: PlantedBug): Bucket {
  if (b.control) return 'control';
  if (b.dev.status === 'fail') return 'dev';
  if (b.holdout.status === 'fail') return 'holdout';
  return 'missed';
}

const BUCKET: Record<Bucket, { label: string; tone: string }> = {
  control: { label: 'Control', tone: 'in_progress' },
  dev: { label: 'Caught on dev data', tone: 'verified' },
  holdout: { label: 'Caught only by holdout', tone: 'retrying' },
  missed: { label: 'Missed', tone: 'failed' },
};

/**
 * The checker's own test: bugs planted on purpose in a translation that passes.
 * A checker that never fails proves nothing, so this is the evidence the green ticks mean something.
 */
export function CheckerTest({ data }: { data: ResultsFile }) {
  const t = data.checker_tests;
  if (!t) return <p className="muted">This results file has no checker test.</p>;
  const bugs = t.bugs.filter((b) => !b.control);
  const control = t.bugs.find((b) => b.control);
  const by = (k: Bucket) => bugs.filter((b) => bucket(b) === k).length;
  const caught = by('dev') + by('holdout');
  const controlOk = control && control.dev.status === 'pass' && control.holdout.status === 'pass';

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Checker test</h1>
          <p className="muted">
            A checker that never says FAIL proves nothing. So we took the {t.job} translation that passes, planted
            one realistic bug at a time, and ran each through the same check on dev and holdout data.
          </p>
        </div>
      </header>

      <section className="stats stats-4" aria-label="Planted bug results">
        <div className="stat stat-main">
          <span className="stat-label">Planted bugs caught</span>
          <span className="stat-value"><span className="headline-num">{caught}</span><span className="stat-of"> / {bugs.length}</span></span>
          <div className="hbar" aria-hidden>
            {bugs.map((b) => <span key={b.name} className={`hbar-seg tone-${BUCKET[bucket(b)].tone}`} />)}
          </div>
          <span className="stat-note">Each planted into a copy of the real translation, run on both datasets</span>
        </div>
        <div className="stat"><span className="stat-label">Caught on dev data</span><span className="stat-value">{by('dev')}</span></div>
        <div className="stat"><span className="stat-label">Caught only by holdout</span><span className="stat-value">{by('holdout')}</span></div>
        <div className="stat"><span className="stat-label">Missed</span><span className="stat-value">{by('missed')}</span></div>
        <div className="stat">
          <span className="stat-label">Control (no bug)</span>
          <span className={`stat-value ${controlOk ? 'ok' : 'bad'}`}>{controlOk ? 'Passes' : 'Fails'}</span>
        </div>
      </section>

      <section aria-labelledby="bugs-title">
        <div className="section-head">
          <h2 id="bugs-title">Every planted bug <span className="count">{t.bugs.length}</span></h2>
          <p className="muted small">Reasons come from the test bench report. Missed bugs say what data would catch them.</p>
        </div>
        <div className="grid-scroll bug-scroll" tabIndex={0}>
          <table className="bugs">
            <thead>
              <tr>
                <th scope="col">Planted bug</th>
                <th scope="col">Dev data</th>
                <th scope="col"><Icon name="lock" size={12} /> Holdout data</th>
                <th scope="col">Result</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {t.bugs.map((b) => {
                const k = bucket(b);
                return (
                  <tr key={b.name} className={`bug-${k}`}>
                    <td className="bug-name"><code>{b.name}</code><span>{b.description}</span></td>
                    <td><RunCell run={b.dev} /></td>
                    <td><RunCell run={b.holdout} /></td>
                    <td><span className={`tag tone-${BUCKET[k].tone}`}>{BUCKET[k].label}</span></td>
                    <td className="bug-why">{b.why}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <h2>What this shows</h2>
        <ul className="plain-list">
          <li>The control (the real translation, unchanged) passes both datasets, so the checker doesn't cry wolf.</li>
          <li>
            {by('holdout') === 1 ? 'One bug was' : `${by('holdout')} bugs were`} invisible on dev data and only caught on holdout
            data. That's why a holdout set exists: passing the data you were corrected on proves less.
          </li>
          <li>
            The {by('missed')} missed bugs change nothing on this data, so no row comparison can see them. Each row says
            what extra test would. Passing means "matched on every dataset we tried", not a proof.
          </li>
        </ul>
      </section>
    </div>
  );
}

function RunCell({ run }: { run: BugRun }) {
  if (run.crashed) return <span className="bad">Crashed</span>;
  if (run.status === 'pass') return <span className="run-chip rc-pass">PASS</span>;
  return (
    <span className="bug-fail">
      <span className="run-chip rc-fail">FAIL</span>
      {run.failed_tables.map((f) => (
        <span key={f.table} className="small">
          {f.table} <span className="muted">({f.failed_checks.map((c) => c.replace(/_/g, ' ')).join(', ')})</span>
        </span>
      ))}
    </span>
  );
}
