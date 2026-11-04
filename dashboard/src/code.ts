// Syntax highlighting (only the two languages we need, so the bundle stays small)
// and a line diff between two attempts' code.
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import sql from 'highlight.js/lib/languages/sql';

hljs.registerLanguage('python', python);
hljs.registerLanguage('sql', sql);

export type Lang = 'python' | 'sql';

/**
 * Highlight the whole file at once (so multi-line strings and comments are coloured right),
 * then split the HTML into lines, closing and reopening any <span> that crosses a line break.
 */
export function highlightLines(code: string, lang: Lang): string[] {
  const html = hljs.highlight(code.replace(/\s+$/, ''), { language: lang, ignoreIllegals: true }).value;
  const lines: string[] = [];
  const open: string[] = [];
  let current = '';
  const tag = /<span[^>]*>|<\/span>|\n/g;
  let last = 0;
  for (let m = tag.exec(html); m; m = tag.exec(html)) {
    current += html.slice(last, m.index);
    last = m.index + m[0].length;
    if (m[0] === '\n') {
      lines.push(current + '</span>'.repeat(open.length));
      current = open.join('');
    } else if (m[0] === '</span>') {
      open.pop();
      current += m[0];
    } else {
      open.push(m[0]);
      current += m[0];
    }
  }
  lines.push(current + html.slice(last));
  return lines;
}

export type DiffOp = { kind: 'same' | 'add' | 'del'; text: string; oldNo: number | null; newNo: number | null };

/** Classic longest-common-subsequence line diff. Files here are a few hundred lines at most. */
export function lineDiff(oldText: string, newText: string): DiffOp[] {
  const a = oldText.replace(/\s+$/, '').split('\n');
  const b = newText.replace(/\s+$/, '').split('\n');
  const n = a.length;
  const m = b.length;
  // lcs[i][j] = length of the LCS of a[i..] and b[j..]
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && a[i] === b[j]) {
      ops.push({ kind: 'same', text: a[i], oldNo: i + 1, newNo: j + 1 });
      i++;
      j++;
    } else if (i < n && (j >= m || lcs[i + 1][j] >= lcs[i][j + 1])) {
      // removed lines first, then added ones, like git diff
      ops.push({ kind: 'del', text: a[i], oldNo: i + 1, newNo: null });
      i++;
    } else {
      ops.push({ kind: 'add', text: b[j], oldNo: null, newNo: j + 1 });
      j++;
    }
  }
  return ops;
}
