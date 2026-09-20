# Bug Assessment: canvas run-mode wiring (E75-OQ-1 option (a))

- **Slug**: canvas-run-mode
- **Created**: 2026-09-20
- **Source**: pasted text — `.workspace/tmp/canvas-run-mode-brief.md` (E75-OQ-1
  follow-up task brief, orchestrator-ruled; direction pre-ruled, gate is a
  SCOPE GATE)
- **Verdict**: valid (deterministic; grounded in code + recorded fixtures)
- **Severity**: medium (a landed feature family is dark against live data; no
  data risk. Landing the flip WITHOUT the mirror catch-up would hard-crash
  RunView — GraphCanvas throws on unknown node status — which is why the
  change is atomic)

## Report (verbatim or summarized)

GOAL (brief): activate the canvas RUN MODE against live data. The E-76 canvas
run mode exists but is exercised only on the mock provider; the server
declares `run_graph: false` / `validate: false`, so the http provider refuses
the E-75 run-graph routes. The design is ALREADY RULED — this is wiring:
flip the two capabilities, amend the TS mirror to the FINAL E-75 wire
shapes, swap the provisional fixtures, map `stage_marks` for the fleet strip
— ONE ATOMIC CHANGE (E75-OQ-1 resolution, option (a)).

## Symptom

With the http provider against a live server, run mode never renders: the
catalog declares `run_graph`/`validate` false, so `http-graph.ts` throws
`CapabilityUnavailable` before fetching, RunView shows the stale banner
"Graph view arrives with E-75." (false since E-75 landed), and the fleet
strip linearly infers marks (`http.ts` ignores the served `stage_marks` /
`closed_marks`), so `skipped` stages never render (E76-OQ-3's served-but-
not-shown gap). Expected: the flipped capabilities + FINAL TS mirror +
recorded fixtures make run mode and exact strip rendering work on live data.

## Reproduction

1. Serve the dashboard against a live backend (http provider).
2. Open any GraphWorkflow run (`/runs/{id}`): `runGraph.start` stops at
   `stores/runGraph.ts:71` (`can('run_graph')` false) → RunView.vue:60
   banner.
3. Open `/graphs`: editor validation inert (`graphEditor.ts:55`
   `can('validate')` false).
4. Fleet strip for a graph run: `mapRun`/`mapClosed` (http.ts:61-91) never
   read `s.stage_marks` / `snap.closed_marks` → linear fallback.

No [NEEDS CLARIFICATION] items — the ruling and evidence are complete.

## Suspected Code Paths

Backend (all verified on 36baf5b):

- `src/sdlc/dashboard/graph_wire.py:119-122` — `Capabilities`: `validate`
  alias False, `save`/`load` True (E-77), `run_graph` False. THE ONLY
  backend change in scope.
- `src/sdlc/dashboard/api.py:227,280,298` — `/graphs/validate`,
  `/runs/{run_id}/graph`, `/runs/{run_id}/graph_state` exist and are
  Python-tested (E-75/E-77). NOT to be touched.
- `src/sdlc/dashboard/api.py:297-302` — graph_state route response union is
  `GraphState | GraphStateUnavailable | NoGraph` (E-77 added `unavailable`:
  `registry_drift` / `retention_expired`).
- `src/sdlc/dashboard/graph_wire.py:418-475` — FINAL wire models:
  `NodeRunState.status` Literal incl. `skipped`/`cancelled` + E-77's
  `canonical_stage: str | None`; `PendingRef.node: str | None`; kind
  gate/clarify/escalation; `EdgeRunState` (back edges only);
  `RunOutcomeWire{state,reason,result}`; `GraphState.outcome`;
  `GraphStateUnavailable`; `Issue.severity` incl. `not_executable`
  (:290).
- `src/sdlc/dashboard/fleet.py:69-88` — `FleetSnapshot.runs` (RunState rows
  carry `stage_marks`) + `closed_marks: dict[run_id, marks]`;
  `GET /inbox` (api.py:131) serves it verbatim.

Frontend (all verified):

- `interfaces/dashboard/frontend/src/api/graph-types.ts:118-150` — TS mirror
  still PROVISIONAL (see inventory below for the gaps).
- `interfaces/dashboard/frontend/src/api/http-graph.ts:62-84` — both run
  routes capability-gated; poll finality at :76 is `state.terminal !== null`.
- `interfaces/dashboard/frontend/src/api/http.ts:10,67,83` — `stagesOf`
  linear inference only; no `stage_marks`/`closed_marks` consumption.
