# RED-set report — qa-chaos seat (bug canvas-run-mode, E75-OQ-1 option (a))

- **Seat**: qa-chaos (Claude). **Date**: 2026-09-20.
- **Worktree**: `D:\own\Kroker-bug`, branch `fix/canvas-run-mode` (base main `36baf5b`).
- **Scope**: chaos/edge RED contracts around the ruled wiring — capability flip
  sites, FINAL wire shapes the provisional mirror mishandles, stale fixture
  artifacts, marks edge cases, banner honesty. All rows are assertion-RED on
  the pre-fix tree and were individually observed failing; none were forced.
- **Companion reports**: qa-happy RED set committed as `282831b` (pytest) plus
  their concurrent frontend rows (see §6).

## 1. Adopted pre-draft — `tests/test_dashboard_canvas_run_mode_chaos.py`

Adopted verbatim into the RED set by the orchestrator ruling (bug-lead verified
RED 4/4). **Nothing was added to it after adoption.** File remains untracked;
the bug-lead commits it. Axes: stale state (three declaration sites pinned to
the same ruled set, so a half-landed flip fails the test naming the stale
side), boundary (exact four-key alias set), error path (fixture wire-validity
parse), concurrency (documented N/A — pure function + static files).

| Test | Exact observed failing assertion |
|---|---|
| `test_capability_defaults_are_the_ruled_flip` | `AssertionError: E75-OQ-1 (a): flip the defaults, got {'validate': False, 'save': True, 'load': True, 'run_graph': False}` (differing items: `run_graph`, `validate`) |
| `test_runtime_catalog_declares_the_ruled_capabilities` | `AssertionError: E75-OQ-1 (a): catalog must declare the flip, got {'validate': False, 'save': True, 'load': True, 'run_graph': False}` |
| `test_shipped_catalog_fixture_declares_the_ruled_capabilities` | `AssertionError: catalog.json is stale: run python scripts/dump_graph_fixtures.py` (fixture caps `run_graph/validate: False` ≠ ruled) |
| `test_no_provisional_recordings_survive_the_swap` | `AssertionError: provisional recordings must be deleted in the swap: ['run_graphs.provisional.json', 'validation.provisional.json']` |

Iteration evidence: `.venv\Scripts\python.exe -m pytest tests/test_dashboard_canvas_run_mode_chaos.py -v`
→ **4 failed in 5.49s** (all AssertionError, no collection errors).
`uv run --frozen ruff check` / `ruff format --check` on the file: clean.

## 2. Frontend RED pins (round 2)

### `interfaces/dashboard/frontend/src/api/http-graph.chaos.test.ts`

| Test | Exact observed failing assertion |
|---|---|
| `an outcome-shaped running state is non-final: changed pending keeps polling` | `expected 1 to be 2 // Object.is equality` (at the `expect(statePolls).toBe(2)` line — the chain stops after one fetch because the body has no `terminal` and `undefined !== null` reads final) |

Follows the file's fake-timer + `{ jitter: 0, random: () => 0.5 }` determinism
pattern; asserts the second delivery carries the changed pending
(`architecture#2`).

### `interfaces/dashboard/frontend/src/adapters/graph.test.ts`

| Test | Exact observed failing assertion |
|---|---|
| `an unattributed pending is keyed nowhere; skipped and cancelled pass through as statuses` | `expected [ 'null', 'architecture' ] to deeply equal [ 'architecture' ]` — the null node coerces to a `"null"` key in `pendingByNode` |

The skipped/cancelled pass-through clauses ride in the same test (they are
green at the adapter today — see §4.3); the red core is the coerced key. Cast
pattern: one `as unknown as GraphStateResponse` on the outcome-shaped literal.

### `interfaces/dashboard/frontend/src/composables/composables.test.ts`

| Test | Exact observed failing assertion |
|---|---|
| `marks present but EMPTY renders every canonical stage skipped, never the linear fallback` | `expected [ 'done', 'done', 'active', …(2) ] to deeply equal [ 'skipped', 'skipped', …(3) ]` |
| `a non-canonical marks key renders nothing and is not an activeStages product fault` | `expected [ 'pending', 'pending', …(3) ] to deeply equal [ 'skipped', 'skipped', …(3) ]` (console.error spy asserted silent — rule 3 governs activeStages names only) |

Added after qa-happy's verbatim/null rows in the same describe — complementary
angles, no duplication; adopts their `as never` literal pattern.

### `interfaces/dashboard/frontend/src/views/RunView.test.ts` (new)

| Test | Exact observed failing assertion |
|---|---|
| `an unavailable graph_state (retention_expired) shows an honest banner, not an empty canvas` | `expected false to be true // Object.is equality` (`run-graph-state-unavailable` banner absent today) |
| `without the run_graph capability the banner no longer claims E-75` | `expected 'Graph view arrives with E-75.' not to contain 'E-75'` |

Proposals embedded in these pins (decision points for the fix):
- testid **`run-graph-state-unavailable`** for the retention/drift banner —
  `run-graph-unavailable` is already taken by the capability banner
  (RunView.vue:60); copy containing *"no longer available"*.
- honest capability-banner copy containing *"not available on this server"*.

### `interfaces/ui/src/components/graph_canvas/graph_canvas.spec.ts`

