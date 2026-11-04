# Dashboard: the migration control room

A read-only website that shows what the pipeline proved.
It never runs the pipeline.
It reads JSON files from `public/data/` and draws them.

## Run it

You need Node.js 20 or newer (`brew install node` on a Mac).

```
cd dashboard
npm ci            # once: installs the exact versions in package-lock.json
npm run dev       # http://localhost:5173, reloads when you edit
```

## Build it (for the demo, or to host anywhere)

```
npm run build     # type-checks, then writes dist/
npm run preview   # serves dist/ at http://localhost:4173
```

`dist/` is plain files with relative paths and no internet needed: fonts and code are bundled.
Copy it anywhere (a USB stick, GitHub Pages, Netlify) and serve it with any web server, e.g. `python3 -m http.server -d dist 8000`.
Opening `dist/index.html` by double-clicking won't work: browsers block reading the JSON files from disk.

## Which data it shows

`public/data/manifest.json` lists the result files and which one opens first.
The header has a dropdown to switch, and `?data=<id>` in the address picks one (e.g. `http://localhost:5173/?data=real`).

| File | What it is |
|---|---|
| `sample.json` | The demo story. Invented numbers, so the UI shows a "Sample data" banner. Built by `scripts/build_dashboard_data.py`. |
| `real.json` | Only what has really happened so far. Built by the same script. |
| `sqlglot_probe.json` | Real output of `scripts/sqlglot_probe.py`, shown on "How it works". |
| `results.json` | Not there yet: what `loop.py` (or `scripts/check_to_results.py`) will write. |

The format is in `docs/results-contract.md`.
Check a file with `python scripts/check_results.py dashboard/public/data/results.json`.

To show real check.py results today (from branch `claude/test-bench`):

```
python migrator/check.py sale
python scripts/check_to_results.py sale
```

then add `{"id": "results", "label": "Latest run", "path": "results.json"}` to `manifest.json` and set `"default": "results"`.
JSON changes show up on a browser refresh; no rebuild needed with `npm run dev`. For `dist/`, copy the JSON into `dist/data/` or rebuild.

## Links and keys

Every view has its own address, so you can paste a link to one attempt:
`#/job/sale/attempt/2` or `#/job/sale/attempt/3/code`.

Press `?` in the app for the keyboard shortcuts: `←` `→` step through attempts, `1`-`4` switch tabs, `[` `]` previous/next job, `t` theme, `Esc` back.

## How the code is laid out

| File | What it does |
|---|---|
| `src/types.ts` | The results file as TypeScript types. Mirrors the contract doc. |
| `src/model.ts` | Every conclusion the UI draws, worked out from the evidence: attempt outcomes, the job status shown, the plain-language sentences. If you change what "verified" means, it's here. |
| `src/router.ts` | The `#/...` addresses. |
| `src/code.ts` | Syntax highlighting and the line diff between attempts. |
| `src/ui.tsx` | Icons, status pills, badges. |
| `src/views/` | One file per screen or big piece of a screen. |
| `src/styles.css` | All styling. Colours are variables at the top, with a dark-mode copy. |

The one rule: the dashboard never trusts a job's `status` field on its own.
`model.ts` recomputes it from the per-table results, and a "verified" without the evidence shows as "Unconfirmed" with a warning.
