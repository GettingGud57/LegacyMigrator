// Small shared pieces: icons, status pills, badges.
import type { ReactNode } from 'react';
import type { Outcome, ShownStatus } from './model';
import { OUTCOME_LABEL, STATUS_LABEL } from './model';

type IconName =
  | 'check' | 'cross' | 'retry' | 'dot' | 'circle' | 'warn' | 'lock' | 'eye' | 'crash'
  | 'sun' | 'moon' | 'auto' | 'arrow' | 'back' | 'keyboard' | 'half';

const PATHS: Record<IconName, ReactNode> = {
  check: <path d="M5 12.5l4.2 4.2L19 7" />,
  cross: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
  retry: <><path d="M19 8.5A7.5 7.5 0 1 0 19.5 14" /><path d="M19.5 4v4.5H15" /></>,
  dot: <circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none" />,
  circle: <circle cx="12" cy="12" r="7" />,
  half: <><circle cx="12" cy="12" r="7" /><path d="M12 5a7 7 0 0 1 0 14z" fill="currentColor" stroke="none" /></>,
  warn: <><path d="M12 4l9 16H3z" /><path d="M12 10v4.5M12 17.2v.3" /></>,
  lock: <><rect x="5" y="10.5" width="14" height="9.5" rx="1.5" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></>,
  eye: <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.8" /></>,
  crash: <><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></>,
  moon: <path d="M19.5 14.5A8 8 0 0 1 9.5 4.5a8 8 0 1 0 10 10z" />,
  auto: <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none" /></>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  back: <path d="M19 12H5M11 6l-6 6 6 6" />,
  keyboard: <><rect x="2.5" y="6" width="19" height="12" rx="2" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" /></>,
};

export function Icon({ name, size = 18, title }: { name: IconName; size?: number; title?: string }) {
  return (
    <svg
      className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
    >
      {title && <title>{title}</title>}
      {PATHS[name]}
    </svg>
  );
}

const STATUS_ICON: Record<ShownStatus, IconName> = {
  verified: 'check', failed: 'cross', retrying: 'retry', in_progress: 'half', not_started: 'circle', unconfirmed: 'warn',
};

/** Status always carries an icon and a word, never colour alone. */
export function StatusPill({ status, big = false }: { status: ShownStatus; big?: boolean }) {
  return (
    <span className={`pill tone-${status} ${big ? 'pill-big' : ''}`}>
      <Icon name={STATUS_ICON[status]} size={big ? 20 : 15} />
      {STATUS_LABEL[status]}
    </span>
  );
}

const OUTCOME_ICON: Record<Outcome, IconName> = {
  crashed: 'crash', mismatch: 'cross', incomplete: 'half', passed_dev: 'check', failed_holdout: 'cross', verified: 'check',
};

export const OUTCOME_TONE: Record<Outcome, ShownStatus> = {
  crashed: 'failed', mismatch: 'failed', incomplete: 'in_progress', passed_dev: 'in_progress',
  failed_holdout: 'failed', verified: 'verified',
};

export function OutcomeMark({ outcome, size = 16 }: { outcome: Outcome; size?: number }) {
  return (
    <span className={`mark tone-${OUTCOME_TONE[outcome]}`} title={OUTCOME_LABEL[outcome]}>
      <Icon name={OUTCOME_ICON[outcome]} size={size} />
    </span>
  );
}

export function HoldoutBadge({ state, compact = false }: { state: 'passed' | 'failed' | 'not_run'; compact?: boolean }) {
  const text = {
    passed: compact ? 'Passed' : 'Passed on holdout data the AI never saw',
    failed: compact ? 'Failed' : 'Failed on holdout data the AI never saw',
    not_run: compact ? 'Not run' : 'Holdout not run yet',
  }[state];
  const tone = { passed: 'verified', failed: 'failed', not_run: 'not_started' }[state];
  return (
    <span className={`holdout tone-${tone}`}>
      <Icon name="lock" size={compact ? 14 : 16} />
      {text}
    </span>
  );
}

export function TableVerdictTag({ verdict }: { verdict: 'pass' | 'fail' | 'not_compared' }) {
  const map = {
    pass: { icon: 'check' as IconName, text: 'Match', tone: 'verified' },
    fail: { icon: 'cross' as IconName, text: 'Differs', tone: 'failed' },
    not_compared: { icon: 'circle' as IconName, text: 'Not compared', tone: 'not_started' },
  }[verdict];
  return (
    <span className={`tag tone-${map.tone}`}>
      <Icon name={map.icon} size={14} />
      {map.text}
    </span>
  );
}