| Test | Exact observed failing assertion |
|---|---|
| `renders a skipped node with its stable class, not the GRAPH_CANVAS-4 throw`  // clause: GRAPH_CANVAS-4 | `expected [Function] to not throw an error but 'Error: GraphCanvas: unknown status "s…' was thrown` |
| `renders a cancelled node with its stable class, not the GRAPH_CANVAS-4 throw`  // clause: GRAPH_CANVAS-4 | `…unknown status "c…' was thrown` |

jsdom finding: vue-flow node slots never render in jsdom (probed: even a known
`running` status renders no class), so the rows stub only the VueFlow renderer
to surface GraphCanvas's own node template — the class assertion tests real
component code, and the throw still fires from GraphCanvas's own setup
(`assertStatuses`), which is the RED mechanism.

## 3. Iteration command evidence (frontend)

| Command | Result |
|---|---|
| `npm run test --workspace sdlc-dashboard -- src/api/http-graph.chaos.test.ts` | 1 failed \| 35 passed (36) |
| `npm run test --workspace sdlc-dashboard -- src/adapters/graph.test.ts src/composables/composables.test.ts src/views/RunView.test.ts` | 9 failed \| 31 passed (40) — 5 mine + 4 qa-happy concurrent |
| `npm run test --workspace sdlc-dashboard -- <all 4 files>` (final) | 10 failed \| 65 passed (75) — 6 mine + 4 qa-happy |
| `npm run test --workspace @kroker/ui -- <canvas + issue_list>` | 2 failed \| 12 passed (14) |
| `npm run test --workspace @kroker/ui -- <canvas>` (final, after stub type fix) | 2 failed \| 7 passed (9) |
| `npm run typecheck --workspace sdlc-dashboard` | green (covers RunView.test.ts) |
| `npm run typecheck --workspace @kroker/ui` | green after fixing the stub slot signature (TS2554, caught by vue-tsc not vitest) |

All failures are assertion failures, none are errors/collection failures.
`node_modules` was absent in this worktree; installed via `npm ci` at the repo
root (check_ui's own first step).

## 4. Honestly-unreachable-pin analysis (nothing forced)

1. **Unavailable body at the provider level (pin 1, first half) — GREEN today
   by accident, not pinned.** The body has no `terminal` field, so
   `state.terminal !== null` is accidentally true; the chain already ends with
   exactly one fetch, one delivery, no retries, no onError — observably
   identical to the FINAL contract. Verified empirically (probe passed in the
   35). A comment in the chaos file records this; the honest unavailable-red
   is the RunView banner (§2). Store-level note: `receive()`'s sha guard checks
   `kind === 'state'`, so an unavailable delivery cannot trip it.
2. **IssueList `not_executable` (pin 4) — cannot be made assertion-RED on this
   surface.** The component is a pure interpolator: `:class` =
   `` `cmp-issue-${severity}` `` renders any severity string, and ISSUE_LIST-1
   pins supplied order (the interleaved chaos row pins *no* sorting;
   issue_list.md: "the component never reclassifies"). Probe row passed 6/6
   including `cmp-issue-not_executable` and after-order; the recorded
   validation fixture is `['not_executable', 'not_executable']` (no
   errors/warnings), so "orders after" is supplied-order semantics. The only
   gaps are the severity *union* (typecheck-only red, excluded by the
   dispatch) and the mock's provisional fixture (the swap's surface). The
   probe was reverted; the row can ride C1 as a landing-green regression row
   if the bug-lead wants it.
3. **skipped/cancelled pass-through at the adapter — green today** (`node.status
   = run.status` is verbatim, no validation); its red surface is the canvas
   throw (pinned in §2). The pass-through clauses are asserted inside the
   null-pending test, whose red core is the coerced `"null"` key.
4. **Concurrency — N/A** for this fix surface (pure catalog function + static
   committed fixtures; run-graph query caching is landed E-75/E-77 surface,
   out of scope). No fake threading tests were fabricated.

## 5. Flagged items for the bug-lead

- **pw tier / showcase profile**: class *rendering* for the new statuses in a
  real browser needs a showcase profile carrying `skipped`/`cancelled`;
  `graph_canvas.profiles.ts` is a source file — out of my test-only charter.
  Belongs to C1 if wanted. My jsdom rows cover no-throw + the class via the
  VueFlow stub.
- **Testid/copy proposals** in §2 RunView need a ruling at fix time
  (`run-graph-state-unavailable`, the two copy fragments).
- **`not_executable` IssueList row** (§4.2) — include as C1 landing-green or
  drop.

## 6. Confirmations

- **No production code touched.** Touched paths, all test files:
  `tests/test_dashboard_canvas_run_mode_chaos.py` (adopted pre-draft, §1),
  the four modified `*.test.ts` files + new `RunView.test.ts` (§2).
  `issue_list.spec.ts` was probed and reverted byte-identical (no diff).
  Concurrent modifications in `graph.test.ts`/`composables.test.ts` and the
  four other modified files (`fleet.test.ts`, `http-graph.test.ts`,
  `http.test.ts`, `mock/graph.test.ts`, `fleet-snapshot.json`) are qa-happy's,
  not mine.
- **No recorded fixtures edited. No commits made** (bug-lead verifies and
  commits). Deterministic on any machine: fixtures/mocks only, fake timers
  only in the file's existing pattern, no network, no token spend, no
  Temporal.
- vue-tsc green on both workspaces; mypy unaffected (no Python changes in
  round 2); ruff clean on the pytest file.
