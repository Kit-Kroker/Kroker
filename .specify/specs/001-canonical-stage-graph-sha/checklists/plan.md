# Plan Quality Checklist: E-77 — canonical_stage + graph_sha per run

**Purpose**: Validate plan-artifact quality (plan.md, research.md, data-model.md, contracts/, quickstart.md) before GATE 2 and /speckit-tasks
**Created**: 2026-09-19 (reviewer seat, plan gate)
**Feature**: [spec.md](../spec.md)

**Note**: Items test the PLAN as written — traceability, precision, consistency, verifiability — not the implementation. Evidence was gathered by reading main `84ac93a` at the cited anchors.

## Spec → Plan Traceability

- [x] CHK001 Is every FR-001..FR-027 mapped to a delivery slice S1..S9 and/or research decision R-1..R-13? [Traceability, Spec §Requirements]
- [x] CHK002 Are US1..US5 acceptance scenarios covered by slice headers without orphan scenarios? [Traceability, Spec §User Scenarios] — S1 (US2 AS1–2,5–7), S2 (US1 AS1–3,5; US2 AS3–4; US3 AS1,5–6), S3 (US3 AS2–4), S4 (US1 AS5), S5 (US5), S6 (US1 AS4), S8 (US4)
- [x] CHK003 Are SC-001..SC-008 each provable by a named slice/test? [Traceability, Spec §Success Criteria] — SC-001/002 (S1), SC-003 (S6+S4, by mechanism), SC-004 (quickstart heatmap/replay rows), SC-005 (S2/R-4, by mechanism), SC-006 (S5), SC-007 (S3), SC-008 (S7)
- [x] CHK004 Do FR-013, SC-003 and SC-005 have a designed home even though their IDs are not repeated in the slices? [Traceability] — FR-013 → S6/R-8 (graph stored before pointer; reader verifies each named file, contracts/records-and-store.md); SC-003 → S6 ("never blocks" covers any terminal outcome) + S4 arm sha; SC-005 → S2/R-4 (every record carries `graph_sha`)
- [x] CHK005 Are the GATE 1 rulings G1–G4 and brief rulings R1–R5 carried into design decisions rather than silently dropped? [Consistency, Spec §Binding rulings] — G1→R-8, G2→R-4, G3→R-5/R-6/R-7/R-9/R-10/R-11, G4→R-5 feasibility; R1–R5 in the plan's Constitution Check table
- [x] CHK006 Are the spec's pressure-test dispositions P1–P18 reflected (accepted ones designed, rejected ones with reasons)? [Consistency, Spec §Pressure-test dispositions] — P8/P11 rejections restated in R-6/R-10 rationale

## Placeholder Completeness

- [x] CHK007 Are there zero unresolved-marker placeholders (NEEDS CLARIFICATION / TBD / TODO) across plan artifacts? [Gap] — plan.md:59 states none remain; scan confirms
- [x] CHK008 Does every open fork from Phase 0 terminate in a decision R-1..R-13 with rationale and rejected alternatives? [Completeness, research.md]

## Path & Anchor Precision

- [x] CHK009 Do all cited repository files exist at the stated paths? [Clarity] — all verified on main: `src/sdlc/graph/{model,node_types,run_view,store,start,topology,validate,router}.py`, `src/sdlc/workflows/{graph,graph_dispatch,run_host,pipeline_child,models,benchmark_host}.py`, `src/sdlc/benchmarks/{models,heatmap,workflow}.py`, `src/sdlc/core/models.py`, `src/sdlc/observability/summary.py`, `src/sdlc/dashboard/{graph_wire,run_graph,api}.py`, `interfaces/dashboard/frontend/src/api/http-graph.ts`, test files incl. `tests/graph/test_graph_store.py`, `tests/core/`
- [x] CHK010 Are the load-bearing line anchors accurate? [Clarity] — spot-checked: `heatmap.py:25` (CANONICAL_STAGES), `run_graph.py:111-112` (drift RuntimeError), `store.py:34-41` (default_root) and put() first-write-wins, `graph.py:130` (`_graph_sha`), `graph_dispatch.py:160` (ref mint), `router.py:345-357`/`477-490`, `topology.py:42` (is_back_edge), `validate.py:232-234`/`552-557`, `core/models.py:477/507`, `summary.py:136`, `benchmark_host.py:94-116`, `pipeline_child.py:36-44`, `api.py:189-202`/`224-235`, `node_types.py:63-64`/`256-265`/`313`, `run_view.py:211-212` (the silent drop), `heatmap.py:101`, http-graph.ts:54-60, `code/step.py` = 979 lines with `:784` `fix_attempts=attempt-1`, purity pin `node_types.py` allowed-set as R-1 states
- [x] CHK011 Are file sizes claimed in the plan's ceiling watch-list correct? [Consistency, plan.md Constitution Check] — graph_wire 543, run_graph 130, store 90, graph_dispatch 329, heatmap 190: all < 600 as stated

## Validation Verifiability

- [x] CHK012 Does quickstart.md give explicit, runnable test commands per scenario (not descriptions)? [Measurability, quickstart.md] — per-scenario pytest invocations with real paths, split fast / temporal / static gates
- [x] CHK013 Do the regression pins named by the plan exist today? [Traceability] — `tests/replay/` (incl. test_feature_replay.py), `tests/graph/test_graph_purity.py`, `tests/test_benchmark_heatmap.py`, `tests/graph_workflow/test_graph_view_query.py`, `test_parent_wiring.py`
- [x] CHK014 Are static gates explicit (ruff, mypy, file-size, empty `interfaces/` diff)? [Measurability, quickstart.md §3]

## Contract & Data-Model Consistency

- [x] CHK015 Do contracts/ and data-model.md agree on wire shapes (`SaveOk`/`LoadOk` +`layout_sha`, `GraphStateUnavailable`, `NodeRunState.canonical_stage`, capabilities flip)? [Consistency, contracts/http-graphs.md, data-model.md]
- [x] CHK016 Is the optional-fields rule (FR-024) applied uniformly across records, summary/state, wire and store readers? [Consistency, data-model.md, contracts/records-and-store.md]
- [x] CHK017 Are cross-artifact invariants stated testably (re-entry ∈ {None,0,1}; unknown-stage ↔ record.stage; latest moved only by save)? [Measurability, data-model.md §GraphAttribution invariants, contracts/records-and-store.md]

## Constraint Compliance

- [x] CHK018 Does the plan keep the binding architecture constraints with named mitigations (replay neutrality FR-025, code/step.py FR-027, purity pin amendment, ownership-table rows, grace U6)? [Consistency, plan.md Constitution Check + Risks]
- [x] CHK019 Are risks paired with concrete mitigations and tests (Windows retry simulation, byte-identity pin, sandbox passthrough)? [Coverage, plan.md Risks]

## Notes

- Verdict context: reviewer gate run for E-77 GATE 2; full findings in `.workspace/tmp/reviewer-e77-plan-1.md`.
- Minor citation nits (non-blocking): `test_feature_replay.py` and `benchmark_host.py` are cited without their `tests/replay/` / `src/sdlc/workflows/` prefixes (each resolves uniquely in the repo); R-5 cites `graph_dispatch.py:201` where the `_started` write is at :205 (same function, 4-line drift).
- FR-013, SC-003, SC-005 are delivered by mechanism rather than by ID citation; the delivering slices and tests are named, so /speckit-tasks coverage is unaffected.
