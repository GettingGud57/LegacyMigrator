import { useMemo, useState } from 'react';
import type { Attempt, Job } from '../types';
import { highlightLines, lineDiff, type Lang } from '../code';

/** Old T-SQL and new PySpark side by side; optionally, what changed since the previous attempt. */
export function CodeView({ job, attempt }: { job: Job; attempt: Attempt }) {
  const prev = job.attempts[attempt.number - 2];
  const [showDiff, setShowDiff] = useState(false);
  const [phonePane, setPhonePane] = useState<'sql' | 'py'>('py');
  const diffOn = showDiff && !!prev;

  return (
    <div className="code-view">
      <div className="code-toolbar">
        <div className="seg phone-only" role="tablist" aria-label="Which code">
          <button role="tab" aria-selected={phonePane === 'sql'} onClick={() => setPhonePane('sql')}>Old T-SQL</button>
          <button role="tab" aria-selected={phonePane === 'py'} onClick={() => setPhonePane('py')}>New PySpark</button>
        </div>
        {prev && (
          <label className="toggle">
            <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
            <span>Show what changed since attempt {prev.number}</span>
          </label>
        )}
      </div>
      <div className={`code-grid show-${phonePane}`}>
        <CodePane
          className="pane-sql"
          title="Old: T-SQL stored procedure"
          sub={job.source_file ?? job.proc}
          code={job.legacy_sql}
          lang="sql"
        />
        {diffOn ? (
          <DiffPane
            className="pane-py"
            title={`New: PySpark, attempt ${attempt.number} vs ${prev.number}`}
            oldCode={prev.code}
            newCode={attempt.code}
          />
        ) : (
          <CodePane
            className="pane-py"
            title={`New: PySpark, attempt ${attempt.number}`}
            sub="written by the AI, never edited by hand"
            code={attempt.code}
            lang="python"
          />
        )}
      </div>
    </div>
  );
}

function CodePane({ title, sub, code, lang, className }: { title: string; sub: string; code: string; lang: Lang; className: string }) {
  const lines = useMemo(() => highlightLines(code, lang), [code, lang]);
  return (
    <figure className={`code-pane ${className}`}>
      <figcaption>
        <strong>{title}</strong>
        <span className="muted">{sub} · {lines.length} lines</span>
      </figcaption>
      <div className="code-scroll" tabIndex={0} aria-label={title}>
        <pre className="hljs">
          <code>
            {lines.map((html, i) => (
              <span className="ln" key={i}>
                <span className="ln-no" aria-hidden>{i + 1}</span>
                <span className="ln-code" dangerouslySetInnerHTML={{ __html: html || ' ' }} />
              </span>
            ))}
          </code>
        </pre>
      </div>
    </figure>
  );
}

function DiffPane({ title, oldCode, newCode, className }: { title: string; oldCode: string; newCode: string; className: string }) {
  const ops = useMemo(() => lineDiff(oldCode, newCode), [oldCode, newCode]);
  // Highlight each side whole, then pick lines out by number, so colours stay right.
  const oldHl = useMemo(() => highlightLines(oldCode, 'python'), [oldCode]);
  const newHl = useMemo(() => highlightLines(newCode, 'python'), [newCode]);
  const added = ops.filter((o) => o.kind === 'add').length;
  const removed = ops.filter((o) => o.kind === 'del').length;
  return (
    <figure className={`code-pane ${className}`}>
      <figcaption>
        <strong>{title}</strong>
        <span className="muted">
          <span className="diff-add-t">+{added}</span> <span className="diff-del-t">−{removed}</span> lines
        </span>
      </figcaption>
      <div className="code-scroll" tabIndex={0} aria-label={title}>
        <pre className="hljs">
          <code>
            {ops.map((o, i) => {
              const html = o.kind === 'del' ? oldHl[o.oldNo! - 1] : newHl[o.newNo! - 1];
              return (
                <span className={`ln diff-${o.kind}`} key={i}>
                  <span className="ln-no" aria-hidden>{o.kind === 'del' ? '−' : o.kind === 'add' ? '+' : o.newNo}</span>
                  <span className="ln-code" dangerouslySetInnerHTML={{ __html: html || ' ' }} />
                </span>
              );
            })}
          </code>
        </pre>
      </div>
    </figure>
  );
}
