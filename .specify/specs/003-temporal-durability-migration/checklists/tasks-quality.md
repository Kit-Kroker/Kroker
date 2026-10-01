# Checklist: Tasks Quality — 003 Temporal Durability Migration

**Purpose**: Unit tests for `tasks.md` — coverage of every FR/SC, task format, dependency/parallel correctness, TDD order, path validity, scope discipline, escalation rules. Not implementation tests.

**Created**: 2026-09-30

## Requirement Coverage

- [ ] CHK001 - Does every functional requirement FR-001..FR-021 map to at least one task that implements or verifies it? [Coverage, Spec §Requirements]
- [ ] CHK002 - Does every success criterion SC-001..SC-008 (incl. SC-006a) map to a closing task? [Coverage, Spec §Success Criteria]
- [ ] CHK003 - Does each FR-020 hypothesis (a)-(e) have both a proving task and a recorded-outcome step (T037)? [Coverage, Spec §FR-020, tasks T029-T032, T037]
- [ ] CHK004 - Is the FR-005.5a tool-bearing capture obligation complete — captured histories for BOTH `architect` and `research` — or is the research omission an unresolved deviation from a spec MUST? [Coverage, Conflict, Spec §FR-005.5a, tasks T005-T007]
- [ ] CHK005 - Is FR-021 (sandbox-module marking guard: "a test or lint guards this") tasked anywhere? [Gap, Spec §FR-021]
- [ ] CHK006 - Is FR-014's priced-usage verification clause ("unchanged priced-usage record in the temporal-tier run") tasked? [Gap, Spec §FR-014]
- [ ] CHK007 - Is FR-012 (optional roles stay optional; absent folder never breaks import/boot) covered by a named task or named existing tests that the runs execute? [Coverage, Spec §FR-012]

## Task Format

- [ ] CHK008 - Does every task line match the declared format `- [ ] Tnnn [P?] [US?] description with path`? [Clarity, tasks.md §Format]
- [ ] CHK009 - Are `[US]` tags consistent with the phase headers' story assignments (Phase 3=US2, Phase 4=US1, Phase 5=US3)? [Consistency]
- [ ] CHK010 - Are the self-reported counts accurate (44 tasks; parallel `[P]` marker count) against the file's actual markers? [Measurability, tasks.md §Counts]

## Ordering and Dependencies

- [ ] CHK011 - Is the Phase 1 commit-before-Phase 2 constraint enforced by an explicit stop task (T009) plus a dependency statement, not just prose? [Dependency, tasks.md §Dependencies]
- [ ] CHK012 - Does every TDD pair keep the failing-test task before its implementation task, with no implementation task lacking a guarding test? [Dependency, tasks.md §Tests]
- [ ] CHK013 - Do the dependency notes cover all same-file sequences (loader T015→T016, roles T017→T019, worker T020 after T019) and match the `[P]` markers and parallel examples? [Consistency, tasks.md §Dependencies, §Parallel examples]
- [ ] CHK014 - Is the run-order relationship between T010 (tests) and T011 (package + fixture registry they import) stated? [Dependency, tasks T010-T011]

## Paths and Executability

- [ ] CHK015 - Does every referenced file path exist on main or get created by an earlier task (fixtures, histories, `tests/durability/`, dumper)? [Completeness]
- [ ] CHK016 - Is every verification command a single pytest invocation scoped to the dev container, matching quickstart.md and the host-hazard rule? [Consistency, quickstart.md, tasks.md §Environment]
- [ ] CHK017 - Are frozen-value prohibitions (names, toolset ids, configs, never edit histories/goldens) restated at the point of use in the tasks that touch them (T013, T021, T025, T028, T034)? [Consistency]

## Scope and Process Discipline

- [ ] CHK018 - Does any task implement B2/C3/D1 out-of-scope work (model forwarding, SDK `max_retries` disabling, zai provider, defects 6.2/6.3)? [Consistency, Spec §Resolved Decisions]
- [ ] CHK019 - Is the STOP-and-escalate rule attached to every task that could observe a replay/payload/registration difference (T026, T029, T030, T031, T036)? [Completeness, tasks.md §Rules carried in]
- [ ] CHK020 - Is the executor no-commit rule compatible with the orchestrator-commit checkpoint — does any task ask the executor to commit? [Consistency, tasks.md §Environment, T009]
- [ ] CHK021 - Are the baseline (T002) and final (T042) runs comparable — same tiers, same commands, counts recorded in a named place? [Measurability]
- [ ] CHK022 - Does the closing report task (T044) enumerate all evidence the orchestrator needs (pass counts, FR-020 outcomes, residual risks, changed files)? [Completeness]
- [ ] CHK023 - Are tasks added after a review pass (non-sequential numbering, e.g. T045/T046) explained by a numbering note and given inline execution-order guidance? [Clarity, tasks.md §Numbering note]

## Re-review addendum (reviewer-003-4, 2026-09-30)

- CHK004 re-checked: research-history MUST handled as a proposed spec amendment (plan.md:106-108) with tasks following the proposal (T005 note, T033); acceptable pending the GATE 2 ruling.
- CHK005 re-checked: RESOLVED — T045 (FR-021 sandbox-module marking guard), Phase 3, before T023.
- CHK006 re-checked: RESOLVED — T046 (FR-014 priced-usage equality against pre-migration records), Phase 5, before T037.
- CHK010 re-checked: RESOLVED — counts corrected (46 tasks; 19 `[P]`), verified against the file.
- CHK014 re-checked: RESOLVED — T011-before-T010 run order stated (tasks.md:123).