- `interfaces/dashboard/frontend/src/views/RunView.vue:60` — stale banner.
- `interfaces/dashboard/frontend/src/stores/runGraph.ts:71`,
  `src/views/GraphEditorView.vue:25` — capability gates.
- `interfaces/dashboard/frontend/src/api/mock/graph.ts:12-13,25,74-78` —
  mock consumes the two PROVISIONAL fixtures; overrides caps all-true.

## Root Cause Hypothesis

Deliberate staged rollout, not an accident: E-75 landed backend-only per
E75-OQ-1 option (a) (design §12, `2026-09-17-graph-queries-design.md:371-376`
+ §7.4 :295-324). The capabilities stayed false and the TS mirror stayed
PROVISIONAL so no provisional consumer could observe the breaking
`terminal` → `outcome` change; the recorded fixtures
(`run_state/*.recorded.json`) are the FINAL contract. The cause of the
symptom is simply that the ruled follow-up (flip + mirror catch-up + fixture
swap + stage_marks mapping, as one atomic change) has not landed. The
recorded fixtures prove the server-side shapes are already FINAL on main
(e.g. `validation.recorded.json` carries `severity: "not_executable"`;
`graph_state.recorded.json` carries `outcome`, `skipped`, `cancelled`).
Confidence: high.

## SCOPE GATE (a): full consumer / fixture inventory

Verified by grepping every symbol across `interfaces/dashboard/frontend/src`
and reading each hit. The brief's coupling list was a starting point; the
items marked **[NEW]** are additions this assessment found.

### A1. TS mirror gaps (`graph-types.ts`) vs the FINAL Python wire

| mirror location | provisional today | FINAL target (graph_wire.py) |
|---|---|---|
| :124 `NodeRunStatus` | idle/running/blocked/done/failed/stale | + `skipped`, `cancelled` (:421) |
| :126-132 `NodeRunState` | 5 fields | + `canonical_stage: str \| None` (**[NEW]**, :428, E-77 US3; present in recorded fixture nodes) |
| :134-138 `PendingRef` | `node: string` | `node: string \| None` (:441); kind stays gate/clarify/escalation (:443) |
| :140-150 `GraphStateResponse` | `terminal: null \| 'done' \| 'failed' \| 'escalated'` (:149) | `outcome: RunOutcomeWire{state: running\|completed\|rejected\|escalated\|failed, reason, result}` (:446-463); **[NEW]** union member `unavailable` (`GraphStateUnavailable` :466-475, served by api.py:298-302) |
| :96-101 `Issue.severity` | error/warning | + `not_executable` (:290) |
| unchanged | `GraphResponse`, `NoGraph`, `ValidationWire`, `IssueTarget`, `EdgeRunState` shape | confirmed unchanged |

### A2. Every TS consumer of the changed symbols (production code)

- `api/http-graph.ts:76` — poll finality `state.terminal !== null` → must
  become outcome-based and treat `unavailable` as final.
- `api/http.ts` — `mapRun` (:61-75) must read `s.stage_marks`; `mapClosed`
  (:77-91) must read `snap.closed_marks[run_id]`; `mapSnapshot` (:129-146)
  threads `closed_marks`; `startRun` fallback literal (:200-207) gains the
  new Run field.
- `api/types.ts:18-32` — `Run` gains a marks field (proposed:
  `stageMarks: Record<string, DotState> | null`, null = linear fallback).
- `composables/stageState.ts:13-40` — E-76 §9.1 rule 1 branch: marks
  present → render verbatim in `canonicalStages` order, absent stage →
  `skipped`; null → today's linear fallback unchanged.
- `adapters/fleet.ts:10-16` — threads the marks into `toStageDots`.
- `adapters/graph.ts:167` — `pendingByNode[p.node]` keyed by a now-nullable
  node; unattributed pendings must be skipped (no node to anchor to; the
  inbox is their surface). `:119` `severity: issue.severity` now feeds
  `not_executable` into `IssueItem` (see A4). `:135` `node.status =
  run.status` now feeds `skipped`/`cancelled` into `CanvasNode` (see A4).
- `views/RunView.vue:60` — banner copy is false after E-75; must be updated/
  removed; **[NEW]** an `unavailable` state (registry_drift /
  retention_expired) needs an honest banner instead of an empty canvas.
- `stores/runGraph.ts:37-57` — `receive()` already guards
  `next.kind === 'state'`; mostly type-driven; `state.kind === 'unavailable'`
  must not trip the sha guard.
