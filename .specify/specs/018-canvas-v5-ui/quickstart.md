# Quickstart: validating round 018

## Prerequisites

- Branch `018-canvas-v5-ui`, cut from main `07232332` or newer (T001).
- The dev venv (`uv sync --frozen --extra dev`), plus Node for `check_ui.py`. If Node is missing, `check_ui.py` skips with exit 0. A skip is not a pass: report it and stop.
- No compose service is built, restarted or recreated by this round (L8). A parallel benchmark round may be running.

## 1. Gates (every slice, in this order, one command per shell call)

1. `python scripts/check_ui.py`. This runs install, typecheck, builds, vitest (dashboard and ui), ds-bundle, Playwright (showcase plus `app.*.pw.ts` on `VITE_API=mock`) and, from slice 1, the raw-colour check.
2. `pytest`, the fast tier. `addopts` already carries `-q`; do not add another.
3. `pytest tests/test_read_fixtures_fresh.py tests/test_graph_fixtures_fresh.py tests/test_fleet_fixture_fresh.py`.
4. `KROKER_DIFF_GUARD=1 pytest tests/test_018_diff_guard.py`.
5. `python scripts/check_clauses.py`. It always exits 0; read the output. The bar is 0 dangling, and untested only for clauses already untested in baseline.md.
6. `python scripts/check_file_size.py`.
7. `ruff check .`, `ruff format --check .` and `mypy` on touched Python files.

Compare against `baseline.md` (slice 0 counts). The number of passing tests may only drop where contracts/clauses.md retires or rewrites the clause the test covered.

## 2. Walk-through on the mock (after slice 9)

Serve the dashboard built with `VITE_API=mock`, as the app Playwright tier does, then:

1. **Header.** Check Fleet · Inbox · run-in-context and Graphs · Compare · Interfaces. Then ⌘K → "Open Inbox"; ⋯ → Light theme switches every surface.
2. **Fleet.** The halted fixture reads `failed` with its result string. The budget fixture reads `rejected:budget`. Arms read verbatim, and an unpriced run reads "unpriced" or "not priced", never `$0.00`.
3. **Run (escalated fixture).** The escalated sink is lit. The revise edge at its limit carries the escalation note.
4. **Run (live fixture with a tool escalation).** The rail shows the call to action, and the card offers Approve and Deny only. Approve: the call to action goes, and Events shows the decision.
5. **Rail → Cost.** Role rows with calls, tokens and dollars, a "not priced" role, a partial total, and the budget block. `?tab=cost` lands here.
6. **Board.** Kanban columns by wire status, then "Open full Agent Board →" for the list, detail, timeline, versions and counters.
7. **Inbox.** The task card offers approve, revise (thaw tests) and reject, with the reject consequence shown. The budget card and the merge override card are present. Resolve everything, then check the empty state and that the badge is gone.
8. **Graphs.** Three cards and the PipelineConfig panel, with the ADR-6 check and its same-weights note. "Open in Design" on `default`: a mismatched drop is refused; placing a planned type is refused; a layout-only save keeps the sha. "Run this version" opens the start form; on a changed graph it is disabled, with its reason.
9. **Compare.** Arms × graphs, a `not measured` cell, and heatmap columns in record order. An empty-store fixture shows the root path.
10. **Interfaces.** Five rows. Three columns are `not measured`, and family is filled on the dev harness row only.

## 3. Live smoke (optional, read-only)

Run `uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500` from the repo root against the live Temporal. Open each screen. Expected:
- no 500 in the server log;
- Compare either shows records or names its root (set `SDLC_RUNS_ROOT` to the `KROKER_RUNS_BIND` host path to see them).

Do not start a run against live infrastructure during the parallel benchmark round without the orchestrator's go.
