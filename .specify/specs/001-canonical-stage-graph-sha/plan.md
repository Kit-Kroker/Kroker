# Implementation Plan: E-77 — graph store + custom-graph benchmark mapping

**Branch**: orchestrator's call (spec dir `001-canonical-stage-graph-sha`) | **Date**: 2026-09-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `.specify/specs/001-canonical-stage-graph-sha/spec.md` (final: GATE 1 cleared 2026-09-19, full scope; advisor and skeptic dispositions P1–P18).

## Summary

FR-1206 plus the rest of the E-77 family row, backend-only:

- **Stage resolution.** A single pure stage resolver attributes every node to a `CANONICAL_STAGES` member or the literal `unknown`. Stage marks, graph-state wire and records all use it, and the shipped registry is pinned complete.
- **Run identity.** Every graph run records `graph_sha` on its live state, summary and every benchmark record. Records are stamped in the graph workflow's record path, together with activation, round, node stage and a fail-edge re-entry indicator; oracle records are stamped by the benchmark parent.
- **Start-time persistence.** The client start chokepoint writes, before the start: the graph, the run's own layout, a registry snapshot and a per-run pointer.
- **Save/load.** Save/load routes go live on a store whose identity files stay immutable. Layouts are content-addressed documents; an editor-only `latest` hint is the only last-write-wins surface (E72-OQ-7).
- **Registry drift** stops being a server error (E72-OQ-8).
- **Fail-edge axis.** It is derived honestly: absent for every graph buildable today. The dependency on a graph-expressed fix loop (E74-OQ-3) is the accepted G4 tradeoff.

