# Pipeline as data — graph interpreter + canvas (`E-72`…`E-77`) → FR-1200

**The framing.** The 15-stage DAG is not data — it is imperative Python.
`feature.py::_pipeline` (line 1625, in a 2,329-line file) hardcodes stage order,
the typed handoffs between stages, the fix loops, the gate awaits and the signal
handling. Every pipeline shape the factory can run is a shape someone wrote by
hand. FR-1200 makes the pipeline a user-authored `PipelineGraph` executed by a
generic interpreter, with a canvas to edit it — n8n's model, applied to the SDLC
DAG.

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
  graph onto the fixed `CANONICAL_STAGES` list (`benchmarks/heatmap.py:24`), so
  the heatmap and SC rollups survive arbitrary graphs. Unmapped types record as
  `unknown`, which `heatmap.py:96` already handles.

**Cheaper than it looks.** The node handlers already exist as methods —
`_run_clarify` (:1836), `_run_architect` (:1900), `_fan_out_research` (:803),
`_dev_task` (:1218), `_gate` (:1105), `_run_deep_review` (:876), `_run_adversary`
(:942), `_run_handoff` (:994), `_merge_task` (:1193), `_retro` (:1559). The work
is replacing the *wiring*, not the stage bodies. `_revisable_stage` (:1166)
disappears entirely: wrapping a stage in a gate-and-retry loop becomes topology.

**The quiet win.** Four boolean flags (`research_enabled`, `deep_review_enabled`,
`adversarial_review_enabled`, `handoff_enabled`) and their scattered
`if cfg.X_enabled and t_X is not None` guards collapse into *is there a node*.

- [ ] **E-72 — `PipelineGraph` model + node-type registry** → FR-1201.
  `GraphNode` / `GraphEdge` / `NodePort` in `sdlc/graph/model.py`; nodes carry
  `RoleConfig` (`models.py:717`) and `GateConfig` (`models.py:53`) **verbatim**
  rather than a forked `params["model"]` string, so the registry loader's
  validation, the ADR-6 model-inequality checks and `PROMPT_SHAS` memo
  invalidation keep working unchanged. `content_sha()` excludes `position` and
  `label` so tidying the canvas never invalidates a memo. Registry declares each
  node type's ports, payload types and `canonical_stage`.
- [ ] **E-73 — `GraphRouter` + `validate.py`** → FR-1202. **The bug budget lives
  here.** A pure, synchronous routing state machine — no Temporal, no I/O — so
  the hard part is table-testable in milliseconds. Owns: one-output-port-per-
  activation branching; **round-based stale-input invalidation** (a backward edge
  increments `round` and invalidates buffered inputs at lower rounds, or a revise
  loop re-runs `architect` while `planner` still holds last round's spec);
  per-edge `max_traversals` with exhaustion terminating `ESCALATED` (reproducing
  `feature.py:1464`); fan-out/collect. Rounds are not new — `gate_key(gate,
  round)` (`models.py`) already carries this semantics for gates; the router
  generalises it to the whole graph. `validate.py` is the **single** source of
  truth for legality (port compatibility, reachability, every cycle bounded,
  one entry node) and is never reimplemented in TypeScript.
- [ ] **E-74 — `GraphWorkflow` replaces `_pipeline`** → FR-1203. Thin Temporal
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
- [ ] **E-75 — graph queries on the dashboard backend** → FR-1204. **Superseded in part 2026-08-18:** E-10 built the backend, so this narrows to adding `graph_state()` and `graph()` beside the existing queries once `GraphWorkflow` exists. The "dashboard backend remains" half of P2 is closed; what is left here is graph-shaped run state, which needs E-74 first. The only storage is still content-addressed `graphs/<sha>.yaml`.
- [ ] **E-76 — canvas** → FR-1205. `@vue-flow/core` (React Flow's Vue port, what
  n8n itself uses; fits the existing Vue 3 + Pinia + Vite stack) plus `dagre` for
  auto-layout of YAML-authored graphs. **One renderer, two modes**: `runState`
  present ⇒ status rings, cost, durations, traversal counters on loop edges, live
  gate approve/reject; `editable` ⇒ palette + inspector. Editing a *running*
  graph is disabled by design (see (a) above). Backward edges render curved with
  a `2/3` counter, so a post-mortem shows **why** a run looped, not merely that it
  did. `Run.stageIdx` (`api/types.ts:20`) is a linear index that cannot express
  graph position and becomes `currentNodes: string[]`; `StageDots.vue` survives by
  mapping active nodes through `canonical_stage` back onto the fixed 15-stage
  strip, so the fleet table keeps its glanceable row and cannot disagree with the
  benchmark.
- [ ] **E-77 — graph store + custom-graph benchmark mapping** → FR-1206. Runs
  record their `graph_sha`, so a post-mortem always renders the graph that
  *actually ran* rather than what the graph looks like now. Benchmark records
  derive `fix_attempts` from inbound-fail-edge traversal counts and `round` from
  the router, keeping the §9 measurement axes intact across hand-authored graphs.

**Open questions.**

- **OQ-10 — in-flight runs at cutover.** Big-bang means `FeatureWorkflow`
  disappears. Drain first (block new runs, wait out current ones) or accept that
  in-flight runs fail and are restarted? Unresolved; blocks E-74's landing, not
  its design.
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
