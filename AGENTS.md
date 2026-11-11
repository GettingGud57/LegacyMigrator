# AGENTS.md

Instructions for any agent working in this repo.

## Project

LegacyMigrator is an entry for EXL hackathon Challenge 03.
It migrates legacy T-SQL/SAS jobs to PySpark and proves record-for-record reconciliation against the real legacy output.
The pitch is "the AI never grades its own work", so the rules below are what make the result credible.

The project brief and the hackathon PDF are not in this repo.
The PDF is the source of truth over the brief.

## Project rules

- Never write `migrator/diff.py`.
  It is the judge and is written by hand.
  Reviewing it and answering questions about it is fine.
  If asked for reconciliation code, stop and offer a review instead.
- `migrator/loop.py` (the retry loop) may be AI-assisted, but it never decides PASS or FAIL itself.
  Every verdict comes from `diff.reconcile`.
- The key and ignored columns per table live in `jobs/<job>.json` and are chosen by a human.
  The translator and the loop must never change them.
- The translator must never see holdout data or holdout diffs.
- Translations reproduce legacy behaviour, quirks included.
  Do not "improve" the logic.
- Never commit `.env` or `snapshots/`.
  Never put credentials in commands or code.
- Helpers go in `scripts/`, never in `legacy_jobs/`, because the tool translates everything in `legacy_jobs/`.
- If the brief conflicts with the hackathon PDF, or you need either one and cannot read it, flag it and ask.
  Do not guess.

## General guidelines

- Never use the em dash. Use a plain dash "-" instead.
- When writing commit messages, never add your agent name as co-author.
- Never manually modify CHANGELOG.md files or any files that are marked as auto-generated.
- When writing or substantially editing long Markdown files, put each full sentence on its own line.
  Preserve normal Markdown structure, but avoid wrapping multiple sentences onto one physical line.
- When making technical decisions, do not give much weight to development cost.
  Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
- When doing bug fixes, always start by reproducing the bug in an end to end setting, as closely aligned as possible with how an end user operates.
  This makes sure you find the real problem, so your fix will actually solve it.
- When end to end testing a product, be picky about the UI you see and be obsessed with pixel perfection.
  If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along the way.
- Apply that same high standard to engineering excellence: lint, test failures, and test flakiness.
  If you see one, even if it is not caused by what you are working on right now, still get it fixed.