- `stores/graphEditor.ts:43-44,55` — `errorCount` filters
  `severity === 'error'` only; by design (§7.3) `not_executable` is NOT an
  error (a not_executable graph stays saveable/runnable in the editor;
  starting refuses it). Behavior unchanged; pin with a test.

### A3. @kroker/ui couplings — **[NEW], hard requirements** (see escalations)

- `ui/src/components/graph_canvas/types.ts:5-7` — `CanvasStatus` lacks
  `skipped`/`cancelled`; `GraphCanvas.vue:64-69` THROWS on an unknown
  status, so the flipped run view would crash rendering real recorded data
  (context node is `skipped`; interrupted run's architecture node is
  `cancelled`). Widening + CSS classes + `graph_canvas.md` clause required.
- `ui/src/components/issue_list/IssueList.vue:4` — `IssueItem.severity` is
  `'error' | 'warning'`; `not_executable` must be accepted (adapter passes
  wire severity through at adapters/graph.ts:119) or the dashboard
  typecheck fails. Widening + `cmp-issue-not_executable` class +
  `issue_list.md` clause required.
- `ui/src/components/stage_dots/StageDots.vue:4` — `DotState` already
  includes `skipped` (with CSS :43). Unchanged; this is E76-OQ-3's
  served-but-not-shown readiness.

### A4. TS test files pinned to old shapes (every one moves)

- `api/http-graph.test.ts` — :74-90 poll test body uses `terminal` →
  outcome-shaped; :64-72 "never polls while run_graph is not declared"
  leans on the recorded catalog staying false → must pin an explicit
  no-caps catalog (the :56 pattern) or it breaks when catalog.json
  regenerates all-true; add an `unavailable`-ends-the-chain case. **[NEW]**
- `api/http-graph.chaos.test.ts` — :48-49 `stateBody(terminal)` helper →
  outcome-shaped; :19-20 NO_CAPS/ALL_CAPS fine; :128-134 refusal cases fine
  (explicit caps); :239 mock-advanced assertion moves with the mock swap;
  :293 `severity: 'warning'` stays valid.
- `api/mock/graph.test.ts` — :16-23 pins recorded catalog caps
  `{validate:false, run_graph:false}` and mock's all-true override → both
  lines move at the flip (rationale in diff); :87-124 run-script tests
  (pending `architecture#2`, approve → `current_nodes: ['planner']`, revise
  bumps traversals to 2) are pinned to the PROVISIONAL script → rewritten
  over the recorded scenarios (blocked_at_architecture → approve →
  completed / reject → rejected_at_architecture; traversals asserted
  statically on escalated_revise_exhausted's recorded revisal count of 2 —
  no recorded interactive-revise state exists).
- `api/mock/index.test.ts` — :6,46,62,74,81 Run literals/activeStages pins;
  gains `stageMarks` fields; graph-demo seed asserts marks-backed strip.
- `api/http.test.ts` + `api/__fixtures__/fleet-snapshot.json` — mapSnapshot
  tests; fixture gains a graph run row with `stage_marks` (incl. a
  `skipped` value) and a `closed_marks` entry; new cases: verbatim
  rendering, absent-stage → skipped, null → linear fallback,
  closed graph row marks, FeatureWorkflow rows unchanged.
- `adapters/graph.test.ts` — :5,:84-85,:102 consume
  `run_graphs.provisional.json` → re-source from
  `run_state/graph_state.recorded.json` (+ `graph_response.recorded.json`
  for the graph under test) or outcome-shaped literals; :160-168 literal
  gains `outcome`; traversal assertions move to the escalated recording;
  **[NEW]** unattributed-pending case (`node: null` not keyed, not thrown).
- `adapters/fleet.test.ts` — `mkRun` literal gains `stageMarks`; new
  marks-verbatim + skipped + fallback cases.
- `stores/runGraph.test.ts` — :20-23 state factory `terminal: null` →
  `outcome`; caps set explicitly (:33) so unaffected by catalog regen.
- `stores/graphEditor.test.ts` — :117,:198-200 severity literals stay
  valid; **[NEW]** pin `not_executable` ≠ error in `errorCount`/`runnable`.
- `composables/composables.test.ts`, `components/fleet/FleetTable.test.ts`,
  `App.test.ts` — Run literals gain the new field if it is required
  (constructor sweep; tiny diffs, `stageMarks: null`).
