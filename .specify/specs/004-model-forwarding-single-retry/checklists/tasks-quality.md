# Checklist: Tasks Quality — 004 Model Forwarding and a Single Retry Layer

**Purpose**: Unit tests for `tasks.md` — coverage of every FR/SC/edge case/plan decision/stop-guard, task format, dependency/parallel correctness, TDD order, path validity, scope discipline, escalation rules. Not implementation tests.

**Created**: 2026-10-01 (reviewer seat, tasks review)

## Requirement Coverage

- [x] CHK001 - Does every functional requirement FR-001..FR-015 map to at least one task that implements or verifies it, or a stated exclusion? — **PASS**: coverage-table rows verified against actual task content (FR-001→T025/T029/T032/T033; FR-002→T026/T028/T029/T030/T031; FR-003→T027/T029; FR-004/005→T016-T024; FR-006→T006/T025; FR-007→T010-T013; FR-008→T008/T009/T014/T015/T029; FR-009→T011/T014; FR-010→T003/T014/T035; FR-011→T009/T038; FR-012→T007; FR-013/014→stated exclusion row; FR-015→T030/T038).
- [x] CHK002 - Does every success criterion SC-001..SC-005 map to a closing task? — **PASS**: SC-001/SC-004→Phase 6 checkpoint (T025/T035); SC-002→Phase 5 checkpoint (T024); SC-003→T009/T014; SC-005→T007 checkpoint.
- [x] CHK003 - Does every edge case E1..E8 map to a task or a stated exclusion? — **PASS**: E1,E2→T025 (cases d, b); E3→T027/T029; E4→T034; E5→T003/T014/T035; E6→accepted risk (Q3) + T037; E7→T009; E8→T009. (E4's credential-message clause: see CHK008.)
- [x] CHK004 - Does every plan decision D1-D10 and D7a map to tasks? — **PASS**: D1/D2→T028/T029; D3→T011/T012/T013; D4→T010 + SG-5 in T014; D5→T020-T023; D6→T027/T029; D7a→T032; D7→T033; D8→T012/T010 (assessment gains the capability via `build_agents`, no override surface added); D9→T034; D10→standing rule + T009.
- [x] CHK005 - Are stop-guards SG-1..SG-5 attached to the tasks that can trigger them? — **PASS**: SG-1/SG-5/SG-2→T014; SG-2/SG-3→T035; SG-4→T030; all binding via the standing rules.
- [x] CHK006 - Are FR-006's three mandatory subjects (serial role, clarify fan-out agents, benchmark-arm `default`) plus the recording fake tasked? — **PASS**: T006 (recording fake, distinguishing ids) + T025 cases a/b/e; f (sub-question) and g (architect tool) go beyond the minimum.
- [x] CHK007 - Is FR-011 (unchanged stage outcomes on exhausted retries) carried by more than the request-count assertion? — **PASS** (with note): T009 drives real exhaustion under `AGENT_ACTIVITY_CONFIG`, T038 runs the suites that pin the degrade paths, and D10's mechanism argument (only the retry count changes) is restated as a standing rule; recommended (non-blocking) that T009 also assert the observed failure outcome, not just the count.
- [ ] CHK008 - Is E4's second clause (a missing credential under an override must not fail mid-run *without a clear message*) asserted anywhere? — **FAIL** (minor): T034 asserts warm-up and deadlock timing only; T025 cases a-g include no missing-credential case. One assertion in T034 or T025 closes it.

## Task Format

- [x] CHK009 - Does every task line match the format `- [ ] Tnnn [P?] [US?] description with path`? — **PASS**: all 38 lines conform; every task names concrete file paths or commands.
- [x] CHK010 - Are the `[US]` tags consistent with the phase headers and the phase-order table (3=US4, 4=US3, 5=US2, 6=US1)? — **PASS**: tags match; the non-priority order (US3→US2→US1) is stated with the plan's rationale.
- [x] CHK011 - Do the `[P]` markers match the dependency notes and the parallel examples? — **PASS**: T007, T010, T016-T019, T026/T027, T036/T037 marked parallel; dependency lines and "Parallel examples" agree; same-file sequences (T011→T012→T013, T028→T029, T033 after T032) correctly serial.

## Ordering and Dependencies

- [x] CHK012 - Does every behaviour task have its RED test before it, with no implementation lacking a guarding test? — **PASS**: tests-first sections in Phases 4/5/6; T025's "RED on all but c and d" is correctly reasoned (c and d pass on main by construction); T015/T029's added tests are post-implementation extensions of existing RED files, not behaviour tasks.
- [x] CHK013 - Do the dependencies cover all same-file and same-package sequences, and is Phase 6 gated on Phases 4 and 5? — **PASS**: explicit ("Phase 6 needs Phase 4 ... and Phase 5"); per-phase chains complete; T024 and T035 are the phase-closing verification tasks.
- [x] CHK014 - Is the tasks-phase ↔ plan-phase mapping consistent, including where Phase A's evidence is produced? — **PASS**: table maps 1→A, 2→B/D split, 3→A(US4), 4→B, 5→C, 6→D, 7→E; the plan's Phase-A stacked-count evidence is produced inside T009 (run on a clean worktree of the base sha) and recorded in `baseline.md` — later than Phase 1 but present and quickstart-consistent.

## Paths and Executability

- [x] CHK015 - Does every referenced path exist on main or get created by an earlier task? — **PASS**: verified existing — `tests/conftest.py`, `tests/fakes/fake_agents.py`, `tests/test_benchmark_arms.py`, `tests/test_role_model_resolution.py`, `tests/test_cli_role_model.py`, `tests/graph/` (graph validation tests), `tests/replay/`, `tests/durability/test_first_workflow_task_time.py`, `tests/durability/test_sandbox_module_marking.py` (module pin — T005's addition is exactly what that test's docstring demands), `scripts/check_ui.py`, `interfaces/` (problem codes do reach `interfaces/dashboard/frontend/src/api/graph-types.ts`, so T023's gated regeneration is real), the three AGENTS.md clause files, `.workspace/tasks/2026-09-30-model-forwarding-and-single-retry-layer.md`, `runner.py` `_warm_workflow_side_imports` (:43), `benchmarks/workflow.py` `_cell_config` (:62), `research/stage.py` :104/:358, `research/step.py` :63, `code/step.py` :770; new files (model_ids.py, baseline.md, inventory.md, the four new test files, the stub, the fixture) are each created by an earlier task than their first use.
- [x] CHK016 - Is every verification command a single pytest invocation in the dev container, matching quickstart.md? — **PASS**: standing rule + T014/T024/T035/T038 ("separate commands", "each as its own command"); the six-command close-out in T038 matches quickstart's lint row.
- [x] CHK017 - Are the frozen-value prohibitions restated at the point of use? — **PASS**: wire fixture frozen in T003 ("load, never regenerate"); histories/goldens in the standing rules and re-invoked at T014/T035; budgets/backoff standing rule; T009 reuses `AGENT_ACTIVITY_CONFIG` and the 6-attempt budget as-is.

## Scope and Process Discipline

- [x] CHK018 - Does any task implement out-of-scope work (native zai provider, defects 6.2/6.3, pricing, budget retune)? — **PASS**: none; FR-013/FR-014 are a stated exclusion row; T037 files the judge/budget follow-ups as inbox tasks instead of doing them.
- [x] CHK019 - Does any task edit an attempt budget, backoff, captured history or golden? — **PASS**: standing rules forbid it; T023's conditional regeneration under `interfaces/` is a UI capability/type file gated by `scripts/check_ui.py`, not a replay history or golden — correct handling of a consequence the plan did not name.
- [x] CHK020 - Is the commit/reviewer discipline stated and compatible with the repo's rules? — **PASS**: per-task commit, `git commit -F`, no attribution trailers, per-task reviewer gate (standing rules 11-13).
- [x] CHK021 - Are the baseline (T002) and final (T038) runs comparable? — **PASS**: same tiers and commands, recorded in `baseline.md`, final counts must be >= baseline with no new failure.
- [x] CHK022 - Does the close-out enumerate the evidence the orchestrator needs? — **PASS**: T038 (counts vs baseline), T036 (docs), T037 (inbox tasks + source task marked done), phase checkpoints name the SCs they close.
- [x] CHK023 - Is each task specific enough to execute without further context? — **PASS**: contract and decision references throughout (T011→model-resolution contract; T016→validation contract table; T029→contract + D6; T032→D7a; T033→D7), exact lines and function names, T008's stub design, T025's cases a-g, T030's net-zero + SG-4 rule.
