import { useCallback, useEffect, useState } from 'react';
import type { Manifest, ResultsFile } from './types';
import { go, href, useRoute } from './router';
import { Icon, StatusIcon } from './ui';
import { jobView } from './model';
import { Overview } from './views/Overview';
import { JobPage } from './views/JobPage';
import { HowItWorks, type Probe } from './views/HowItWorks';
import { CheckerTest } from './views/CheckerTest';

type Theme = 'system' | 'light' | 'dark';

// Browser storage can be missing or blocked (private windows, some kiosks), so never rely on it.
function loadTheme(): Theme {
  try {
    const t = localStorage.getItem('lm-theme');
    if (t === 'light' || t === 'dark') return t;
  } catch {
    /* ignore */
  }
  return 'system';
}

function saveTheme(t: Theme) {
  try {
    localStorage.setItem('lm-theme', t);
  } catch {
    /* ignore */
  }
}

function useTheme() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  useEffect(() => {
    if (theme === 'system') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    saveTheme(theme);
  }, [theme]);
  const cycle = useCallback(() => setTheme((t) => (t === 'system' ? 'dark' : t === 'dark' ? 'light' : 'system')), []);
  return { theme, cycle };
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

type Loaded = { manifest: Manifest; fileId: string; data: ResultsFile; probe: Probe | null };

function useData() {
  const [state, setState] = useState<Loaded | { error: string } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const manifest = await getJson<Manifest>('data/manifest.json');
        const wanted = new URLSearchParams(window.location.search).get('data') ?? manifest.default;
        const entry = manifest.files.find((f) => f.id === wanted) ?? manifest.files[0];
        const [data, probe] = await Promise.all([
          getJson<ResultsFile>(`data/${entry.path}`),
          getJson<Probe>('data/sqlglot_probe.json').catch(() => null),
        ]);
        if (data.contract_version !== 1) throw new Error(`${entry.path}: contract_version ${data.contract_version}, this dashboard reads 1`);
        setState({ manifest, fileId: entry.id, data, probe });
      } catch (e) {
        setState({ error: String(e) });
      }
    })();
  }, []);
  return state;
}

function switchFile(id: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('data', id);
  window.location.href = url.toString();
}

