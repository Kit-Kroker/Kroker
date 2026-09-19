# Tasks Quality Checklist: E-77 — canonical_stage + graph_sha per run

**Purpose**: Validate tasks.md quality (format, traceability, ordering, verifiability, file references) before implementation seats pick up work
**Created**: 2026-09-19 (reviewer seat, tasks gate)
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [tasks.md](../tasks.md)

**Note**: Items test the TASK LIST as written — structure, coverage, ordering, executability — not the implementation. Evidence gathered against main `84ac93a` and the four files cited by the FR-026 amendment.

## FR-026 Amendment Verification (called out by the brief)

- [x] CHK001 Does `scripts/dump_graph_fixtures.py` actually write the recorded fixtures under `interfaces/dashboard/frontend/src/api/__fixtures__/graph/`, including `catalog.json` (capabilities) and `run_state/graph_state.recorded.json` (`project_graph_state` output)? [Traceability, T040] — verified: OUT at line 47, catalog at line 223, graph states at lines 204–216
- [x] CHK002 Does `tests/test_graph_fixtures_fresh.py` fail when committed recordings differ from a fresh `build()`? [Traceability, T040] — verified: `test_committed_recordings_equal_a_fresh_build` + tamper chaos tests
- [x] CHK003 Would flipping `Capabilities.save/load` to true actually break the cited frontend tests? [Traceability, T041] — verified: `http-graph.test.ts:4,18` serves the recorded catalog to the `:47-56` refusal cases (save/load would stop refusing); `mock/graph.test.ts:17` pins the recorded all-false capabilities
- [x] CHK004 Does T041's fix reference a real existing pattern? [Traceability, T041] — verified: `NO_CAPS` in `http-graph.chaos.test.ts:20,96,115,131,140`
- [x] CHK005 Is the amendment propagated consistently across the artifacts? [Consistency, spec.md FR-026, plan.md:54/76/146/159, quickstart.md §3, contracts/http-graphs.md] — yes everywhere; one stale rationale sentence remains in research.md R-11 ("no frontend change is needed") — LOW, see Notes

## Traceability & Coverage

- [x] CHK006 Does the Traceability table cover every FR-001..FR-027 and SC-001..SC-008 with real task mappings? [Traceability, tasks.md §Traceability] — all 27 FRs and 8 SCs present; each mapped task set was cross-checked against task content (e.g. FR-018 → T029 injected fail-edge fixture + T045 ROADMAP naming; FR-022/023 → T010–T011 + T036–T037; SC-003 → T019–T023; SC-005 → T019)
- [x] CHK007 Do the user stories' acceptance scenarios map to tasks, including the deferred ones? [Coverage, spec §User Scenarios] — US1 AS1–5 (T013–T023), US2 AS1–7 (T002–T003, T015–T016, T026–T028, T036 for AS5), US3 AS1–6 (T013–T016, T029–T033), US4 AS1–6 (T034–T035, T038–T041 incl. the AS6 backfill pin in T034), US5 AS1–5 (T008–T011, T034–T037)
- [x] CHK008 Does every task map to a requirement, story, or declared cross-cutting purpose (no orphan tasks)? [Coverage] — T001 (baseline), T012/T025 (checkpoints), T024 (ownership rows required by plan's Constitution Check), T042–T045 (gates/docs per R5/R-13)

## Format & Structure

- [x] CHK009 Is the checklist format strict (checkbox, T-ID, [P], [USn] labels)? [Clarity, tasks.md §Format] — `- [ ]` + T001–T045 sequential; [P] on parallelizable tasks; [USn] on story tasks per the doc's own convention (foundational/gate tasks legitimately unlabelled)
- [x] CHK010 Are tasks bite-sized (one cohesive behaviour or one file-cluster per task)? [Clarity] — largest are T023/T037, each one behaviour across the files its RED test (T022/T036) already split out
- [x] CHK011 Are exact file paths used, and does every referenced existing file exist? [Traceability] — all verified on main, incl. `tests/graph/test_graph_content_sha.py`, `tests/graph_workflow/test_graph_view_dispatch.py`, `test_pipeline_child_upgrade.py`, `tests/test_benchmark_models.py`, `test_run_state_model.py`, `test_run_summary_model.py`, `test_run_summary_build.py`, `test_benchmark_workflow.py`, `test_dashboard_fleet_marks.py`, `scripts/check_ui.py`, `_in` helper (`node_types.py:45`), purity pin `start.py` entry = `{stdlib, sdlc.graph.store}` (`test_graph_purity.py:48`) and `store.py` entry matching T011's amendment plan

## Ordering & Protocol

- [x] CHK012 Is RED-before-GREEN enforced for every implementation task? [Consistency, tasks.md §Tests] — T002→T003, T004→T006, T005→T007, T008→T009, T010→T011, T013→T014, T015→T016, T017→T018, T020→T021, T022→T023, T026→T027, T029→T030/T031, T032→T033 (byte-pin explicitly "written and passing before T033"), T034→T035, T036→T037, T038→T039
- [x] CHK013 Do phase dependencies match the plan's slice dependencies? [Consistency, plan.md §Delivery slices] — Phase 2 blocks stories (⚠️ before T012), US3 needs US1's T014/T016, US5 store before US4 routes, docs last
- [x] CHK014 Are standing rules stated (one pytest per call, 1000-line ceiling, imports_passed_through, no golden re-recording, no attribution trailers)? [Consistency, tasks.md §Standing rules]

## Verifiability & Hygiene

- [x] CHK015 Does every task carry an explicit test command where one applies? [Measurability] — all except T024 (AGENTS.md rows — no test applicable)
- [x] CHK016 Is the tasks file free of placeholders (TBD/TODO/NEEDS CLARIFICATION)? [Gap] — confirmed by scan and full read
- [x] CHK017 Are new test files declared and distinct from existing ones? [Clarity, tasks.md §Notes] — four new files declared; every other referenced test file exists today
- [x] CHK018 Do the numeric expectations line up across tasks and spec (e.g. T031/T032 indicators 0,1,1 → exactly 2 added, matching FR-017/SC-007's once-per-distinct-activation rule)? [Consistency]

## Notes

- Verdict context: reviewer gate run for E-77 after GATE 2; full findings in `.workspace/tmp/reviewer-e77-tasks-1.md`.
- LOW (non-blocking): research.md R-11 rationale line "no frontend change is needed (FR-026)" predates the amendment's "no frontend *production* change" wording; spec/plan/quickstart/contracts all carry the amended form, which governs.
- Cosmetic: T019 and T028 are labelled "RED→GREEN" while being integration verification / behaviour pins that follow their unit-level RED pairs — sequencing itself is correct.