- `stores/graphEdits.test.ts`, `api/seam.test.ts`, `api/client.test.ts`,
  `api/poll*.test.ts`, `constants.test.ts` — no affected symbols (checked);
  only move if the required-field sweep touches shared fixtures.

### A5. Python pin tests (pytest)

- `tests/test_dashboard_graph_wire.py:90-95` — caps pin
  `{validate: False, run_graph: False}` → all-true; comment/rename with
  rationale.
- `tests/test_dashboard_run_graph_routes.py:172-180` —
  `test_capabilities_stay_false` → same flip, same rationale.
- `tests/test_dashboard_graph_routes.py:226-232` — reads today's caps
  dynamically (`== today[...]`), self-consistent across the flip; likely
  rename/comment only.
- `tests/test_graph_fixtures_fresh.py:30,:42-45` — `PROVISIONAL` set pins
  the two provisional files as allowed strays → becomes empty (or the check
  inverts to "no strays") with rationale; :147-168 recorded-set pins stay.
- Backend tests already covering the FINAL shapes (routes, projections,
  fleet marks) are untouched and must stay green unchanged.

### A6. Fixture machinery

- `scripts/dump_graph_fixtures.py` — unchanged code-wise; docstring line
  "No frontend code reads them yet; the canvas follow-up swaps them in"
  becomes stale → one-line doc update with rationale. Run it after the
  flip; only `catalog.json`'s capabilities block changes (verified:
  `catalog.json:1560-1564`).
- Deleted: `__fixtures__/graph/validation.provisional.json`,
  `__fixtures__/graph/run_graphs.provisional.json`.
- Mock swap sources: `run_state/graph_state.recorded.json` (7 scenarios),
  `run_state/graph_response.recorded.json`,
  `run_state/validation.recorded.json` (single ValidationWire for pre_code;
  mock answers it for the pre_code scenario and `mock.unrecorded`
  otherwise — recording semantics preserved).

## SCOPE GATE (b): atomic change plan

