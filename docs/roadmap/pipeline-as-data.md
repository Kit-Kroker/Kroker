# Pipeline as data — graph interpreter + canvas (`E-72`…`E-77`) → FR-1200

**The framing.** The 15-stage DAG is not data — it is imperative Python.
`FeatureWorkflow._pipeline` (`src/sdlc/workflows/feature.py:469`) hardcodes stage order,
the typed handoffs between stages, the fix loops, the gate awaits and the signal
handling. Every pipeline shape the factory can run is a shape someone wrote by
hand. FR-1200 makes the pipeline a user-authored `PipelineGraph` executed by a
generic interpreter, with a canvas to edit it — n8n's model, applied to the SDLC
DAG.

**Admitted 2026-09-12 (PRD v1.2).** FR-1200…FR-1206 have PRD §6 lines (the
family block there is the normative text), and ROADMAP §2 carries the mirror
block. Before that the group was **record only** — ruled 2026-09-11 (user
gate, `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md`
§10) pending exactly those PRD lines. Sequencing now waits only on **OQ-10**
(in-flight runs at cutover), which blocks E-74's landing, not its design;
P2's exit — the third prerequisite — was demonstrated 2026-09-12
(`ordering.md` item 7). **OQ-10 resolved 2026-09-12: grace-retention** —
see PRD §11; all three prerequisites are cleared and the group is free to
sequence.

**Decided 2026-08-06** (brainstorm, no spec written): ports carry control flow
(n8n-style branching, not a strict DAG of composite nodes), and the interpreter
**replaces** `_pipeline` big-bang rather than running beside it. Three objections
were raised and answered rather than dismissed:

- (a) **Temporal determinism.** The graph is workflow *input*, pinned for the
  run's lifetime. A canvas edit never mutates a running workflow — it writes a
  new `content_sha` that the next run picks up. No per-edit `workflow.patched()`.
- (b) **Typed contracts.** Ports declare payload types by existing model name
  (`ArchitectureSpec`, `ImplementationPlan`, `TaskResult`…); edge validation
  rejects incompatible connections. Freedom is real but type-bounded.
- (c) **The benchmark axis.** Node types declare a `canonical_stage`, mapping any
  graph onto the fixed `CANONICAL_STAGES` list (`src/sdlc/benchmarks/heatmap.py:25`), so
  the heatmap and SC rollups survive arbitrary graphs. Unmapped types record as
  `unknown`, which `heatmap.py:122` already handles.

**Cheaper than it looks.** The node handlers already exist, and since the B0
stage migration most are module-level functions rather than `FeatureWorkflow`
methods: `src/sdlc/stages/<stage>/step.py` for all 13 stages (clarify as
`_run_clarify_single`/`_run_clarify_fanout`, `_run_architect` inside
`stages/architecture/step.py`, `_fan_out_research` in `stages/research/step.py`,
`_run_deep_review`/`_run_adversary`/`_run_handoff` in `stages/code/step.py`),
with `_dev_task`/`_merge_task` in `workflows/task_host.py`, `_gate` in
`workflows/gates.py`, and `_retro` still in `workflows/feature.py`. The work is
replacing the *wiring*, not the stage bodies, and B0 already moved the bodies
closer to E-74's `(Activation, PipelineConfig) -> Emission` shape.
`_revisable_stage` (`workflows/role_host.py`) disappears entirely: wrapping a
stage in a gate-and-retry loop becomes topology. *Anchors refreshed 2026-09-11;
the earlier line numbers pointed into a 2,329-line `feature.py`.*

**The quiet win.** Three boolean flags on `PipelineConfig` (`research_enabled`,
`deep_review_enabled`, `adversarial_review_enabled`), the handoff stage's
`t_handoff is not None` guard, and their scattered `if cfg.X_enabled and t_X is
not None` checks collapse into *is there a node*.

