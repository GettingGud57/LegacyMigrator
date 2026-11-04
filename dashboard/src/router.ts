// Hash-based routes, so deep links work on any static host (and from python -m http.server).
//   #/                          overview
//   #/how                       how it works
//   #/job/sale                  a job (its latest attempt)
//   #/job/sale/attempt/2        one attempt
//   #/job/sale/attempt/2/code   one attempt, on a given tab
import { useEffect, useState } from 'react';

export type Tab = 'results' | 'code' | 'evidence' | 'lineage';
export const TABS: Tab[] = ['results', 'code', 'evidence', 'lineage'];

export type Route =
  | { page: 'overview' }
  | { page: 'how' }
  | { page: 'job'; jobId: string; attempt: number | null; tab: Tab };

export function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'how') return { page: 'how' };
  if (parts[0] === 'job' && parts[1]) {
    const attempt = parts[2] === 'attempt' && /^\d+$/.test(parts[3] ?? '') ? Number(parts[3]) : null;
    const tabPart = attempt === null ? parts[2] : parts[4];
    const tab = TABS.includes(tabPart as Tab) ? (tabPart as Tab) : 'results';
    return { page: 'job', jobId: parts[1], attempt, tab };
  }
  return { page: 'overview' };
}

export function href(route: Route): string {
  if (route.page === 'overview') return '#/';
  if (route.page === 'how') return '#/how';
  let h = `#/job/${encodeURIComponent(route.jobId)}`;
  if (route.attempt !== null) h += `/attempt/${route.attempt}`;
  if (route.tab !== 'results') h += `/${route.tab}`;
  return h;
}

export function go(route: Route) {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
