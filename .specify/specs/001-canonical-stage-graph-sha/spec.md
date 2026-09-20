# Feature Specification: E-77 — graph store + custom-graph benchmark mapping

**Feature Branch**: `001-canonical-stage-graph-sha` (spec directory; branch is the orchestrator's call)

**Created**: 2026-09-19

**Status**: Final (planner; FR-026 consequence amended at task generation 2026-09-19) — GATE 1 cleared 2026-09-19 (user): baseline approved, full family scope; amended, advisor-consulted and skeptic-pressure-tested 2026-09-19 (dispositions at the end).

**Input**: E-77 — FR-1206: `canonical_stage` on every node type + `graph_sha` per run; unmapped node types record literal `unknown`. Orchestrator TASK BRIEF (rulings R1–R5) plus the GATE 1 rulings G1–G4 below.

**Normative text** (PRD §6, FR-1206, verbatim terms): *Every node type SHALL declare a `canonical_stage` mapping it onto the fixed `CANONICAL_STAGES` list, so the benchmark's measurement axes (fix attempts from fail-edge traversals, rounds from the router, per-stage economics) survive hand-authored graphs. Every run SHALL record its `graph_sha`, so a post-mortem always renders the graph that actually ran. A type with no mapping records as `unknown` — never silently as a canonical stage.*

**Family row** (`docs/roadmap/pipeline-as-data.md`, E-77 "graph store + custom-graph benchmark mapping"): runs record their `graph_sha`; benchmark records derive `fix_attempts` from inbound-fail-edge traversal counts and `round` from the router. Sibling specs assign to E-77: save/load routes + capabilities (E-75 §1.1), E72-OQ-7 and E72-OQ-8 (E-72 §10).

## Binding rulings

Orchestrator brief (not re-opened):

- **R1 Placement.** The type → stage mapping lives in the pure graph layer (no Temporal imports). `graph_sha` is stamped at the existing E-75 start chokepoint; queries and the fleet *read* it — hashing and legality are never reimplemented.
- **R2** Unmapped node types record the literal `unknown` — a recorded value, not a validation error.
- **R3 Backend-only.** Routes and records are backend. Canvas wiring and fleet-strip consumption of `canonical_stage` remain the named follow-up — except that flipping the `save`/`load` capabilities is in scope (G3).
- **R4 Grace retention.** In-flight FeatureWorkflow runs (no graph) render exactly as today, with no errors.
- **R5 Docs describe main.** ARCHITECTURE/ROADMAP change only for landed state.

User GATE 1 (2026-09-19):

- **G1 (was OQ-2) Carrier = B.** Optional `graph_sha` on the run summary, live run state and benchmark records, **plus** a per-run pointer written at the client start chokepoint.
- **G2 (was OQ-3) Record attribution = B.** Records produced inside an activation of a type resolving to `unknown` are stamped `unknown`; mapped types keep their handler's stage; lens records keep lens stages.
- **G3 (was OQ-1) Full family scope.** (a) `fix_attempts` from inbound fail-edge traversals + `round` from the router; (b) `POST /graphs`, `GET /graphs/{sha}`, capabilities `save`/`load` flipped; (c) E72-OQ-7 resolved by design; (d) E72-OQ-8 fully disposed.
- **G4 Honest axes.** Where the router cannot yet produce an axis, derive what exists, record honest zeros / absent values, and name the dependency as an accepted tradeoff — never fabricate an axis.

## User Scenarios & Testing *(mandatory)*

Actors: the **operator** reading a post-mortem (dashboard / CLI); the **benchmark analyst** reading heatmaps and SC rollups; the **graph author** saving and loading graphs from the editor (API today, canvas later).

### User Story 1 — A post-mortem always names the graph that ran (Priority: P1)

An operator opens a finished, failed or still-running graph run and sees the exact graph identity (`graph_sha`) the run executed, read from the run's own record — not re-derived from today's graph file, and not dependent on orchestration history still being retained.

**Why this priority**: Nothing on main satisfies it. The sha exists only in workflow memory and in the start input in history (E-75 interim, lost at namespace retention — E-75 F9).

**Independent Test**: Start a graph run with a non-default graph; confirm the per-run pointer, live state, run summary and benchmark records all carry the same `graph_sha`, equal to the pinned graph's content hash and to a stored graph's name.

**Acceptance Scenarios**:

1. **Given** a graph run that completes, **When** its run summary is read (query or exported summary file), **Then** it carries `graph_sha` equal to the pinned graph's content hash.
2. **Given** a graph run in flight, **When** the fleet reads its live state, **Then** the live state carries the same `graph_sha`.
3. **Given** two runs of graphs differing only in canvas cosmetics, **When** both are recorded, **Then** they carry the same `graph_sha`.
4. **Given** a client-started graph run that fails before retro (retro is skipped on failed executions, E-74 U9), **When** a post-mortem is requested after history retention has expired, **Then** `graph_sha` is recovered from the per-run pointer.
5. **Given** a benchmark arm (a child run started inside a workflow, which cannot write files), **When** its records are aggregated, **Then** every record of that arm carries the arm's `graph_sha`.

---

### User Story 2 — Every node lands on a canonical stage, or visibly on `unknown` (Priority: P1)

A benchmark analyst aggregates runs of hand-authored graphs. Every node's activity is attributed to its type's `canonical_stage`; a node whose type has no mapping (declared none, or not in the registry at all) is attributed to the literal `unknown` — never folded into a real stage, never dropped.

**Why this priority**: The measurement-axis core of FR-1206. On main, an unmapped or unregistered type contributes nothing to stage marks — the silent drop FR-1206 forbids.

**Independent Test**: With an injected registry containing an unmapped type, run the stage projection and record attribution over a graph containing it; confirm `unknown` appears and no canonical stage absorbed it. Repeat with a node whose type is missing from the registry.

**Acceptance Scenarios**:

1. **Given** the shipped registry, **When** the registry self-check runs, **Then** every shipped type declares a `canonical_stage` from `CANONICAL_STAGES`.
2. **Given** a node type with no mapping, **When** stage marks are projected, **Then** that node contributes to a mark keyed `unknown`.
3. **Given** a node type with no mapping, **When** its activation produces benchmark records, **Then** those records carry stage `unknown` (G2).
4. **Given** a mapped node type whose handler emits lens records (`code` → review/adversary/handoff/deep_review), **When** records are produced, **Then** each keeps its handler/lens stage (G2).
5. **Given** a stored graph whose node type is no longer registered, **When** a post-mortem projects its stages, **Then** the node attributes to `unknown` and nothing errors.
6. **Given** a declared `canonical_stage` outside `CANONICAL_STAGES`, **When** the self-check runs, **Then** it reports a problem (existing rule — a *wrong* mapping is an authoring error; an *absent* one records `unknown`).
7. **Given** records with stage `unknown`, **When** the heatmap is built, **Then** `unknown` renders in the trailing non-canonical bucket (existing behaviour).

---

### User Story 3 — Router-derived rounds and fix attempts survive hand-authored graphs (Priority: P2)

A benchmark analyst compares runs of different graphs on the same case and sees, per record, the router round of the activation that produced it, and — where the graph expresses a fix loop as topology — fix attempts derived from inbound fail-edge traversals, alongside the handler-counted fix attempts that exist today.

**Why this priority**: The rest of FR-1206's measurement axes. P2 because one of the two axes is structurally empty on main (see G4 tradeoff below), so its value is future-proofing plus honest reporting.

**Independent Test**: (i) Run the default graph with a revise loop taken; confirm the producer's records carry round 1 then round 2. (ii) With an injected registry whose type accepts a failure payload, route a `fail` port back into a node over a bounded loop edge; confirm the re-entered activation's records carry the derived fail-edge fix count. (iii) On the default graph, confirm the derived fail-edge axis is *absent* (not zero) and handler-counted `fix_attempts` are unchanged.

**Accepted tradeoff (G4, named dependency).** On main no shipped node type has an in-port accepting the failure payload, so **no legal graph can wire a `fail` edge**; the task fix loop is internal to the coarse `code` handler (E-74 U1). Fail-edge traversals are therefore structurally zero for every graph buildable today. E-77 ships the derivation and records the axis as **absent** where the graph has no inbound fail edge; the axis becomes live only when a graph-expressed fix loop lands (the per-task-topology follow-up, E74-OQ-3). Handler-counted `fix_attempts` remain the fix axis for today's graphs.

**Acceptance Scenarios**:

1. **Given** an activation at router round r, **When** it produces records, **Then** each record carries round r; records produced outside any activation (e.g. retro) carry no round.
2. **Given** a node with no inbound fail edge, **When** its activation produces records, **Then** the fail-edge fix count is absent — never recorded as 0.
3. **Given** a node with an inbound fail edge, **When** an activation of it produces records, **Then** they carry a fail-edge **re-entry indicator**: 1 if this activation was entered over a fail back edge, 0 if entered otherwise — an event, never a cumulative count.
4. **Given** the heatmap's fix column, **When** re-entry indicators are present, **Then** each re-entered activation adds exactly one fix attempt however many records it emitted (counted once per distinct activation), alongside handler counts (distinct loops: retries within one activation vs re-entries across activations). A node re-entered k times over fail edges contributes exactly k.
5. **Given** FeatureWorkflow or pre-E-77 records, **When** aggregated, **Then** round and fail-edge values are absent and every existing report is unchanged.
6. **Given** an activation later cancelled by region invalidation, **When** it had already emitted records, **Then** those records keep their round and indicator — the work happened; this is not double counting.

---

### User Story 4 — A graph author saves and loads graphs by identity (Priority: P2)

A graph author (via the API today; the canvas once its follow-up wires it) saves a graph and gets back its `graph_sha`; loading that sha returns the graph. Saving a re-tidied layout of an already-stored graph neither changes its identity nor alters the layout any past run is pinned to.

**Why this priority**: Closes E-75 §1.1's assignment and makes the existing (capability-gated) canvas save/load code reachable; P2 because no canvas wiring ships here.

**Independent Test**: `POST /graphs` a graph; `GET /graphs/{sha}` returns it; the catalog reports `save`/`load` true; a second save of the same graph with moved nodes returns the same sha, and the first run started with the original layout still renders its original layout.

**Acceptance Scenarios**:

1. **Given** a schema-valid graph within the size cap, **When** it is saved, **Then** the response carries its `graph_sha` and the validator's result (a draft that fails legality is still saveable; legality comes only from the single validator).
2. **Given** a stored sha, **When** it is loaded, **Then** the graph is returned; **Given** an unknown or malformed sha, **Then** the response is "not found" / rejected, never a server error.
3. **Given** an input that is not schema-valid or exceeds the size cap, **When** it is saved, **Then** it is rejected and nothing is written.
4. **Given** the catalog, **When** it is read, **Then** `save` and `load` are true; `validate` and `run_graph` are true as well (flipped by the canvas run-mode wiring, E75-OQ-1, 2026-09-20).
5. **Given** two saves of the same graph with different layouts, **When** the editor loads that sha, **Then** it receives the most recently saved layout; **and** every run keeps rendering the layout it started with (US5).
6. **Given** a dashboard history backfill or a run start storing a graph, **When** it writes, **Then** the editor's "latest" layout is never moved — only an explicit save moves it.

---

### User Story 5 — Layouts never rewrite history (E72-OQ-7) (Priority: P2)

An operator's post-mortem renders a run's graph with the layout the run started with, even after someone re-tidied the same graph in the editor.

**Why this priority**: E72-OQ-7 is the one way FR-1206's "renders the graph that actually ran" can be subtly false while the sha is right.

**Verified today:** the store is **first-write-wins** (an existing, verifying file is never replaced), not last-write-wins as E72-OQ-7 was phrased: runs are safe, but an editor save of a new layout is silently dropped. Both halves need resolving once `save` is live.

**Acceptance Scenarios**:

1. **Given** a stored graph, **When** a new layout of it is saved, **Then** the identity-addressed graph file is never modified, and the new layout is retained separately, addressed by its own layout identity.
2. **Given** a client-started run, **When** its post-mortem renders, **Then** it uses the layout the run was started with (stored at start and named by the per-run pointer), not the editor's latest — so a save racing a start can never re-pin the run.
3. **Given** two concurrent saves of one graph with different layouts, **When** both complete, **Then** both layouts are retained, no file is torn or corrupt, and the editor's "latest" names one of them — the only last-write-wins surface; it never reaches a run, and a lost update to it (e.g. a Windows handle race after bounded retries) is logged, never an error to the saver.
4. **Given** a missing, torn or dangling "latest", **When** the editor loads the sha, **Then** it receives the first-stored layout — "latest" is a hint, never a failure.
5. **Given** a run without a recorded layout (in-workflow child; pre-E-77 run), **When** it renders, **Then** it uses the start-input layout while history exists, else the first-stored layout — documented, never an error.

---

### Edge Cases

- **FeatureWorkflow in-flight run (R4):** no pointer, no `graph_sha`, no marks, no round; everything renders as today.
- **Graph fails validation at start:** the pointer is written by the client before start and names the sha; no router state and no records exist; never a fabricated value.
- **Pointer write fails** (disk hiccup): the run still starts (E-75 store-write precedent); readers fall back to summary / history; a warning is logged.
- **Pre-E-77 GraphWorkflow runs** (since 2026-09-17): no pointer or stamped fields; history fallback while retained; afterwards "not recorded" — never an error.
- **Replay safety:** no new workflow commands on existing GraphWorkflow paths (SG-3 goldens and feature replay tests unchanged, not re-recorded).
- **Old summary files and benchmark records** still parse; every new field is optional.
- **Unmapped type in a revise loop:** every round's records attribute to `unknown`; rounds still counted.
- **Registry drift** (E72-OQ-8): renamed port or removed type after a run. **On main this is a hard failure:** the run-graph source raises when the pinned graph no longer validates (`dashboard/run_graph.py:111-112`), so both run graph routes answer a server error for every affected run. See FR-021–FR-023.
- **Unsafe or reused run ids:** a run id that is not a safe file name never becomes a path (the pointer is skipped with a warning, the run still starts); a reused workflow id replaces its pointer (last write per id), while the graph, layout and registry files it named stay immutable.
- **Snapshot no longer loadable** (node-type schema changed in a later release): treated exactly as "no snapshot" (FR-023).
- **Unauthenticated write surface:** `POST /graphs` writes files on the localhost-bound dashboard (OQ-11 containment). Writes are size-capped, schema-validated and content-addressed; nothing executes.

## Requirements *(mandatory)*

### Functional Requirements

**Canonical stage mapping**

- **FR-001**: Every shipped node type MUST declare a `canonical_stage` in `CANONICAL_STAGES`; the self-check MUST flag a shipped type without one, while the registry model continues to permit absence for injected / out-of-tree types (R2).
- **FR-002**: `CANONICAL_STAGES` MUST remain single-sourced; nothing restates it.
- **FR-003**: Exactly one pure function (graph layer, R1) MUST resolve a node to its stage: the type's `canonical_stage` if registered and mapped, else the literal `unknown`. It takes the registry as a parameter (so a registry snapshot works unchanged) and does not import `CANONICAL_STAGES` — membership is the self-check's job, keeping the graph layer's import-purity pin intact. Stage marks, graph-state wire and record attribution MUST all call it.
- **FR-004**: `unknown` MUST NOT be a member of `CANONICAL_STAGES` and MUST NOT be accepted as a declared `canonical_stage`.
- **FR-005**: Stage marks MUST include `unknown`-resolved nodes under the key `unknown`, with the existing precedence rule; no node is dropped.
- **FR-006**: A node whose type is absent from the resolving registry MUST resolve to `unknown` in every read-side projection without raising.
- **FR-007**: Records produced inside an activation whose node resolves to `unknown` MUST carry stage `unknown`; records of mapped types keep their handler/lens stage (G2).

**`graph_sha` per run**

- **FR-008**: Every GraphWorkflow run MUST record its `graph_sha` using the existing content-hash function only (R1).
- **FR-009**: Live run state and the run summary (query and exported file) MUST carry `graph_sha`.
- **FR-010**: Benchmark records produced by a graph run MUST carry `graph_sha` (register H3 axis), stamped inside the workflow so in-workflow children (benchmark arms) are covered. Oracle records built by the benchmark parent MUST carry the `graph_sha` of the graph the parent started that arm with.
- **FR-011**: The client start chokepoint MUST write, before the run starts, a per-run pointer naming the run's `graph_sha`, its layout identity, its registry snapshot and its roles (FR-022), for every client-started graph run including runs that later fail (G1). The pointer lives under the graph store root (the one root already shared by the client and the dashboard, and kept when run directories are pruned), keyed by a filename-safe encoding of the run id; it is replaced atomically on workflow-id reuse; a write failure never blocks the start.
- **FR-012**: Readers MUST prefer, in order: per-run pointer / stamped fields, then E-75's history-derived sha; absence renders as "not recorded".
- **FR-013**: The recorded `graph_sha` MUST name a graph present in the store.

**Router-derived axes (G3a, G4)**

- **FR-014**: Records produced inside an activation MUST carry that activation's router round; records outside any activation carry none.
- **FR-015**: One pure function (graph layer) MUST derive, per activation and at the moment the activation is issued, a fail-edge **re-entry indicator**: 1 if the activation was entered over a back edge into that node whose source port is a `fail` port, 0 if the node has such an inbound edge but this activation was entered otherwise, **absent** (never 0) if the node has no inbound fail edge.
- **FR-016**: Records MUST carry the indicator as a field separate from the handler-counted `fix_attempts`; handler counts and the handler convention are unchanged.
- **FR-017**: The heatmap's fix axis MUST add fail-edge re-entries counted once per distinct activation (never once per record), alongside handler counts; with no indicator present, every existing heatmap/SC output is byte-for-byte unchanged.
- **FR-018**: The derivation MUST be exercised end-to-end by an injected registry that admits a fail edge; the spec and ROADMAP MUST name the graph-expressed-loop dependency (E74-OQ-3) as the accepted tradeoff.

**Save / load and layouts (G3b, G3c)**

- **FR-019**: The store MUST keep the identity-addressed graph file immutable once written (first write wins, as today), and MUST retain every stored layout as a complete graph document under a **layout identity** — a content hash of the full document, cosmetics included (for a given `graph_sha` it varies only with cosmetics). Layout files are immutable, content-addressed and verified on read (parses, layout identity matches its name, `graph_sha` matches the graph it is filed under). The client start chokepoint stores the run's own layout.
- **FR-020**: `POST /graphs` MUST accept a schema-valid, size-capped graph, store it and its layout, move the editor's "latest" layout for that sha, and answer the graph sha, the layout identity and the single validator's result (legality failures do not block a save). `GET /graphs/{sha}` MUST return the graph with the "latest" layout (falling back to the first-stored layout when "latest" is missing, torn or dangling), or "not found"; an explicit layout identity MAY be requested. Only an explicit save moves "latest" — never a start or a history backfill. "Latest" is replaced atomically with bounded retry on Windows sharing violations; a lost update is logged, never an error. The catalog MUST report `save` and `load` true. Existing provisional wire shapes are kept; additions are optional fields.

**Registry drift (G3d)**

- **FR-021 (read side)**: A run whose pinned graph no longer validates against the resolving registry MUST NOT produce a server error (today it does). The run graph route still returns the stored graph; the graph-state route answers an explicit "state unavailable: registry drift" result carrying the problems; stage projections resolve affected nodes to `unknown` (FR-006). No second legality or topology builder is introduced (R1).
- **FR-022 (write side)**: The store MUST retain an immutable, content-addressed snapshot of the whole node-type registry in force at client start (one file per registry version, not per run), and the per-run pointer MUST name it together with the run's roles, so a post-mortem validates the pinned graph with the single validator against the registry and roles the run actually used. The snapshot records the client's registry; client and worker share one checkout in this repo — stated, not engineered around.
- **FR-023**: Where no snapshot is recorded or it no longer loads (children, pre-E-77 runs, a later node-type schema change), resolution uses the start input while history exists, else the current registry, with FR-021 degradation — documented, never an error.

**Compatibility and boundaries**

- **FR-024**: Every new field on run summary, run state, benchmark records and wire MUST be optional; FeatureWorkflow runs and pre-E-77 artifacts parse and render as today (R4).
- **FR-025**: Recording MUST add no workflow commands to existing GraphWorkflow paths (replay goldens unchanged, not re-recorded).
- **FR-026**: No frontend *production* code changes; canvas run mode and fleet-strip consumption of per-node stages / `unknown` marks remain the named follow-up (R3). New wire fields are pinned by recorded fixtures produced from the real functions. **Consequence of G3's capability flip (found at task generation, 2026-09-19):** the recorded fixtures live under `interfaces/dashboard/frontend/src/api/__fixtures__/graph/` and are regenerated by `scripts/dump_graph_fixtures.py` (guarded by `tests/test_graph_fixtures_fresh.py`); the recorded catalog is imported by frontend unit tests, two of which pin the all-false recording (`src/api/http-graph.test.ts` save/load refusal cases; `src/api/mock/graph.test.ts:17`). Those two get test-only updates (refusal cases use an explicit no-capability catalog, as `http-graph.chaos.test.ts` already does). The permitted `interfaces/` diff is exactly: regenerated `__fixtures__/graph/**/*.json` + those two test files; verified by `python scripts/check_ui.py`.
- **FR-027**: E-77 MUST NOT grow `stages/code/step.py` (979 of the 1000-line ceiling); stamping happens in the graph workflow's record path, derivations in the graph layer, aggregation in the heatmap.

### Key Entities

- **Node type (registry entry)**: carries `canonical_stage`; presence becomes mandatory for shipped types.
- **Resolved stage**: a `CANONICAL_STAGES` member or `unknown`.
- **`graph_sha`**: pinned graph content hash (cosmetics excluded); key into the store.
- **Layout identity**: content hash of a full graph document, cosmetics included; key to an immutable layout file filed under its graph. "Latest" is an editor-only hint naming one of them.
- **Registry snapshot**: immutable, content-addressed copy of the whole node-type registry, one per registry version, versioned by a schema marker.
- **Per-run pointer**: durable per-run index written at client start under the graph store root: `graph_sha`, layout identity, registry snapshot identity, the run's roles; verified on read field by field (an unresolvable field degrades to "not recorded").
- **Run summary / live run state / benchmark record**: existing; gain optional `graph_sha`; records also gain optional round and fail-edge re-entry indicator.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of shipped node types declare a canonical stage from the fixed list.
- **SC-002**: For any graph of N nodes, stage projection attributes all N (canonical or `unknown`), zero dropped — table-tested with an unmapped and an unregistered type.
- **SC-003**: 100% of client-started graph runs (any terminal outcome) have `graph_sha`, layout and registry snapshot recoverable after history is gone; 100% of benchmark-arm records carry `graph_sha`.
- **SC-004**: Zero behaviour change for FeatureWorkflow runs and pre-E-77 artifacts; existing heatmap/SC outputs on today's records are identical; replay goldens not re-recorded.
- **SC-005**: Records from two graphs of one case partition by `graph_sha` with no manual joins.
- **SC-006**: Re-saving a stored graph with a new layout leaves 100% of pinned runs rendering their original layout; concurrent saves never produce a torn or corrupt file.
- **SC-007**: On the default graph, 0 records carry a fail-edge indicator (absent, not zero); on the injected fail-edge fixture, a node re-entered k times over fail edges contributes exactly k to the heatmap fix axis regardless of how many records each activation emitted.
- **SC-008**: 0 server errors from the run graph routes for runs whose pinned graph no longer validates (today: every such run errors).

## Assumptions

- `CANONICAL_STAGES` is the heatmap list (18 entries: 15-stage vocabulary plus lens columns; `oracle` trails separately). The brief's "13-stage" hypothesis did not match code.
- All 16 shipped types already declare a stage (E-72/E-74); no mapping values change.
- The per-run pointer lives with the run's artifacts, outside anything retention prunes before the run's own record.
- The size cap for save is the existing catalog `max_graph_bytes`.
- Localhost-bind remains the dashboard's containment (OQ-11); E-77 adds no auth.

## Verified context (hypotheses from the brief, checked on main `84ac93a`)

- `canonical_stage` is a registry field (`sdlc/graph/node_types.py`), validated against `CANONICAL_STAGES` (`benchmarks/heatmap.py:25`); all 16 types declare one; gates take their producer's stage.
- `run_view.stage_marks` skips unregistered/unmapped types — the silent drop.
- `graph_sha` lives only in GraphWorkflow memory (`workflows/graph.py:130`) and in history (`dashboard/run_graph.py`); `RunSummary`, `RunState`, `BenchmarkRecord` carry none.
- Retro (writer of `runs/<id>/summary.json`) is skipped on failed executions (E-74 U9).
- Children start inside workflows (`workflows/pipeline_child.py`); no client chokepoint sees them (E-75 V1).
- **Fail edges:** routed `fail` emissions are supported by the dispatcher (`graph_dispatch.py`), but no shipped in-port accepts `NodeFailure`, so no legal graph can wire one; `default.graph.yaml`'s only back edges are the two gate `revise` loops. The `code` handler counts fix attempts internally (`stages/code/step.py:784`, `attempt - 1`).
- **Store:** `GraphStore.put` returns early when a verifying file exists — first-write-wins (`graph/store.py`).
- **Save/load wire:** provisional `SaveOk{sha, validation}`, `LoadOk{sha, graph}`, `LoadMissing` in `dashboard/graph_wire.py`; the canvas provider already calls `POST /graphs` / `GET /graphs/{sha}` gated only by capabilities (`interfaces/dashboard/frontend/src/api/http-graph.ts:54-60`) — flipping `save`/`load` activates it.
- E-74 §12 names no E-77 question; E-72 §10 assigns E72-OQ-7/8; E-75 §1.1 assigns save/load.

## Resolved decisions (user-gated 2026-09-19)

- **OQ-1 → full scope (G3).** Items (a)–(d) are in; (a) under the G4 tradeoff above.
- **OQ-2 → B (G1).** Stamped optional fields + per-run pointer at the client start chokepoint.
- **OQ-3 → B (G2).** `unknown` stamps only activations of unmapped types; mapped and lens stages kept.
- **E72-OQ-7 → resolved by FR-019/FR-020 and US5** (immutable identity file, content-addressed layouts, per-run layout pin, editor-only "latest").
- **E72-OQ-8 → resolved by FR-021–FR-023** (read-side degradation + write-side registry snapshot named by the per-run pointer).

## Pressure-test dispositions (2026-09-19)

Advisor (`.workspace/tmp/advisor-e77-1.md`) and skeptic (`.workspace/tmp/skeptic-e77-1.md`) answers, dispositioned:

| # | finding | source | disposition |
|---|---|---|---|
| P1 | No legal graph can wire a `fail` edge today | skeptic 1.1 (verified) | **Holds** — G4 tradeoff stands |
| P2 | "Absent, not zero" is the honest encoding | skeptic 1.2 | **Holds** |
| P3 | A cumulative per-record count is multiplied by records-per-activation and summed triangularly by the heatmap | skeptic 1.3 | **Accepted** — indicator semantic, counted once per activation (US3 AS3–4, FR-015–017, SC-007) |
| P4 | Round is obtainable without commands; stamp in the graph workflow's record path, count captured when the activation is issued | skeptic 1.4, advisor D-d | **Accepted** (FR-014/015, FR-025) |
| P5 | History backfill must never move "latest" | skeptic 2.1 | **Accepted** (US4 AS6, FR-020) |
| P6 | Windows sharing violation on the mutable "latest" | skeptic 2.2, advisor D-a | **Accepted** — bounded retry, lost update logged (US5 AS3, FR-020) |
| P7 | Save racing a start re-pins the run | skeptic 2.3 | **Accepted** — the start stores and pins the run's own layout (US5 AS2, FR-019) |
| P8 | Replace "latest" with a timestamped directory scan | skeptic 2.5 | **Rejected** — clock-ordered names are neither content-addressed nor verifiable; one atomic pointer with a verified fallback is smaller |
| P9 | Layout = full document hashed with cosmetics, not a cosmetics-only file | advisor D-a | **Accepted** (FR-019) — no layout model or merge step |
| P10 | Drift crashes `run_graph.py:111-112` today | skeptic 3.1 (verified) | **Accepted** (FR-021, SC-008) |
| P11 | Replace the snapshot by a degraded topology builder inferring ports from edges | skeptic 3.3 | **Rejected** — a second topology/legality path violates R1; the snapshot makes client-started runs render fully, the explicit drift result covers the rest |
| P12 | Snapshot the whole registry, one file per version, schema-marked; unloadable = no snapshot | advisor D-c | **Accepted** (FR-022/023) |
| P13 | Post-mortem validation needs the run's roles, lost with history | advisor D-b | **Accepted** — the pointer names roles (FR-011/022) |
| P14 | Pointer in the graph store root, filename-safe run id, atomic replace on id reuse | advisor D-b | **Accepted** (FR-011); skeptic 4 (`runs/<id>/`) **rejected** — three disagreeing roots, and run dirs are what operators prune |
| P15 | Oracle records bypass the workflow's record path | advisor D-d | **Accepted** — parent stamps the arm's sha (FR-010) |
| P16 | Graph-layer purity: resolver must not import `CANONICAL_STAGES` | skeptic 5.1 | **Accepted** (FR-003) |
| P17 | `code/step.py` at 979/1000 lines | skeptic 5.3 (verified) | **Accepted** (FR-027) |
| P18 | Cancelled activations keep their records' round/indicator | advisor D-d | **Accepted** (US3 AS6) |

## Open Questions

- **E77-OQ-1 — pre-existing heatmap inflation (not E-77's to fix; recorded).** The `code` handler stamps `fix_attempts = attempt − 1` on every attempt record (`stages/code/step.py:784`) and the heatmap sums records (`benchmarks/heatmap.py:101`), so a task needing n attempts reports n(n−1)/2 fix attempts rather than n−1 (skeptic 1.3, verified). FR-017 pins today's outputs byte-for-byte, so E-77 neither copies nor repairs the convention; the repair (and its effect on recorded benchmark baselines) is a named follow-up for the benchmark owner.

  **RESOLVED (2026-09-20):** fixed by the `heatmap-fix-inflation` bug flow on branch `fix/heatmap-fix-inflation` — Direction A, aggregate-side: the heatmap's fix axis takes `max(fix_attempts)` per `(case_id, stage, run_id, task_id)` group and sums the group maxima (`task_id=None` records pass through per record). The producer stamp is unchanged; all recorded history re-aggregates honestly to n−1 per task. FR-017's pins stayed byte-identical. Chain: `.specify/bugs/heatmap-fix-inflation/`.