- [x] **E-72 — `PipelineGraph` model + node-type registry** → FR-1201.
  `GraphNode` / `GraphEdge` / `NodePort` in `sdlc/graph/model.py`; nodes carry
  `RoleConfig` (`src/sdlc/core/models.py:176`) and `GateConfig` (`:57`) **verbatim**
  rather than a forked `params["model"]` string, so the registry loader's
  validation, the ADR-6 model-inequality checks and `PROMPT_SHAS` memo
  invalidation keep working unchanged. `content_sha()` excludes `position` and
  `label` so tidying the canvas never invalidates a memo. Registry declares each
  node type's ports, payload types and `canonical_stage`.

  **Landed** (spec `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md`,
  plan `docs/superpowers/plans/2026-09-13-graph-model-node-registry.md`): `sdlc/graph/`
  ships the frozen schema, `content_sha()`, YAML io and a seed registry for the typed
  pre-code half (no `gate.clarify`). Rejecting incompatible edges is E-73's
  `validate.py`; the post-plan catalog and `code` decomposition are E-74's
  (E72-OQ-3). Open questions E72-OQ-1…8 live in the spec §10.
- [x] **E-73 — `GraphRouter` + `validate.py`** → FR-1202. **The bug budget lives
  here.** A pure, synchronous routing state machine — no Temporal, no I/O — so
  the hard part is table-testable in milliseconds. Owns: one-output-port-per-
  activation branching; **round-based stale-input invalidation** (a backward edge
  increments `round` and invalidates buffered inputs at lower rounds, or a revise
  loop re-runs `architect` while `planner` still holds last round's spec);
  per-edge `max_traversals` with exhaustion terminating `ESCALATED` (reproducing
  the per-task `max_fix_attempts` budget, `src/sdlc/stages/code/step.py:534`);
  fan-out/collect. Rounds are not new — `gate_key(gate, round)`
  (`src/sdlc/core/models.py:228`) already carries this semantics for gates; the router
  generalises it to the whole graph. `validate.py` is the **single** source of
  truth for legality (port compatibility, reachability, every cycle bounded,
  one entry node) and is never reimplemented in TypeScript.

  **Landed** (spec `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md`,
  plan `docs/superpowers/plans/2026-09-14-graph-router-and-validator.md`): `sdlc/graph/`
  gains `topology.py`, `validate.py` (25 `ProblemCode`s; the only producer of `Topology`)
  and `router.py` (a pure reducer). A loop edge is exactly an edge carrying
  `max_traversals`; the literal "invalidate inputs at lower rounds" is superseded by
  REGION invalidation, because it would starve `architect` of upstream inputs. Exhaustion
  is ESCALATED at the router, and each activation's `unavailable_ports` snapshot lets a
  gate run as today's final gate (E-74 handler rule). Open questions E73-OQ-1…8 live in
  the spec §10; E73-OQ-3 (never-reset counters) is a documented limitation.
- [x] **E-74 — `GraphWorkflow` replaces `_pipeline`** → FR-1203. Thin Temporal
  layer over E-73: dispatch table from `node.type` to the existing handlers,
  which converge on `(Activation, PipelineConfig) -> Emission`; exceptions become
  `fail` emissions so error routing is topology. `PipelineConfig` splits by scope
  — run-scoped settings stay, per-stage settings move onto nodes,
  `max_fix_attempts` becomes `GraphEdge.max_traversals`. Determinism rules
  (sorted iteration, no bare `set`/`dict` walks, fixed-order `gather`) enforced
  by a lint test, since the router is new code where they break silently.
  `default.graph.yaml` expresses today's pipeline and is asserted to reproduce
  its stage sequence. **Big-bang was chosen over strangler-with-parity** — run
  the benchmark before/after anyway as a regression check; the choice was to not
  *gate* on dual-running, not to discard free evidence.

  **Landed** (spec `docs/superpowers/specs/2026-09-15-graph-workflow-cutover-design.md`,
  plan `docs/superpowers/plans/2026-09-15-graph-workflow-cutover.md`): every new run —
  `sdlc start`, dashboard/operator, benchmark cells, tidy-up fix runs — starts
  `GraphWorkflow` over a pinned, validated graph (`workflows/graphs/default`,
  `default-research`, `seeded`), and GraphWorkflow reproduces FeatureWorkflow's
  golden traces exactly (stage/gate trace, command projection, close). `code` is one
  coarse node; **follow-ups:** per-task topology with `max_fix_attempts → max_traversals`
  (E74-OQ-3), research-as-topology (E74-OQ-2), and the FeatureWorkflow deletion gated
  on the two Running queries of spec §8.5. Rollback is roll-forward only.
- [x] **E-75 — graph queries on the dashboard backend** → FR-1204. `GraphWorkflow` exposes a `graph_view` query (router state + per-activation timing, attributed cost and pendings, recorded in memory with no new commands); the dashboard serves `GET /runs/{id}/graph` (the pinned start input, read from history), `GET /runs/{id}/graph_state` and `POST /graphs/validate` (`executable()` problems as `not_executable`), and `RunState.stage_marks` renders `skipped` stages for graph runs. Graphs are stored content-addressed as `graphs/<sha>.yaml` (`sdlc/graph/store.py`), written at client start and backfilled on first read; no graph database.

  **Landed** (spec `docs/superpowers/specs/2026-09-17-graph-queries-design.md`, plan `docs/superpowers/plans/2026-09-17-graph-queries.md`). Backend-only: catalog capabilities stay `false`. **Follow-ups:** canvas run-mode wiring (flip `run_graph`/`validate`, amend `graph-types.ts` and fixtures, map `stage_marks` in `http.ts`); crew-child escalation attribution (E75-OQ-2); closed-run `run_summary` replay per fleet tick (E75-OQ-3); pricing harness/crew spend (E75-OQ-4). Durable `graph_sha` per run stays E-77.
- [x] **E-76 — canvas** → FR-1205. `@vue-flow/core` (React Flow's Vue port, what
  n8n itself uses; fits the existing Vue 3 + Pinia + Vite stack) plus `dagre` for
  auto-layout of YAML-authored graphs. **One renderer, two modes**: `runState`
  present ⇒ status rings, cost, durations, traversal counters on loop edges, live
  gate approve/reject; `editable` ⇒ palette + inspector. Editing a *running*
  graph is disabled by design (see (a) above). Backward edges render curved with
  a `2/3` counter, so a post-mortem shows **why** a run looped, not merely that it
  did. `Run.stageIdx` was a linear index that could not express
  graph position; it became `Run.activeStages: string[]` (canonical stage
  names), while `current_nodes` lives in the run's graph state. `StageDots.vue`
  (`interfaces/ui/src/components/stage_dots/`, E-89) renders the canonical
  stage list the catalog serves (18 stages), matched by name, so the fleet
  table keeps its glanceable row and cannot disagree with the benchmark.

  **Landed** (spec `docs/superpowers/specs/2026-09-14-graph-canvas-design.md`,
  plan `docs/superpowers/plans/2026-09-14-graph-canvas.md`): six `@kroker/ui`
  components, edit mode at `/graphs`, run mode in RunView, the pure
  `/graphs/catalog|parse|serialize` routes over `sdlc/dashboard/graph_wire.py`,
  and the strict graph YAML loader. Run mode is exercised on the mock provider;
  live run data arrives with E-75, validation with E-73, save/load with E-77
  (all gated by server-declared capabilities). Open questions E76-OQ-1…5 live
  in the spec §12.
- [x] **E-77 — graph store + custom-graph benchmark mapping** → FR-1206. Runs
  record their `graph_sha`, so a post-mortem always renders the graph that
  *actually ran* rather than what the graph looks like now. Benchmark records
  derive `fix_attempts` from inbound-fail-edge traversal counts and `round` from
  the router, keeping the §9 measurement axes intact across hand-authored graphs.

  **Landed** (spec `.specify/specs/001-canonical-stage-graph-sha/spec.md`):
  every graph run records its `graph_sha` — run summary, live state, benchmark
  records (benchmark-arm and oracle records included) and a per-run pointer
  written at client start naming the run's layout, registry snapshot and roles,
  so a post-mortem survives history retention and registry drift (a drifted
  graph degrades to `unknown` nodes, never a server error). Unmapped or
  unregistered node types contribute `unknown` stage marks and record stages —
  never silently dropped. The store keeps immutable layouts (one file per layout
  identity) under an editor-only `latest`; `POST /graphs` / `GET /graphs/{sha}`
  serve with `save`/`load` capabilities `true` (`run_graph` stays as on main).
  **Follow-ups:** canvas run mode / fleet-strip consumption of
  `canonical_stage` and `unknown` marks + the TS mirror (E-76 family,
  E75-OQ-1); the fail-edge fix axis derives from topology but records absent —
  never zero — on every graph buildable today, waiting on graph-expressed fix
  loops (E74-OQ-3); the heatmap's pre-existing `attempt − 1` inflation (a task
  needing n attempts reports n(n−1)/2 fix attempts rather than n−1, E77-OQ-1)
  is recorded as a follow-up for the benchmark owner.

