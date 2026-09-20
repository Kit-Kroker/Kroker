# E-75 — dashboard graph queries (FR-1204) — design

| | |
|---|---|
| Epic | E-75 (pipeline-as-data) → FR-1204 |
| Date | 2026-09-17 |
| Status | **user-approved (2026-09-17)**: E75-OQ-1 = (a) backend-only; E75-OQ-2…4 accepted deferrals; R-Q2 confirmed (§12). Reviewer-approved 2026-09-17 (round 3 after two CHANGES REQUESTED rounds); skeptic round dispositioned (§13) |
| Normative text | `PRD.md` §6 FR-1204 (FR-1205 for the consumer) |
| Frozen contracts | E-72 `2026-09-13-graph-model-node-registry-design.md`; E-73 `2026-09-14-graph-router-and-validator-design.md` (+ §6.7 erratum); E-74 `2026-09-15-graph-workflow-cutover-design.md` (D3, D5, D7, §5.4–§5.7, §8.1) |
| Consumer contract | E-76 `2026-09-14-graph-canvas-design.md` §5.5–§5.8, §9, §9.1 (PROVISIONAL shapes this spec amends and promotes) |
| Consultation log | `.workspace/tmp/` (uncommitted scratch): advisor `e75-consult-q1.md` → `advisor-e75-q1.md`; skeptic brief `e75-skeptic-brief.md` → `e75-skeptic-full.md` (F1–F12, §13); reviewer brief `e75-reviewer-brief.md` → `e75-reviewer-r1.md` (§13.1), `e75-reviewer-r2.md` (§13.2), `e75-reviewer-r3.md` (**APPROVED**; its advisory on failed closed-marks queries folded into §5.3) |

## 1. Purpose and deliverable

FR-1204: the dashboard backend SHALL expose the graph a run executes and its
per-node state (status, cost, duration, traversal counters) beside the
existing run queries; graphs SHALL be stored content-addressed
(`graphs/<sha>.yaml`); there is no graph database.

E-75 is **backend-only** (orchestrator ruling Q1). It lands:

1. a pure run-view layer in `sdlc/graph/run_view.py` (facts model, status
   projection, stage-mark aggregation, the activation context variable);
2. a `graph_view` query on `GraphWorkflow` plus memory-only bookkeeping in the
   dispatcher and hosts (per-activation timing, cost and pending attribution);
3. a content-addressed graph store `sdlc/graph/store.py`, written at client
   start and backfilled from history;
4. three dashboard routes — `GET /runs/{id}/graph`, `GET /runs/{id}/graph_state`,
   `POST /graphs/validate` — whose `graph_wire` models this spec amends and
   promotes to **FINAL**, recorded as fixtures from the real functions;
5. `RunState.stage_marks` for graph runs, so the fleet strip can render
   `skipped` exactly (E76-OQ-3), with an immutable per-run cache for closed rows;
6. discharges E74-OQ-1 (run outcome rendering incl. `completed:<sorted sinks>`)
   and E74-OQ-4 (`executable()` beside `validate`, distinct severity).

Catalog `capabilities` stay `false`: flipping them, the TS mirror amendment and
any canvas/fleet frontend change are the named canvas follow-up (§11, E75-OQ-1).

### 1.1 Family boundary (stated explicitly)

| concern | owner |
|---|---|
| content-addressed `graphs/<sha>.yaml` store + its write | **E-75** |
| deriving a run's graph and sha (from the start input in history) | **E-75**, interim |
| recording `graph_sha` on every run (so a post-mortem needs no history read) | **E-77** (FR-1206) |
| `canonical_stage` on every node type; unmapped types record `unknown` | **E-77** (FR-1206) — E-75 only *consumes* the registry value; a `None` contributes no stage mark |
| save/load routes (`POST /graphs`, `GET /graphs/{sha}`), capabilities `save`/`load` | E-77 (store already exists) |
| run mode wiring, capability flips, TS mirror | canvas follow-up (E-76 family) |

**Erratum (2026-09-20, E-77):** the save/load row above has landed — `POST /graphs` / `GET /graphs/{sha}` serve and capabilities `save`/`load` are `true` (spec `.specify/specs/001-canonical-stage-graph-sha/spec.md`).

**Erratum (2026-09-20, canvas run-mode wiring):** the "run mode wiring, capability flips, TS mirror" row has landed (bug flow `canvas-run-mode`, branch `fix/canvas-run-mode`) — `validate`/`run_graph` are `true`, `graph-types.ts` mirrors §7.4's FINAL shapes (plus E-77's `canonical_stage` and the `unavailable` member), the mock consumes the recorded `run_state/*` fixtures, and `http.ts` maps `stage_marks`/`closed_marks` for the fleet strip.