Design decisions and alternatives: [research.md](research.md). Entities and files: [data-model.md](data-model.md). Contracts: [contracts/](contracts/). Validation: [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python ≥ 3.11

**Primary Dependencies**:
- pydantic v2
- temporalio 1.30.0 (workflow sandbox; `imports_passed_through` for graph-layer models)
- FastAPI (dashboard router)
- PyYAML (graph io)

**Storage**: Files only; there is no database. `graphs/` under the graph store's `default_root()` holds:
- identity files;
- `<sha>/layouts/`, `<sha>/latest`;
- `registry/`;
- `runs/`.

Benchmark records keep their existing store. `summary.json` keeps its existing export.

**Testing**: pytest, in the fast unit tier plus the `temporal` marker. The replay goldens (`tests/replay`) and the recorded wire fixtures are the regression pins.

**Target Platform**: Temporal worker, CLI client and dashboard backend on Windows and Linux. Windows file-sharing semantics are an explicit constraint (R-6).

**Project Type**: Library + worker + web-service backend (single repo, `src/sdlc/`).

**Performance Goals**:
- Start adds at most four small file writes (identity already exists).
- The heatmap adds one O(records) pass that only runs when an indicator exists.
- The dispatcher adds an O(inputs) check per activation.

**Constraints**:
- No new workflow commands on existing GraphWorkflow paths (FR-025).
- The FeatureWorkflow command sequence is unchanged (U6 grace).
- `sdlc/graph` module-import purity pin.
- 1000-line file ceiling; `stages/code/step.py` stays untouched (FR-027).
- No frontend production code changes; regenerated fixtures + two test-only updates are the permitted `interfaces/` diff (FR-026).
- Localhost-bound unauthenticated dashboard (OQ-11).

**Scale/Scope**: 16 node types, one registry snapshot per code version, and one pointer per client-started run.

No NEEDS CLARIFICATION remain; R-1…R-13 resolve all of them.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is an unfilled template. The binding project gates are therefore `AGENTS.md` (root), `src/sdlc/workflows/AGENTS.md`, `src/sdlc/core/AGENTS.md`, the brief's R1–R5 and GATE 1's G1–G4.

| gate | source | pre-design | post-design |
|---|---|---|---|
| Cross-stage calls banned; the orchestrator is the sole coordinator | AGENTS.md slices | pass (no stage code changes) | pass: stamping lives in `GraphWorkflow`, oracle stamping in the benchmark parent |
| Producer owns its artifacts; `core/` = config and envelopes only | AGENTS.md, core Rule 5/7 | pass | pass: `GraphAttribution` in `benchmarks/models.py` (BenchmarkRecord's home); `RunSummary`/`RunState` gain a plain `str \| None`; `core/` imports nothing new |
| 1000-line ceiling; baselined files never grow | AGENTS.md | pass | pass: `code/step.py` untouched. Watch: `graph_wire.py`, `run_graph.py`, `store.py`, `graph_dispatch.py`, `heatmap.py` are all < 600 lines today |
| Attribute ownership: one owner per attribute, cross-host readers recorded | workflows/AGENTS.md | pass | pass: new `GraphDispatcher._attrib` (owner dispatcher, reader `GraphWorkflow._stamp`) and the `GraphWorkflow._record` override get table rows in the same diff |
| Grace edits: FeatureWorkflow command sequence unchanged unless patched | workflows/AGENTS.md U6 | pass | pass: `RunHost._retro` passes one extra argument (`None` for Feature); content only, no command change; `tests/replay/test_feature_replay.py` unchanged |
| Graph layer pure; hashing and legality never reimplemented | R1, test_graph_purity | pass | pass: new graph-layer functions import only already-allowed modules; `store.py` gains `sdlc.graph.node_types` (registry snapshot) and `sdlc.core.models` (pointer roles), both already allowed elsewhere in the package — a pin-list amendment in `test_graph_purity.py`, reviewed as intentional: still pure, no Temporal; the drift path reuses `validate` |
| `unknown` recorded, not a validation error | R2 | pass | pass |
| Backend-only; save/load flip in scope | R3, G3 | pass | pass: no frontend production code; the `interfaces/` diff is limited to regenerated recorded fixtures + two test-only updates forced by the flip (FR-026 amendment) |
| FeatureWorkflow runs render as today | R4 | pass | pass: all fields optional; routes unchanged for legacy runs |
| Docs describe main | R5 | pass | pass: docs are edited in the landing task only |
| Core envelopes keep `extra="ignore"` | project memory | pass | pass |

No violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/001-canonical-stage-graph-sha/
├── spec.md            # final (GATE 1 + dispositions)
├── plan.md            # this file
├── research.md        # R-1 … R-13
├── data-model.md
├── contracts/
│   ├── http-graphs.md
│   └── records-and-store.md
├── quickstart.md
├── checklists/requirements.md
└── tasks.md           # /speckit-tasks (after GATE 2)
```

### Source Code (repository root)

```text
src/sdlc/graph/
├── model.py           # + PipelineGraph.document_sha()                         (R-6)
├── node_types.py      # + UNKNOWN_STAGE, resolve_stage; check_node_types(require_mapped)   (R-1, R-2)
├── run_view.py        # stage_marks uses resolve_stage; + fail_reentry()      (R-1, R-5)
├── store.py           # + layouts, latest (retry), registry snapshot, pointer; save() vs put()   (R-6..R-8)
└── start.py           # start_graph_run writes identity+layout+registry+pointer before start   (R-8)
src/sdlc/workflows/
├── graph.py           # _record override + _stamp; run_state graph_sha        (R-3, R-4)
├── graph_dispatch.py  # _attrib per activation, filled in _start             (R-4, R-5)
├── run_host.py        # _retro passes graph_sha to build_run_summary         (R-3)
├── pipeline_child.py  # on_graph callback                                     (R-9)
└── AGENTS.md          # ownership rows
src/sdlc/benchmarks/
├── models.py          # + GraphAttribution; BenchmarkRecord.graph            (R-4)
├── heatmap.py         # once-per-activation fail re-entry pass               (R-12)
└── workflow.py        # oracle records stamped with the arm's sha            (R-9)
src/sdlc/core/models.py          # RunSummary.graph_sha, RunState.graph_sha   (R-3)
src/sdlc/observability/summary.py  # build_run_summary(graph_sha=)           (R-3)
src/sdlc/dashboard/
├── graph_wire.py      # SaveOk/LoadOk.layout_sha, caps save/load, NodeRunState.canonical_stage, GraphStateUnavailable   (R-10, R-11)
├── run_graph.py       # no raise on drift; pointer fallback; snapshot registry   (R-10)
└── api.py             # POST /graphs, GET /graphs/{sha}; graph_state union     (R-11)
tests/graph/                     # resolver, completeness, re-entry, store, start, purity pin
tests/graph_workflow/            # stamping, rounds, unknown, parent/oracle
tests/test_benchmark_heatmap.py  # byte-identity + k re-entries
tests/test_dashboard_*           # routes, wire fixtures (re-recorded from real functions)
docs: ROADMAP.md, docs/roadmap/pipeline-as-data.md, ARCHITECTURE.md, E-72/E-75 spec errata   (landing task, R-13)
```

**Structure Decision**: The existing single-repo layout; no new packages. Every change lands in the module that already owns the concern. The graph layer holds the pure rules; `workflows/` holds stamping; `benchmarks/` holds the record model and aggregation; `dashboard/` holds routes and wire. This matches the E-72…E-75 placement pins.

## Delivery slices (for /speckit-tasks)

Each slice is independently testable and ordered by dependency. P1 stories come first.

1. **S1 — resolver + completeness + marks** (US2 AS1–2, 5–7): `node_types.py`, `run_view.stage_marks`. Pure, no Temporal.
2. **S2 — record attribution model + stamping** (US1 AS1–3, 5; US2 AS3–4; US3 AS1, 5–6; SC-005): `GraphAttribution`, dispatcher `_attrib`, `GraphWorkflow._record/_stamp`, `RunSummary`/`RunState.graph_sha`, `build_run_summary`. Replay gate: goldens unchanged.
3. **S3 — fail re-entry + heatmap** (US3 AS2–4, SC-007): `fail_reentry`, the injected fail-edge registry fixture, the heatmap pass, and the byte-identity pin over recorded records.
4. **S4 — oracle stamping** (US1 AS5; SC-003 for arms): `on_graph` callback, oracle records.
5. **S5 — store: layouts, latest, registry snapshot, pointer** (US5, FR-019/022, SC-006): the `store.py` API, the Windows retry and the purity-pin amendment.
6. **S6 — start chokepoint** (US1 AS4, FR-011, FR-013; SC-003): `start_graph_run` writes, the safe-name rule, never blocking.
7. **S7 — run graph routes: drift and retention** (FR-012/021, SC-008): `run_graph.py`, `GraphStateUnavailable`, snapshot registry use, `NodeRunState.canonical_stage`, fixture re-record.
8. **S8 — save/load routes + capability flip** (US4): `api.py`, wire additions, catalog; regenerate recorded fixtures (`scripts/dump_graph_fixtures.py`) and update the two frontend unit tests pinned to the all-false catalog (FR-026).
9. **S9 — landing docs** (R5, R-13): ROADMAP / family row / ARCHITECTURE / E-72 + E-75 errata, and the E77-OQ-1 follow-up recorded.

Dependencies: S2 needs S1. S3 needs S2. S4 needs S2. S6 needs S5. S7 needs S5 and S1. S8 needs S5. S9 comes last.

## Risks

| risk | mitigation |
|---|---|
| `_retro` argument change mistaken for a command change | `tests/replay/test_feature_replay.py` and the SG-3 goldens run unchanged in S2's gate; they are never re-recorded |
| The heatmap's byte-identity silently breaks | pinned by a test over the recorded records fixture before S3 changes code |
| Windows handle races on `latest`/pointer | bounded-retry helper with a unit test that simulates `PermissionError` |
| Purity-pin amendment slips a Temporal import into `store.py` | the pin lists modules exactly; the amendment adds only `sdlc.graph.node_types` and `sdlc.core.models` |
| Capability flip breaks frontend unit tests pinned to the all-false recorded catalog | test-only updates in S8, gated by `python scripts/check_ui.py` (the only sanctioned JS entry point, `interfaces/AGENTS.md`) |
| FINAL `GraphState` wire change | additive optional field; fixtures re-recorded from the real projection; TS mirror named in the canvas follow-up |
| Temporal sandbox pydantic duplication for new graph-layer models read in workflows | every workflow module naming new graph/benchmarks models imports them under `imports_passed_through()` (project memory fingerprint: ValidationError with input_type == class name) |

## Complexity Tracking

None — no Constitution Check violations.