**External input (2026-09-11).** A third-party platform analysis (register §H,
verbatim at `docs/reports/2026-09-11-external-platform-analysis.md`)
independently proposed this group's substance and ranked it first:
- its FlowSpec is E-72…E-74 (H2), and its visual builder is E-76 (H1);
- its graph-shaped run replay is E-75 + E-76's run-state mode (H5);
- the validator half of its dry-run is E-73's `validate.py` (H6);
- its workflow-as-experiment axis needs E-77's `graph_sha` (H3).

This adds priority pressure, not scope. Its untyped YAML is not adopted over
E-72's typed ports (objection (b)). The one idea it adds that this group has not
designed, subflows, is OQ-14.

**Open questions.**

- **OQ-10 — in-flight runs at cutover. Resolved (2026-09-12): grace-retention.**
  The cutover lands without draining: new starts move to `GraphWorkflow` in
  the same change, `FeatureWorkflow` stays registered — unchanged,
  replay-safe — solely to carry in-flight executions to their own terminal
  states, and its deletion is a follow-up commit gated on the
  Running-executions query being empty (collapsing into one commit when
  nothing is in flight). Rejected: drain-first (couples the deploy to foreign
  runs) and hard-cut-and-restart (restart under the same workflow id breaks
  on stale `sdlc/*` branches today — known open defect). This is not
  strangler-with-parity: no new run ever executes the old path.