## 2. Rulings and decisions

### 2.1 Orchestrator rulings (pre-resolved, binding)

| # | ruling | how this spec realises it |
|---|---|---|
| Q1 | Backend-only; canvas wiring is a follow-up | §1, D7, §7.4; capabilities stay false |
| Q2 | E-75 owns the store write, on start, at a shared chokepoint; the query reads the store, never workflow internals | **Refined (R-Q2, §3 V1):** the hypothesised chokepoint `build_run_input` also runs inside the workflow sandbox (`pipeline_child.py:36`), where file I/O is illegal. The write is at the client start helper every *client* site uses (§6.1), and the graph route backfills from the run's **start input in history** — never from workflow memory. Flagged for the user gate. |
| Q3 | Current/final per-node state + traversal counters; per-attempt history is a NAMED NON-GOAL; cost/duration where instrumented, honest omission otherwise; source = router state + observability | §5, §7.2 |
| Q4 | Query handler reads router state in workflow memory and projects to a stable wire DTO at the query boundary; response carries Halt/run-level fields | **Split (D2):** the workflow returns raw facts (`GraphRunView`); the dashboard projects the wire DTO. Router state stays the single source; wire churn never needs a worker deploy. |

### 2.2 Design decisions

| # | decision |
|---|---|
| D1 | **Placement.** Pure models, projections and the context variable in `sdlc/graph/run_view.py` (purity pin entry: stdlib, pydantic, `sdlc.graph.router`, `sdlc.graph.topology`, `sdlc.graph.node_types`). Store in `sdlc/graph/store.py` (stdlib, `sdlc.graph.io`, `sdlc.graph.model`); `sdlc/workflows/` never imports it (pinned). Client start helper in `sdlc/graph/start.py` (pin entry: stdlib, `sdlc.graph.store`; no Temporal import even under `TYPE_CHECKING` — `client` is duck-typed, N3) (§6.1). Temporal code in `workflows/`. Routes and wire in `sdlc/dashboard/`. |
| D2 | **Raw facts out of the workflow.** `GraphWorkflow.graph_view() -> GraphRunView \| None`; the dashboard's `graph_wire.project_graph_state(view, topology, execution)` builds the wire DTO. The status mapping is one pure function (`run_view.node_status`) used by both the wire projection and the in-workflow stage marks. |
| D3 | **Payload store never exposed** (E-74 D3). `GraphRunView` carries `RouterState` (whose tokens are opaque refs) and facts; no `StoredPayload`, no payload content. |
| D4 | **Attribution by context variable.** `ACTIVATION: ContextVar[str \| None]` in `run_view.py` (passthrough module — one object per process). Set only as the first statement of the dispatcher's per-activation task; read by `ReportHost._track_usage` (cost bag) and `GateHost._gate` / `QuestionHost.ask_and_wait` (pending → activation). Never set elsewhere (pinned). |
| D5 | **Replay neutrality.** Every addition is memory-only (attributes, dict writes, `workflow.now()` reads at event time) — no commands. Pinned by the unchanged SG-3 goldens and `test_feature_replay.py`; neither is re-recorded. |
| D6 | **Graph source = start input.** `GET /runs/{id}/graph` decodes `GraphRunInput` from the first history event with the client's data converter; FeatureWorkflow runs answer `no_graph/legacy_run`. |
| D7 | **Capabilities stay false**; routes exist and are exercised by Python tests and recorded fixtures only. |
| D8 | **Closed runs are immutable.** Route- and fleet-side caches keyed by run id hold closed-run views/marks; a closed run is successfully queried at most once per process (a failed query is retried next tick). |

## 3. Verified anchors and corrected hypotheses

