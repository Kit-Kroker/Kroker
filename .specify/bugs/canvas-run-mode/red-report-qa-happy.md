# RED-set report — qa-happy seat (bug canvas-run-mode, E75-OQ-1 option (a))

- **Seat**: qa-happy (happy path). Worktree `D:\own\Kroker-bug`, branch
  `fix/canvas-run-mode`, base main `36baf5b`.
- **Date**: 2026-09-20. All RED observations below are from the pre-fix tree
  (the wiring has not landed).
- **Scope kept**: test files only; no production code; existing tests neither
  deleted nor weakened; recorded fixtures (`run_state/*.recorded.json`) only
  ever read, never edited; `fleet-snapshot.json` gained rows only (permitted).

Two deliverables: (1) the Python-side RED contracts — **committed** as
`282831b` ("test(dashboard): RED contracts for the canvas run-mode wiring
(E75-OQ-1)", 3 files, 58 insertions, 0 deletions; pre-commit hooks passed);
(2) the TS-side RED contracts — **left uncommitted** in the working tree for
the bug-lead to verify and commit.

## 1. Python-side contracts (tests/, commit 282831b)

### Files touched

- `tests/test_dashboard_graph_wire.py` (+ canvas run-mode section, 2 tests)
- `tests/test_dashboard_run_graph_routes.py` (+1 test)
- `tests/test_graph_fixtures_fresh.py` (+ section, 2 tests)

### Tests and exact failing assertions (observed via
`.venv/Scripts/python.exe -m pytest --tb=line -p no:warnings`)

| Test | Exact failing assertion line |
|---|---|
| `test_dashboard_graph_wire.py::test_catalog_capabilities_declare_canvas_run_mode_live` | `AssertionError: assert {'validate': ...graph': False} == {'validate': ..._graph': True}` |
| `test_dashboard_graph_wire.py::test_capability_defaults_flip_exactly_validate_and_run_graph` | `assert (False, False) == (True, True)` |
| `test_dashboard_run_graph_routes.py::test_served_catalog_opens_the_run_graph_routes_to_the_http_provider` | `AssertionError: assert {'validate': ...graph': False} == {'validate': ..._graph': True}` |
| `test_graph_fixtures_fresh.py::test_committed_catalog_fixture_declares_run_mode_capabilities` | `AssertionError: assert {'validate': ...graph': False} == {'validate': ..._graph': True}` |
| `test_graph_fixtures_fresh.py::test_the_provisional_run_fixtures_are_swapped_for_the_recorded_contract` | `AssertionError: canvas run-mode swap incomplete: ['run_graphs.provisional.json', 'validation.provisional.json'] must go -- the recorded fixtures replace the provisional mock data (E-75 design 7.4, E75-OQ-1 (a))` |

(One cosmetic amendment after the first RED run: "§7.4" → "design 7.4" in that
assertion message, so it survives cp1252 consoles. Failure mode unchanged.)

### Command evidence

- Five node ids via `.venv\Scripts\python.exe -m pytest`: **5 FAILED**, each an
  assertion value mismatch (dict/tuple inequality, stray-set naming) — no
  errors, no collection failures.
- Full three files: **`5 failed, 51 passed in 12.82s`** — every pre-existing
  test in the touched files green; the old caps pins
  (`test_catalog_capabilities_are_all_false_until_later_epics`,
  `test_capabilities_stay_false`, `PROVISIONAL` set, and the flip-neutral
  `test_catalog_reports_save_and_load_true_with_the_rest_as_today`) are
  deliberately untouched so the atomic fix commit moves them with rationale.
- `uv run --frozen ruff check` + `ruff format --check` on the three files:
  clean.

## 2. TS-side contracts (interfaces/dashboard/frontend/src, uncommitted)

### Files touched

- `api/http-graph.test.ts` (+1 test, +1 fixture import)
- `api/http.test.ts` (+2 tests)
- `api/__fixtures__/fleet-snapshot.json` (gained: open graph run
  `graph-run-live` with full 18-key `stage_marks` + `graph_sha`; closed graph
  run `graph-run-closed`; top-level `closed_marks` for it; `total_open_runs`
  2→3)
- `api/mock/graph.test.ts` (+2 tests, +2 recorded-fixture imports)
- `adapters/graph.test.ts` (+1 describe, 3 tests, +2 recorded-fixture imports)
- `adapters/fleet.test.ts` (+1 test)
- `composables/composables.test.ts` (+2 tests)

### Tests and exact failing assertions (observed via vitest 1.6.0)