- **OQ-11 — dashboard auth.** ⚠️ **Now live, not hypothetical (2026-08-07).**
  E-78's board API is already serving unauthenticated, and its two agent write
  routes trust a self-asserted `X-Actor` header — so the audit log's "who moved
  what" is spoofable by anything that can reach the port. Localhost-bind is the
  current containment. Was framed as: E-75 is the first server in the project, and
  *"start a run"* and *"approve a merge gate"* are not endpoints to leave
  unauthenticated once anything but localhost can reach them. Localhost-bind with
  no auth is the assumed near-term answer; **E-60** (identity & authorization,
  FR-1004) is where it stops being acceptable.
  **2026-08-18 (E-10):** a *second* unauthenticated surface now serves, and this
  one can start runs and approve merge gates. Operator identity is the
  self-asserted `X-Actor` header landing on `GateDecision.reviewer` — never on
  `decided_by`, which stays `Literal["human","policy","timeout"]` so
  `ReadinessOverride.approved_by` keeps distinguishing a machine approval from a
  human one. Localhost-bind remains the whole containment.
- **OQ-P5..P8 — prompt-gate sensitivity (E-83).** Tracked in the eval spec's §9
  (`docs/superpowers/specs/2026-08-12-judge-sensitivity-and-plan-adherence-design.md`),
  not duplicated here. **OQ-P5 answered:** the gate has teeth — `scope_dropped`
  fails absolutely via the `scope_preserved` veto (proven end-to-end through
  real promptfoo). An earlier draft mis-recorded it as PASS due to a
  veto-engine substring false negative (since fixed to word-boundary matching);
  see spec §9's correction. New: OQ-P6 (veto authorship is manual/unenforced),
  OQ-P7 (`PlanDrift` has no baseline yet), OQ-P8 (phase-1 step caching vs judge
  nondeterminism).
- **OQ-12 — S5 normalization is English-centric.** Layer-suffix stripping and
  singularization assume English identifiers, so a non-English codebase degrades
  to LOW-confidence single-source candidates. Recorded rather than solved:
  calibrating it needs the corpus SC-8 also needs.
- **OQ-14 — subflows (register H7).** A subgraph node type (one node running
  another graph as a child workflow) is expressible on E-72: the 2026-08-06
  decision rejected composite nodes as the *branching* primitive, not a subgraph
  node. Child-workflow precedent exists in `CrewTaskWorkflow` (E-88),
  `DeploymentWorkflow` (E-67) and the `TriageWorkflow` child (E-44/E-45).
  Unresolved: E-73 round/stale-input semantics across the boundary,
  `canonical_stage` for inner nodes (E-77), and a composite's `graph_sha`. Not
  before E-74.
