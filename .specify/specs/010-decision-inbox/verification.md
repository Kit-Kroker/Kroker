# Verification: Decision Inbox (010)

Recorded by T024 on branch `010-decision-inbox`. Base sha: `18de7f1`
(baseline.md). The quickstart §2 manual walk was **waived by the
orchestrator**; the evidence below stands in for it.

## Automated gates (all green, run 2026-10-06 pre-interrupt)

| Command | Result |
|---|---|
| `python scripts/check_ui.py` | every step green: install, both typechecks (vue-tsc), both builds, vitest-dashboard **36 files / 446 tests**, ds-bundle, vitest-ui **32 files / 147 tests**, playwright **94 passed** (86 at baseline + 8 inbox tests: CONSOLE-17..22, two for CONSOLE-21) |
| `python scripts/check_clauses.py` | `195 clauses declared, 10 untested, 0 dangling` — every untested clause is pre-existing stage-tier (unchanged from baseline); no `CONSOLE-17`…`CONSOLE-23` gap; no dangling citation |
| `python scripts/check_file_size.py` | clean — no file over the 1000-line ceiling (largest new file: `entries.test.ts` 425 lines; `InboxView.test.ts` 418) |

## Final counts against baseline.md

| Suite | Baseline | Final |
|---|---|---|
| vitest-dashboard | 35 files / 374 tests | 36 files / 446 tests |
| vitest-ui | 32 files / 147 tests | 32 files / 147 tests |
| playwright | 86 | 94 |

## Scope diff (`git diff 18de7f1 HEAD --stat`)

33 files, all inside `.specify/specs/010-decision-inbox/`,
`interfaces/dashboard/frontend/`, `interfaces/ui/app.md`,
`interfaces/ui/app.pw.ts`, `README.md`, `ROADMAP.md`,
`interfaces/dashboard/frontend/README.md`. **No forbidden path
changed.** `F/api/types.ts` shows **additions only** (+14 lines: the
`UnreadableRun` and `InboxState` interfaces and the `getInboxState`
member after `listInbox`; no existing name or signature touched —
FR-014). The working tree's other modified files are the user's
pre-existing uncommitted edits, never staged by this branch.

## The quickstart §2 walk

The walk was attempted on `VITE_API=mock npm run dev`: the dashboard
vite dev server on `127.0.0.1:5199` was started and **answered HTTP
200** during the attempt (the first attempt failed on a shell-attached
server plus a localhost→::1 resolution quirk; the restarted detached
server answered). The scripted walk itself did not complete: the run
was **interrupted twice by the orchestrator** (session ran long; the
machine was under **memory pressure**), and the walk is now **waived
by the orchestrator**, on the rationale recorded here:

- The app-tier Playwright suite runs the **same mock-provider build**
  (`VITE_API=mock`, port 4174) through every screen the walk
  describes: six entries + badge (`CONSOLE-17`), accept and typed
  answer with blank-send blocked (`CONSOLE-18`), revise gating and
  reject (`CONSOLE-19`), override with mandatory justification
  (`CONSOLE-20`), retry with guidance and quarantine without
  (`CONSOLE-21`), the full six-resolution sequence ending in the
  empty state with no badge (`CONSOLE-22`), and the run page offering
  no decided gate (`CONSOLE-23`).
- The walk's one by-eye-only step (EC8, narrow window) is covered at
  the unit tier by the `inbox-longtext` class assertions on the four
  free-text blocks (`entries.test.ts`), per contract §3.2.

What the mock cannot show (load failure, unreadable runs, the 404
race, two runs on one key) is pinned at the unit tier, as the Failure
modes paragraph of `app.md` now states.

## Reviewer gate

Every task T001–T023 passed the blocking per-task reviewer gate
(approve, zero fixes-needed outstanding). This file and the tasks.md
checkbox flip ride the final T024 commit under the same gate.