export function App() {
  const route = useRoute();
  const loaded = useData();
  const { theme, cycle } = useTheme();
  const [help, setHelp] = useState(false);

  // Global keys. Job-page keys (arrows, tabs) live in JobPage.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement;
      if (el.closest('input, textarea, select, [contenteditable]')) return;
      if (e.key === '?') setHelp((h) => !h);
      else if (e.key === 'Escape') {
        if (help) setHelp(false);
        else if (route.page !== 'overview') go({ page: 'overview' });
      } else if (e.key === 'o') go({ page: 'overview' });
      else if (e.key === 'h') go({ page: 'how' });
      else if (e.key === 'c') go({ page: 'checks' });
      else if (e.key === 't') cycle();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [route.page, help, cycle]);

  // Each page starts at the top; changing attempt or tab within a job keeps the scroll position.
  const pageKey = route.page === 'job' ? `job:${route.jobId}` : route.page;
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pageKey]);

  const data = loaded && 'data' in loaded ? loaded.data : null;
  useEffect(() => {
    const job = route.page === 'job' && data ? data.jobs.find((j) => j.id === route.jobId) : null;
    const part = route.page === 'how' ? 'How it works' : route.page === 'checks' ? 'Checker test' : job ? job.name : 'Overview';
    document.title = `${part} - LegacyMigrator`;
  }, [route, data]);

  const job = route.page === 'job' && data ? data.jobs.find((j) => j.id === route.jobId) : undefined;
  const files = loaded && 'manifest' in loaded ? loaded.manifest.files : [];
  const fileId = loaded && 'fileId' in loaded ? loaded.fileId : '';

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <aside className="sidebar" aria-label="Navigation">
        <a className="brand" href={href({ page: 'overview' })} aria-label="LegacyMigrator overview">
          <Logo />
          <span className="brand-text">
            <span className="brand-name">LegacyMigrator</span>
            <span className="brand-sub">Migration control room</span>
          </span>
        </a>
        <nav className="side-nav" aria-label="Main">
          <a href={href({ page: 'overview' })} aria-current={route.page === 'overview' ? 'page' : undefined}>
            <Icon name="grid" size={16} /> Overview
          </a>
          {data?.checker_tests && (
            <a href={href({ page: 'checks' })} aria-current={route.page === 'checks' ? 'page' : undefined}>
              <Icon name="bug" size={16} /> Checker test
            </a>
          )}
          <a href={href({ page: 'how' })} aria-current={route.page === 'how' ? 'page' : undefined}>
            <Icon name="book" size={16} /> How it works
          </a>
        </nav>
        {data && (
          <div className="side-section">
            <p className="side-label">Jobs <span>{data.jobs.length}</span></p>
            <ul className="side-jobs">
              {data.jobs.map((j) => {
                const v = jobView(j);
                return (
                  <li key={j.id}>
                    <a
                      href={href({ page: 'job', jobId: j.id, attempt: null, tab: 'results' })}
                      aria-current={route.page === 'job' && route.jobId === j.id ? 'page' : undefined}
                    >
                      <StatusIcon status={v.shown} />
                      <span className="sj-name">{j.name}</span>
                      <span className="sj-meta">{j.attempts.length ? `${j.attempts.length} att.` : '-'}</span>
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        <div className="side-foot">
          {files.length > 1 && (
            <label className="field">
              <span className="side-label">Results file</span>
              <select id="results-file" value={fileId} onChange={(e) => switchFile(e.target.value)}>
                {files.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
              </select>
            </label>
          )}
          <div className="side-tools">
            <button className="icon-btn" onClick={cycle} title={`Theme: ${theme} (t)`} aria-label={`Theme: ${theme}. Change theme`}>
              <Icon name={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'auto'} size={16} />
            </button>
            <button className="icon-btn" onClick={() => setHelp(true)} title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts">
              <Icon name="keyboard" size={16} />
            </button>
          </div>
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <nav className="crumbs" aria-label="Breadcrumb">
            <a href={href({ page: 'overview' })}>Jobs</a>
            {route.page === 'how' && <><span className="sep">/</span><span>How it works</span></>}
            {route.page === 'checks' && <><span className="sep">/</span><span>Checker test</span></>}
            {job && <><span className="sep">/</span><span>{job.name}</span></>}
            {job && route.page === 'job' && route.attempt && <><span className="sep">/</span><span>Attempt {route.attempt}</span></>}
          </nav>
          <div className="topbar-meta">
            {data && <span className="muted run-time">Run {new Date(data.generated_at).toISOString().slice(0, 16).replace('T', ' ')} UTC</span>}
          </div>
        </header>

        {data?.sample && <SampleBanner notes={data.notes ?? []} />}

        <main id="main" className="main">
          {!loaded && <p className="loading">Loading results…</p>}
          {loaded && 'error' in loaded && <LoadError error={loaded.error} />}
          {data && route.page === 'overview' && <Overview data={data} />}
          {data && route.page === 'checks' && <CheckerTest data={data} />}
          {data && route.page === 'how' && <HowItWorks data={data} probe={loaded && 'probe' in loaded ? loaded.probe : null} />}
          {data && route.page === 'job' && <JobPage data={data} route={route} />}
        </main>

        <footer className="footer">
          {data && <span>{data.title ?? 'Results'} · contract v{data.contract_version}</span>}
          <span>The AI translates. The old system's real output decides.</span>
        </footer>
      </div>

      {help && <Shortcuts onClose={() => setHelp(false)} />}
    </div>
  );
}

function Logo() {
  // Two lanes, old and new, meeting in a check: the translation is only accepted when they agree.
  return (
    <svg className="logo" width="28" height="28" viewBox="0 0 28 28" aria-hidden>
      <rect x="1" y="1" width="26" height="26" rx="6" className="logo-bg" />
      <path d="M7 9h8M7 14h5" className="logo-old" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M12 19.5l3 3 6.5-8" className="logo-new" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

function SampleBanner({ notes }: { notes: string[] }) {
  return (
    <div className="sample-banner" role="note">
      <div className="sample-inner">
        <strong><Icon name="warn" size={14} /> Sample data</strong>
        <span>{notes[0] ?? 'Invented numbers for the demo. Not real results.'}</span>
        {notes.length > 1 && (
          <details>
            <summary>What's real?</summary>
            <ul>{notes.slice(1).map((n) => <li key={n}>{n}</li>)}</ul>
          </details>
        )}
      </div>
    </div>
  );
}

function LoadError({ error }: { error: string }) {
  return (
    <div className="panel load-error">
      <h1>Couldn't load the results</h1>
      <p><code>{error}</code></p>
      <p>
        The dashboard reads <code>data/manifest.json</code> and the file it points to. If you opened
        <code> index.html</code> straight from disk, browsers block that: run <code>npm run preview</code> or
        <code> python3 -m http.server</code> in <code>dashboard/dist</code> instead.
      </p>
    </div>
  );
}

const KEYS: [string, string][] = [
  ['o', 'Overview: all jobs'],
  ['h', 'How it works'],
  ['c', 'Checker test (planted bugs)'],
  ['↑ ↓  or  j k', 'Move between jobs (overview)'],
  ['Enter', 'Open the selected job'],
  ['← →', 'Previous / next attempt (job page)'],
  ['[  ]', 'Previous / next job'],
  ['1 2 3 4', 'Results, Code, Evidence, Lineage tabs'],
  ['t', 'Theme: system, dark, light'],
  ['Esc', 'Back to overview'],
  ['?', 'Show or hide this list'],
];

function Shortcuts({ onClose }: { onClose: () => void }) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="keys-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="keys-title">Keyboard shortcuts</h2>
        <dl className="keys">
          {KEYS.map(([k, v]) => (
            <div key={k}><dt><kbd>{k}</kbd></dt><dd>{v}</dd></div>
          ))}
        </dl>
        <button className="btn" onClick={onClose} autoFocus>Close</button>
      </div>
    </div>
  );
}