Commit decomposition (each commit keeps pytest fast tier + fixture freshness
+ `ruff check` / `ruff format --check` / `mypy` / `scripts/check_file_size.py`
+ `python scripts/check_ui.py` green — the brief's atomicity rule):

- **C1 — ui additive unions** (green independently; widens only):
  `CanvasStatus` += `skipped`/`cancelled` (+ CSS classes in GraphCanvas.vue,
  clause row in graph_canvas.md); `IssueItem.severity` +=
  `not_executable` (+ class, issue_list.md clause); additive ui spec rows per
  the clause-citation rules. No dashboard change.
- **C2 — TS catch-up to the recorded FINAL contract** (caps still false —
  the http provider gates before fetching, so no server/TS mismatch is
  observable; mock serves recorded shapes with its caps override):
  `graph-types.ts` FINAL mirror (outcome, unavailable, canonical_stage,
  skipped/cancelled, not_executable, nullable PendingRef.node);
  `http-graph.ts` outcome-based finality + unavailable-final;
  `adapters/graph.ts` null-node skip; Run.stageMarks + http.ts
  stage_marks/closed_marks mapping; stageState §9.1 rule 1; RunView banner
  copy + unavailable banner; mock swap to recorded fixtures + delete the
  two provisional files + freshness PROVISIONAL pin → empty; all A4 test
  updates; mock seeds gain stageMarks; dump script docstring line.
- **C3 — the flip**: graph_wire.py :119/:122 → True (+ capabilities
  docstring); regenerate catalog.json; update the two caps pins
  (A5) + mock/graph.test.ts recorded-caps assertion + mock caps-override
  comment; test_dashboard_graph_routes.py rename if needed.
- **C4 — docs, only after a 'verified' verdict** (brief's doc duty):
  roadmap tick `docs/roadmap/pipeline-as-data.md:158-162` (canvas-run-mode
  part only; leave the fail-edge axis and E75-OQ-2/3/4 siblings);
  `.specify/specs/001-canonical-stage-graph-sha/spec.md:108` phrase; E-75
  design §12 E75-OQ-1 "landed" annotation; E-76 spec §5.7 pointer refresh.

Single-commit fallback: C2+C3 in one commit if any gate ordering surprise
appears (the brief permits it). C1 may not merge into C2+C3: the ui widening
must exist before the dashboard mirror references the new values, or the
typecheck gate is red mid-sequence.

Gate order per commit: `uv run --frozen` ruff/format/mypy/check_file_size →
`.venv\Scripts\python.exe -m pytest` (fast tier; no pytest-timeout
installed) → `python scripts/check_ui.py`. No Temporal, no e2e, no new
Playwright suites (check_ui's pw step runs the ui package's existing specs).

### RED regression tests (step 2, before any fix work)

qa-happy + qa-chaos extend the existing suites in place; deterministic on
any machine (fixtures/vi.fn only, no timers beyond existing fake-timer
patterns):

- happy: catalog caps all-true (pytest, RED now); poll ends on
  `outcome.state !== 'running'` and on `unavailable`; mapSnapshot renders
  stage_marks verbatim / absent→skipped / null→linear fallback / closed
  graph row from closed_marks; mock serves recorded blocked→approve→
  completed and →reject→rejected; recorded fixtures typecheck against the
  mirror (import JSON, assert assignable to GraphStateResponse).
- chaos: `unavailable` stops the poll without an unhandled rejection and
  RunView shows a banner (store/view level); `PendingRef.node: null` is not
  keyed into pendingByNode and does not throw; `skipped`/`cancelled` node
  statuses render stable classes (no GraphCanvas throw); `not_executable`
  does not raise editor errorCount and renders its own issue class; a
  `stage_marks` key outside the canonical list (e.g. `unknown`) renders
  nothing and is not reported as an activeStages product fault; running
  outcome keeps polling.

## Proposed Remediation

**Preferred**: exactly the ruled E75-OQ-1 option (a) wiring as decomposed
above — flip the two booleans (only backend change), amend the TS mirror to
the FINAL wire (including the two E-77-era additions the brief's §7.4 list
predates: `unavailable` and `canonical_stage`), swap the mock to the
recorded fixtures, map stage_marks/closed_marks for the strip with the
FeatureWorkflow linear fallback intact, and keep RunView's copy honest.

**Alternatives**: none within the ruling. (Mapping new statuses/severities
onto old display values in adapters was rejected: it would re-hide `skipped`
— the exact gap E76-OQ-3 closes — and `not_executable` — E-74 OQ-4's
distinct severity.)

**Files likely to change**: A2/A3/A4/A5/A6 lists above (≈30 files + 2
deletions, dominated by test updates and one regenerated fixture).

**Tests to add or update**: the RED list above; every updated pin carries
its rationale in the diff/commit message (brief constraint).

## Risks & Considerations

- **ui package scope** (escalation 1): the ruling's letter says "amend
  graph-types.ts", but GraphCanvas's unknown-status throw and IssueList's
  narrow severity make the two ui widenings non-optional. Flagged for
  clearance.
- **Run.stageMarks required vs optional**: proposed required-with-null
  (explicit fallback, ~6 constructor sites touched); optional field would
  shrink the diff but hide forgotten seeds. Red tests pin behavior either
  way; final call at fix time.
- **check_ui cost**: full npm pipeline per commit; acceptable, but C2 and C3
  are the two mandatory full-gate commits (C1's gate is cheaper: ui
  typecheck/vitest/pw only — still via check_ui).
- **Behavior activation, not just types**: flipping `validate` makes the
  editor's debounced auto-validation live against the real validator
  (graphEditor.ts:54-68) — intended, but the graphEditor test suite must
  stay honest about it.
- **Replay neutrality**: no workflow commands, SG-3 goldens untouched —
  backend diff is two booleans + regenerated catalog; verified no other
  backend surface moves.

## Open Questions (for the gate ruling)

1. **Escalation 1 — @kroker/ui widenings** (CanvasStatus += skipped/
   cancelled; IssueItem.severity += not_executable, + CSS + clause docs +
   additive spec rows): required for typecheck and to avoid a runtime throw;
   confirm in scope.
2. **Escalation 2 — mirror additions beyond the brief's §7.4 list**:
   `GraphStateUnavailable` union member (+ poll-final + RunView banner) and
   `NodeRunState.canonical_stage` (additive optional). Both already on the
   wire (E-77); recorded fixtures prove it. Confirm in scope.
3. **Escalation 3 — mock interactive-revise flow**: no recorded state for
   "revise then still running" exists; propose the mock script becomes
   blocked → approve → completed / reject → rejected_at_architecture, with
   traversal counts asserted on the escalated recording. Confirm
   acceptable.
4. **`unknown` marks key**: E-77 lets stage_marks carry an `unknown` key
   (not a canonical stage). Proposal: it renders nothing (§9.1 rule 1
   iterates canonical stages); NOT treated as the rule-3 product fault
   (that path governs activeStages names). Confirm.