- **V1 (Q2 hypothesis disproven).** `build_run_input` callers: `cli.py:451`, `interfaces/dashboard/api/main.py:57` (client; the operator's `start_run` reaches it through the same starter) and `workflows/pipeline_child.py:36` (sandbox; tidy-up and benchmark parents).
- **V2.** `GraphDispatcher` is a local in `GraphWorkflow.run` (`graph.py:124`); no query can read `RouterState` today. GraphWorkflow queries: `run_summary`, `run_state`, and GateHost's `status`/`pending_gate`/`pending_decisions`. **No `graph_state` query exists** (E-74 §5.7 deferred it).
- **V3.** `RouterState.nodes[n] = {round, status: pending|running|done|dead, taken_port}`; `traversals` keyed by back-edge id; on terminate, retired activations' nodes stay `running`; region invalidation resets nodes to `pending` and keeps `round`.
- **V4.** Cost exists only per role (`report_host.py:50-87`); MODEL_USAGE events carry no node. The router has no timestamps.
- **V5.** Pendings: `gates.py:211` (`gate_key(name, round)`), `question_host.py` (question ids). A graph gate node's own pending key equals its activation id; handler-internal gates (`research`, merge, deploy, code escalation) and clarify questions do not. Crew-child escalations live in the child's `_pending`.
- **V6.** E-76 shipped PROVISIONAL wire models (`graph_wire.py:247-425`) and the http provider (`frontend/src/api/http-graph.ts`) already calls all three routes, gated only by catalog capabilities (all `false`, `graph_wire.py:102`). **Flipping a capability activates existing canvas code.** No `/graphs/validate` route exists; `graph_wire.validation()` does.
- **V7.** No GraphWorkflow replay histories; SG-3 goldens (`tests/replay/test_graph_golden.py`) pin the command projection. GraphWorkflow runs are in flight since 2026-09-17.
- **V8.** `fleet.py` never discriminates workflow types; closed runs (≤20) are `run_summary`-queried every tick (history replay each time).
- **V9.** `RunSummary.stages` exists (`list[StageOutcome]`); E-76 §5.8's proposed `RunState.stages` would collide with it.
- **V10.** Every seed node type declares `canonical_stage`; UI `DotState = pending|active|done|blocked|failed|skipped` (`interfaces/ui/.../StageDots.vue:4`).
- **V11.** temporalio 1.30.0: `WorkflowHandle.fetch_history_events` and `describe` exist (`client/_workflow.py:358,421`).

## 4. Workflow side

### 4.1 `sdlc/graph/run_view.py`

```python
ACTIVATION: ContextVar[str | None] = ContextVar("sdlc_graph_activation", default=None)

class ActivationFacts(BaseModel):       # frozen, extra="forbid"
    started_at: datetime
    ended_at: datetime | None = None
    cost_usd: float | None = None        # see §4.3
    priced: bool = True                  # False once any folded call was unpriced

class PendingFact(BaseModel):
    key: str
    activation_id: str | None            # None = opened outside any activation
    kind: Literal["gate", "clarify", "escalation"]

class GraphRunView(BaseModel):
    graph_sha: str                       # inp.graph.content_sha(), computed once in run
    state: RouterState
    activations: dict[str, ActivationFacts]   # activation id -> facts, sorted keys
    pending: tuple[PendingFact, ...]          # sorted by key; built from GateHost._pending
    result: str | None                        # the return string, set only after retro returns
    escalated_by: str | None                  # activation whose emission escalated (unavailable port)
    unrouted_failure: UnroutedFailure | None  # {activation_id, error_type}: an unrouted fail is re-raised
```

`NodeStatus` wire vocabulary and `node_status(node_id, view, topology, *, execution_closed=False)`
(§5.1), `StageMark` and `stage_marks(view, topology, graph, registry, *, execution_closed=False)` (§5.3)
live here too, so the workflow and the dashboard share one mapping.
`execution_closed` is passed `True` only by the dashboard (route projection,
fleet closed rows, from `describe`/visibility); the in-workflow `run_state`
never passes it — an open workflow cannot observe its own close (N2).
Per-attempt history is a **non-goal** (Q3): `activations` keeps every
activation's facts for the run's life (bounded by `max_traversals`), but the
wire projects only each node's latest activation.

### 4.2 Dispatcher and GraphWorkflow

- `GraphWorkflow.run` sets `self._graph_sha = inp.graph.content_sha()` and
  `self._dispatcher = dispatcher` **before** `await dispatcher.run()`. The
  dispatcher records `escalated_by` when an `Emitted` it applied returns
  `outcome == "escalated"`, and `unrouted_failure` (activation id, exception
  type name — never the message or payload, D3) when it stores a failure.
  `self._result` is assigned only **after `_retro` returns**, immediately before
  `return` (F3): during retro the view reads router `completed` with `result`
  unset, and a retro failure never leaves a success string on a failed run.
- `GraphDispatcher._start` records `ActivationFacts(started_at=workflow.now())`;
  `_one`'s first statement is `ACTIVATION.set(act.activation_id)`; `_loop`
  stamps `ended_at` when it dequeues the result (live or not); cancelled tasks
  are stamped when `_apply` cancels them.
- `GraphDispatcher.view(graph_sha, result, pending) ->
  GraphRunView` is the only reader of `_state` from outside; the workflow's
  query builds `pending` from GateHost's `_pending` joined with
  `_pending_activation` and passes it in.
- `@workflow.query def graph_view(self) -> GraphRunView | None`: sync,
  read-only, no `workflow.now()`; `None` until `_dispatcher` is set (covers
  validation failure and the watermark preamble).
- `run_state` fills `RunState.stage_marks` from the same view (§5.3); FeatureWorkflow leaves it `None`.
- Every workflow module naming `run_view` imports it under
  `imports_passed_through()` (Temporal-sandbox pydantic duplication trap).

### 4.3 Host attribution (shared hosts, memory-only)

- `ReportHost._track_usage`: `aid = ACTIVATION.get()`; when set and the host
  has an `_activation_cost` map, fold `cost_usd` into that activation's bag;
  an unpriced call (`cost_usd is None`) sets `priced=False`.
- `GateHost._gate` / `QuestionHost.ask_and_wait`: record `key -> ACTIVATION.get()`
  in `_pending_activation` beside the `_pending` write. `PendingFact`s are
  built by iterating **`_pending`** (the source of truth) and joining the
  attribution map, so a stale attribution entry can never surface a pending
  that `_pending` no longer holds (F2). `ask_and_wait` does not pop `_pending`
  on timeout today (the `TimeoutError` fails the execution, E-74 D8); E-75 does not
  change that, and the projection never shows `blocked` once the run outcome
  or execution is terminal (§5.1 row order, §7.2 closed runs list no pendings).
- FeatureWorkflow: the variable is always `None` → no-op. No command change
  (D5); workflows/AGENTS.md U6 grace-edit rule not triggered; ownership table
  gains the new attributes.
- **Wire `cost_usd` scope = the run total's scope (F12).** The only usage
  producer is `RoleHost._run_role` (`role_host.py:153`); coding-harness
  activities and crew children are not priced into `RunState.cost_usd_total`
  either. Node cost is therefore "priced model-role spend attributed to this
  activation", and the invariant `Σ node cost (all activations) +
  unattributed == cost_usd_total` is pinned by a test. `null` when the node
  type has no role (gates) or the activation had any unpriced call; otherwise
  the sum (may be `0.0`). Latest activation only. The `code` node's value
  therefore excludes harness/crew spend, exactly as the run total does; pricing
  harness spend is not E-75's (E75-OQ-4).

## 5. Projections

### 5.1 Node status (first match wins)

| router fact (latest activation) | wire `status` |
|---|---|
| `dead` | `skipped` (new) |
| `pending`, `round == 0` | `idle` |
| `pending`, `round > 0` | `stale` |
| `running`, its latest activation is `escalated_by` (F4) | `failed` |
| `running`, run outcome ≠ `running` (retired at terminate), or the execution closed with router `running` (R1) | `cancelled` (new) |
| `running`, an open pending attributed to its activation | `blocked` |
| `running` | `running` |
| `done`, `taken_port == "fail"`, or a terminal port of kind `failed` | `failed` |
| `done` (incl. a `rejected` terminal such as an edgeless gate `reject`) | `done` |

A gate that rejects did its job: the node is `done` and the run outcome
carries the rejection (§5.2). Every shipped stage type's `fail` port is `terminal="failed"`
(`node_types.py:64`), so an unrouted `fail` terminates the run `failed` with
reason `<node>.fail` (R3); the `fail` row precedes `done` defensively for
user graphs that route `fail` onward.

### 5.2 Run outcome (discharges E74-OQ-1)

`outcome = {state, reason, result}`:

| condition | state | reason | result |
|---|---|---|---|
| view `None`, execution open | `running` | `null` | `null` |
| view `None`, execution closed | `failed` | `not_started:<close status>` | `null` |
| `unrouted_failure` set | `failed` | `<node id>.fail: <error type>` | `null` (no return string exists) |
| router `running`, execution closed (workflow-task failure, timeout, cancel, terminate — R1) | `failed` | `interrupted:<close status>` | `null` |
| router `running`, execution open | `running` | `null` | `null` |
| router terminal / `completed`, `result` set | router outcome | `router.reason` | `result` verbatim (`completed:<sorted sink ids>`, `deployed:…`, `rejected:budget`, …) |
| router `completed`, `result` unset (retro running) | `completed` | `null` | `null` |

Execution status comes from `describe()` in the route, never inside the workflow.

### 5.3 Stage marks (E76-OQ-3)

`RunState.stage_marks: dict[str, DotState] | None` (not `stages`, V9).
Per canonical stage, over nodes whose type declares it:
`failed` > `blocked` > `active` > `done` > `pending`; `skipped` only if every
contributing node is `skipped`; `stale`/`idle` → `pending`; `cancelled` →
`failed` (a node is only ever `cancelled` under a terminal non-`completed`
outcome — the router reaches `completed` only with no live activation — or
under an interrupted execution (§5.2, R1), so the strip marks where the run
stopped, F11); nodes with
`canonical_stage is None` contribute nothing. Stages with no contributing node
are absent (E-76 §9.1 step 1 renders absent stages as `skipped`).

Closed rows: when a GraphWorkflow row first appears closed, the poller
queries `graph_view` **once** and derives its marks with
`execution_closed=True` (so an interrupted run's live nodes read `cancelled` →
`failed`, R1), then caches them per run id. Marks seen while the run was open
are never carried over — they may predate the close (N1). The query is made —
**only for rows whose visibility `workflow_type` is `GraphWorkflow`** (the
closed scan is widened to return `(id, type)`; FeatureWorkflow rows are never queried, F8).

> **Erratum (E-75 plan, Task 9).** The fleet derives closed marks from one `run_state` query (which already carries `stage_marks` computed from the same view) adjusted by `run_view.close_marks`, pinned equal to recomputing with `execution_closed=True` (`tests/graph/test_run_view_projections.py`). Same one-query-per-run bound; no fleet-side topology or history read.
The cache is pruned each tick to the ids in the current closed list, so it is
bounded by `closed_limit` (20). Each closed run costs at most one query per
process (≤20 on a cold start), against today's 20 `run_summary` replays per tick (V8), so no extra
concurrency limit is added. `FleetSnapshot` gains
`closed_marks: dict[str, dict[str, DotState]]`, holding exactly the closed
GraphWorkflow rows. A failed marks query follows `_fetch_closed`'s never-raise
pattern: an `errors` entry, no `closed_marks` key (so the row falls back to the
linear strip), and no cache entry, so the next tick retries.
`RunSummary` is not extended (retro does not run on failed executions).

## 6. Store and client start

### 6.1 `sdlc/graph/store.py`

- Root: `SDLC_GRAPH_STORE`, default `<SDLC_ARTIFACT_ROOT or SDLC_EXPORT_ROOT or ./runs>/../graphs` — outside per-run directories so run pruning never deletes a graph.
- `put(graph) -> sha`: `to_yaml(graph)`; verify `from_yaml(text).content_sha() == graph.content_sha()`; if `<sha>.yaml` exists **and verifies** (parses, sha matches), return. Otherwise write a unique temp file in the same directory and `os.replace` it onto the target; on `PermissionError`/`FileExistsError` (Windows: a concurrent writer or reader holds the target) re-read the target and succeed iff it now verifies, else raise. A corrupt or truncated existing file is therefore replaced, never trusted by existence (F6). Idempotent.
- `get(sha) -> PipelineGraph | None`; a file whose recomputed sha differs raises (corruption is loud).
- The root is resolved to an absolute path once at construction and logged; a relative default shares the anchoring of today's `SDLC_ARTIFACT_ROOT`/`SDLC_EXPORT_ROOT` (F7, accepted). No E-75 read path depends on a store hit: the routes serve from history (§6.2), so a store in another working directory degrades nothing E-75 serves.
  - **Erratum (2026-09-20, bug root-store-write):** F7's CWD-shared anchoring proved wrong in multi-seat use (E-77 T043's relative `x/` snapshot; the respawning `x/registry/<sha>.json` of the 2026-09-20 memo-cache-root session). Store roots are now fail-closed on relative inputs and checkout-anchored by default: `.specify/bugs/root-store-write/` and the root clause in `contracts/records-and-store.md` (`.specify/specs/001-canonical-stage-graph-sha/`) are authoritative.
- `start_graph_run(client, run, run_input, *, id, task_queue)` lives in the client-only `sdlc/graph/start.py` — **not** in `workflows/`, whose `graph_catalog.py` is imported inside the sandbox by `pipeline_child.py:22` (R2). It takes the already-built `GraphRunInput` and the workflow's run callable from the caller, so `sdlc/graph/` never imports `sdlc.workflows`: store put (a store failure is logged, never blocks the start), then `start_workflow`. CLI and dashboard starter call it.

### 6.2 Backfill

`GET /runs/{id}/graph` (D6) decodes the start input, `put`s it
(put-if-absent), and serves it. In-workflow children and pre-E-75 graph runs
are therefore stored on first read. No graph database; no index.

**Retention boundary (F9, accepted):** history is readable only within the
namespace retention window — the same bound every fleet query already has
(`fleet.py` module docstring). A child run never read within retention has
no stored graph. Recording the graph durably for every run, children
included, is E-77's `graph_sha` work (§1.1); E-77 inherits this as an input.

## 7. Routes and wire (`sdlc/dashboard/`)

### 7.1 `GET /runs/{id}/graph`

`describe()` → not found: `404`; `FeatureWorkflow`: `NoGraph`; `GraphWorkflow`:
first history event → `GraphRunInput` → `GraphResponse{sha, graph, back_edges}`
(`back_edges` from `topology.is_back_edge`, sorted). Cached per run id
(immutable input).

### 7.2 `GET /runs/{id}/graph_state`

`describe()` → `404` / `NoGraph` as above; `GraphWorkflow`: `graph_view`
query (closed runs: cached after the first answer, D8) → `project_graph_state`.
A closed execution projects `pending: []` whatever `_pending` still holds (F2).

### 7.3 `POST /graphs/validate` (discharges E74-OQ-4)

Body `{graph}` (same size cap as parse). `validation(graph, roles=resolved_roles(PipelineConfig()))`
plus `executable(graph)` issues with `severity: "not_executable"` and target
`node`. Legal-but-not-executable graphs therefore show without an `error`
(the canvas may save them; starting refuses them).

### 7.4 Wire amendments (PROVISIONAL → FINAL)

| model | change |
|---|---|
| `NodeRunState.status` | adds `skipped`, `cancelled` |
| `GraphState.terminal` | **replaced** by `outcome: RunOutcomeWire{state: running\|completed\|rejected\|escalated\|failed, reason: str\|None, result: str\|None}` |
| `PendingRef.node` | `str \| None` (unattributed pending); `kind` from `stage_gate`/`merge_gate` → `gate`, `clarify` → `clarify`, `task_escalation` → `escalation` |
| `EdgeRunState` | back edges only; absent = 0 |
| `GraphState.current_nodes` | distinct node ids of `state.live`, sorted |
| `Issue.severity` | adds `not_executable` |
| `GraphResponse`, `NoGraph`, `ValidationWire`, `IssueTarget` | unchanged |

E-76's rules hold: no field changes without a state change; `max_traversals`
not repeated; `pending[].key` verbatim.

**What FINAL means here (F1, F10).** The Python models are frozen as the
contract the canvas follow-up implements; the TypeScript mirror
(`graph-types.ts`), the mock's `*.provisional.json` fixtures and the poll's
`terminal !== null` finality test (`http-graph.ts:76`) stay PROVISIONAL and
are **not** exercised against these shapes by E-75. E-75 records
`graph_response.recorded.json`, `graph_state.recorded.json` (running,
completed, rejected-at-gate, escalated, unrouted-fail scenarios) and
`validation.recorded.json` from the real projection functions via
`scripts/dump_graph_fixtures.py`, pinned by the freshness test — a
Python-side export the follow-up type-checks against. The breaking
`terminal` → `outcome` change is safe to land only because every provisional
consumer is capability-gated (`http-graph.ts:63,69` stop before fetching),
and the follow-up's flip, TS amendment and fixture swap are one atomic change
(§12 E75-OQ-1). A catalog test pins all four capabilities `false` so no
partial flip lands with E-75.

## 8. Grace retention (FeatureWorkflow coexistence)

- Routes discriminate by `describe().workflow_type`; FeatureWorkflow → `no_graph/legacy_run`, never a query it lacks.
- Fleet: `stage_marks is None` for FeatureWorkflow rows → the linear strip fallback (E-76 §9.1 step 2), unchanged.
- Closed pre-cutover FeatureWorkflow runs stay `no_graph` after FeatureWorkflow's deletion (E-74 §8.1 permanent disjunction untouched).
- Host edits are no-ops for FeatureWorkflow (D4, D5).

## 9. Testing

- **Pure tables** (fast): `node_status` every row incl. retired-running, dead, stale, rejected terminal vs failed terminal; `stage_marks` precedence, all-skipped, cancelled by outcome, `None` canonical stage; `node_status` escalating emitter → `failed` vs bystander → `cancelled` (F4); `project_graph_state` outcome table incl. view-`None` open/closed, `unrouted_failure` (router `failed` via the terminal `fail` port; wire reason adds the error type; execution closed failed — F5, N4), budget `Halt` with a live gate (strip `failed`, F11), `completed:<sinks>`, retro window (`completed`, `result` null, F3); closed execution with router `running` → `failed`/`interrupted:*` and live nodes `cancelled` (R1); closed execution lists no pendings (F2).
- **Purity pins:** `run_view.py`, `store.py`, `start.py` entries; `workflows/` never imports `sdlc.graph.store`; `ACTIVATION.set` appears only in `graph_dispatch.py`'s task body (grep test).
- **Temporal tier:** sandboxed `graph_view` query on a live run (catches the pydantic duplication fingerprint); two concurrent activations attribute cost and pendings to the right activation; clarify and handler-internal gate attribution; unrouted fail → `unrouted_failure`; `result` unset during retro and set after (F3); cost invariant Σ node cost + unattributed == `cost_usd_total` (F12); SG-3 goldens and `test_feature_replay.py` pass **unchanged**.
- **Store:** put-if-absent on a verifying file; a truncated/corrupt existing file is replaced; `PermissionError` on replace succeeds iff the target then verifies (F6); `get` corruption raises; absolute root; start not blocked by a store failure.
- **Routes** (stub client): history decode for GraphWorkflow, `no_graph` for FeatureWorkflow, `404`, closed-run cache hit, validate severities.
- **Fleet:** one `graph_view` query per first-closed GraphWorkflow row, never carried open marks; an interrupted run's marks re-derived `failed`, never `active` (N1); FeatureWorkflow rows never queried, cache pruned to the current closed list (F8).
- **Catalog:** all four capabilities remain `false` (F1).
- **Fixtures:** recorded JSON freshness.

## 10. FR-1204 traceability

| clause | discharged by |
|---|---|
| expose the graph a run executes | `GET /runs/{id}/graph` from the pinned start input (§7.1) |
| per-node status | `node_status` (§5.1) |
| per-node cost | context-variable attribution (§4.3), honest `null` |
| per-node duration | `started_at`/`ended_at` (§4.2) |
| traversal counters | `EdgeRunState` from `RouterState.traversals` |
| beside the existing run queries | `/runs/{id}/…` routes; `RunState.stage_marks` |
| content-addressed `graphs/<sha>.yaml` | `sdlc/graph/store.py` (§6) |
| no graph database | files only; no index |

## 11. Out of scope

Capability flips, `graph-types.ts`/fixture amendments and RunView/fleet
frontend changes (canvas follow-up, E75-OQ-1); `graph_sha` recording and
`canonical_stage` completeness (E-77); save/load routes (E-77); per-attempt
activation history (Q3 non-goal); crew-child escalation attribution
(E75-OQ-2); closed-run `run_summary` per-tick replay (E75-OQ-3); pricing harness/crew spend (E75-OQ-4); durable graph for children read after retention (E-77, F9); auth (OQ-11).

**Docs on landing:** tick E-75 in `docs/roadmap/pipeline-as-data.md` and ROADMAP
FR-1204; ARCHITECTURE component list gains the run view, store and routes;
`workflows/AGENTS.md` ownership rows; E-76 spec §5.7 pointer to this spec's §7.4.

## 12. Open questions — resolved at the user gate (2026-09-17)

- **E75-OQ-1 — scope fork (brief constraint 4). Resolved: option (a).** E-75 is
  backend-only as specified. A named follow-up epic (canvas run-mode wiring,
  E-76 family) flips `run_graph`/`validate`, amends `graph-types.ts` and the
  provisional fixtures atomically, and maps `stage_marks` in `http.ts` for the
  fleet strip. Until it lands, E76-OQ-3's `skipped` rendering is served but not
  shown. Rejected: (b) E-75 also doing that frontend work.
  **Landed (2026-09-20):** bug flow `canvas-run-mode` (branch
  `fix/canvas-run-mode`) implemented option (a) as ruled — the flip, the TS
  mirror catch-up (§7.4 plus E-77's `canonical_stage`/`unavailable`), the
  provisional-fixture swap and the fleet-strip mapping; E76-OQ-3's
  served-but-not-shown gap is closed.
- **E75-OQ-2 — crew-child escalations. Accepted deferral.** A code node whose
  task escalation is pending inside a crew child shows `running`, not
  `blocked`; querying the child per poll is a follow-up.
- **E75-OQ-3 — closed-run `run_summary` replay each fleet tick. Accepted
  deferral.** The same immutable cache would remove it; a follow-up.
- **E75-OQ-4 — harness and crew spend are unpriced. Accepted deferral.** Only
  `RoleHost._run_role` records usage (`role_host.py:153`); coding-harness
  activities and crew children never reach `cost_usd_total`, so node cost (like
  the run's) is model-role spend only. Pricing harness spend is a separate
  observability item.
- **R-Q2 (ruling refinement). Confirmed by the user:** the store is written at
  the client start helper (`sdlc/graph/start.py`) with history backfill, not
  at `build_run_input` (§2.1, V1).

## 13. Skeptic dispositions (`.workspace/tmp/e75-skeptic-full.md`)

| finding | disposition |
|---|---|
| F1 `terminal`→`outcome` halts the TS poll (`undefined !== null`) | **Rejected as a live defect, clarified.** The poll never fetches while `run_graph` is `false` (`http-graph.ts:69` returns `stop`), and E-75 pins all capabilities `false`. Keeping a duplicate `terminal` would freeze a field that cannot express `rejected`. §7.4 now states the atomic flip+TS obligation. |
| F2 clarify pending leaks on timeout/cancel | **Resolved by construction.** `PendingFact`s iterate `_pending` and join the attribution map, never the reverse; closed executions project no pendings; `blocked` is unreachable under a terminal outcome (§4.3, §7.2). The pre-existing `_pending` non-pop on timeout (which fails the execution) is unchanged. |
| F3 `result` set before retro | **Adopted.** Assigned after `_retro` returns (§4.2); retro window is `completed` with `result` null (§5.2). |
| F4 escalating emitter shows `cancelled` | **Adopted.** Dispatcher records `escalated_by`; status row → `failed` (§4.1, §5.1). No reason-string parsing. |
| F5 unrouted failure has no detail | **Adopted, narrowed** (premise corrected by reviewer R3: with shipped types the router ends `failed`, not `completed`). `unrouted_failure{activation_id, error_type}`; the message is not exposed (D3 spirit) — it remains on the execution's close failure. |
| F6 Windows rename / corrupt put-if-absent | **Adopted.** Verify-then-trust, `os.replace`, re-verify on `PermissionError`/`FileExistsError` (§6.1). |
| F7 relative store root across worktrees | **Accepted tradeoff.** Same anchoring as the existing artifact/export roots; root resolved absolute and logged; no E-75 read path depends on a store hit (§6.1). |
| F8 closed-marks leak, storm, FeatureWorkflow query | **Adopted:** type-filtered queries, cache pruned to the current closed list. **Rejected:** a concurrency limit — 20 one-time queries vs today's 20 replays per tick (§5.3). |
| F9 graph lost after retention | **Accepted tradeoff, documented** (§6.2); durable per-run recording is E-77's input. |
| F10 recorded fixtures prove nothing to TS | **Adopted as wording (option b):** FINAL = the Python contract; TS remains provisional until the follow-up (§7.4). |
| F11 budget halt shows gate `pending` on the strip | **Adopted, simplified:** `cancelled` → `failed` always, since it only occurs under a terminal non-`completed` outcome (§5.3). |
| F12 code node partial spend | **Adopted differently.** Not nulled: node cost is defined with the run total's scope, pinned by the Σ invariant; harness/crew pricing is E75-OQ-4 (§4.3). |

### 13.1 Reviewer round 1 (`.workspace/tmp/e75-reviewer-r1.md`, CHANGES REQUESTED)

| finding | disposition |
|---|---|
| R1 closed execution with router `running` projects `running` forever | **Adopted:** `interrupted:<close status>` row (§5.2); live nodes → `cancelled` (§5.1), strip `failed` (§5.3). |
| R2 `start_graph_run` beside `build_run_input` breaks the store-import pin | **Adopted:** helper in `sdlc/graph/start.py`, outside `workflows/` (§6.1, D1). |
| R3 unrouted `fail` is a terminal, not a sink | **Adopted:** §5.1 note corrected; F5 premise annotated. |
| R4 ambiguous D8 citation | **Adopted:** "E-74 D8". |
| R5 closed scan `(id, type)` read as current | **Adopted:** "widened to return". |

### 13.2 Reviewer round 2 (`.workspace/tmp/e75-reviewer-r2.md`, CHANGES REQUESTED)

| finding | disposition |
|---|---|
| N1 carried open marks freeze an interrupted run as `active` | **Adopted (simpler option):** carry dropped; one `graph_view` query per first-closed GraphWorkflow row with `execution_closed=True` (§5.3, §9). |
| N2 projection signatures lack execution status | **Adopted:** `execution_closed` keyword, dashboard-only (§4.1). |
| N3 `start.py` pin entry and signature | **Adopted** (D1, §6.1, §9). |
| N4 stale F5 premise in §9 | **Adopted.** |