| Test | Exact failing assertion line |
|---|---|
| `http-graph` › polls on a running outcome and ends the chain on a completed outcome (recorded FINAL bodies) | `expected 1 to be 2 // Object.is equality` — a running-outcome body ends the chain today (`terminal` undefined reads final) |
| `http` › carries an open graph run stage_marks verbatim as stageMarks | `expected undefined to deeply equal { intake: 'done', …(17) }` |
| `http` › maps a closed graph run from closed_marks and leaves unmarked rows null | `expected undefined to deeply equal { intake: 'done', …(17) }` (closed_marks unread; unmarked rows give `undefined`, not `null`) |
| `fleet` › renders the strip from stageMarks verbatim; canonical stages absent from the marks render skipped | `expected 'done' to be 'skipped' // Object.is equality` (context) and `expected [ 'pending', 'pending', …(3) ] to deeply equal [ 'skipped', 'skipped', …(3) ]` (absent stages) |
| `composables` › renders stageMarks verbatim in canonical order; absent stages render skipped | `expected [ 'done', 'done', 'active', …(2) ] to deeply equal [ 'done', 'skipped', 'active', …(2) ]` |
| `composables` › keeps the linear inference exactly when stageMarks is null | **green today by design** — preservation pin (see analysis) |
| `mock` › serves the recorded graph and the recorded blocked script with its outcome | `expected '9bc61539a897be2744030e2d1147ce5083dcb…' to be 'a021c25b8f7e012faaf9f4de9664d8cc5b11a…'`, then `expected { kind: 'state', …(6) } to deeply equal { kind: 'state', …(6) }` (provisional `architecture#2`/`terminal` vs recorded `architecture#1`/`outcome`) |
| `mock` › reject at the architecture gate advances to the recorded rejected state | `expected { kind: 'state', …(6) } to deeply equal { kind: 'state', …(6) }` (still the provisional blocked script) |
| `graph` › blocked: recorded architect cost and gate pending ref, with the running outcome present | `expected undefined to deeply equal { Object (state, reason, ...) }` |
| `graph` › escalated: the revise loop counter is the recorded traversal count, with the escalated outcome | `expected undefined to deeply equal { state: 'escalated', …(2) }` |
| `graph` › completed: every node decorated terminal, with the completed outcome present | `expected undefined to deeply equal { state: 'completed', …(2) }` |

### Command evidence

- `npm run test --workspace sdlc-dashboard -- src/api/http-graph.test.ts
  src/api/http.test.ts src/api/mock/graph.test.ts src/adapters/fleet.test.ts
  src/adapters/graph.test.ts src/composables/composables.test.ts`
  → **`10 failed | 72 passed (82)`** at a tree containing exactly my 11 new
  tests (10 RED + 1 deliberate-green) plus all pre-existing tests — i.e. every
  pre-existing test still passes and the only green new test is the
  preservation pin. Every failure is an `AssertionError`; none is a
  typecheck-only failure.
- `npm run typecheck --workspace sdlc-dashboard` (`vue-tsc --noEmit`):
  **green** — the wire literals use the suites' cast patterns
  (`as never`, `as unknown as GraphStateResponse`, narrow read-shape casts).
- `client.test.ts` — the only other `fleet-snapshot.json` consumer — rerun
  against the extended fixture: **5 passed**.
- Later reruns show 11+ failures: qa-chaos landed their own RED tests in
  shared files between my runs (`http-graph.chaos.test.ts`, ui specs,
  `RunView.test.ts`, chaos sections inside `graph.test.ts` /
  `composables.test.ts`, `tests/test_dashboard_canvas_run_mode_chaos.py`).
  Those are their pins, not mine; I touched none of them.

## 3. No-production-code confirmation

- Round 1 commit `282831b`: `3 files changed, 58 insertions(+)` — only the
  three pytest files.
- Round 2 working tree (`git diff --stat`): only the six test files +
  `fleet-snapshot.json` are mine (the other modified/untracked files in the
  tree belong to qa-chaos, listed above). No `src/sdlc` file touched, so mypy
  is unaffected. No `interfaces/**/src` production file (non-test, non-fixture)
  touched.

## 4. Honestly-unreachable-pin analysis

1. **Pin 5's decoration assertions are green today at runtime.** Feeding the
   recorded FINAL states through `toCanvas` today already decorates architect
   `done` at `$1.87`, keys `pendingByNode.architecture` =
   `[{node:'architecture', key:'architecture#1', kind:'gate'}]`, renders the
   revise loop `counter {used: 2, max: 2}` and the `skipped` context status —
   the adapter is shape-tolerant and the states arrive via the blessed casts.
   The pin's RED carrier is the **outcome-on-CanvasModel** assertion
   ("with the outcome present"): I pinned `model.outcome` exposing the run's
   outcome (`running` / `escalated`+reason / `completed`+result). That is my
   best-faith reading of the brief; if the ruled surface for the outcome is
   the store/view rather than the canvas model, move that assertion there —
   flagged rather than forced.
2. **Pin 1's completed-half is green today for the wrong reason**: an
   outcome-shaped body has no `terminal`, so `undefined !== null` reads final
   and the chain ends. The running-half (`expected 1 to be 2`) carries the
   RED; post-fix both halves pass for the right reason
   (`outcome.state !== 'running'`).
3. **The null-fallback pin is green by design.** "stageMarks null keeps
   today's linear behaviour EXACTLY" cannot fail on the pre-fix tree (the
   field does not exist yet); it exists to go red if the fix breaks the
   FeatureWorkflow linear fallback. All other pins carry live RED.
4. **Pin 4 drives `graph.onDecision` directly** rather than `api.decideGate`,
   because decideGate routes through the mock's seeded inbox
   (`architecture#2` today), which the swap rewrites anyway — this keeps the
   pin on the scripted-state surface the brief names and avoids a
   rejection-shaped (non-assertion) failure today. The first assertion in
   each mock test (initial recorded state) fails as a clean assertion diff
   before any decision call.

Seat clear: 16 new tests total (5 pytest + 11 vitest), 15 assertion-RED now,
1 deliberate preservation pin; both rounds verified RED on the pre-fix tree.
