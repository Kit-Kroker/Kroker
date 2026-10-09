# Tasks Checklist: Benchmark Scoring Output Rework (013)

Domain: tasks. Generated at the reviewer tasks gate (2026-10-10), base main
`35d1b056`, against tasks.md T001-T017 and the approved spec, plan,
research, data-model, contract and quickstart. Items test the task list
as a requirements artifact — coverage, executability, ordering,
verifiability — not the implementation.

## Requirement Completeness

- [ ] CHK001 - Does every FR-001 to FR-049 and SC-001 to SC-012 appear in the requirement-coverage table with at least one task? [Completeness, Spec §FR/SC, tasks Requirement coverage]
- [ ] CHK002 - Is every contract clause §1.1 to §11.6 named by some task's RED list, or — for the negative clauses (§10.5, §11.6) — pinned by a named PIN? [Completeness, contract §1-§11]
- [ ] CHK003 - Does every plan work-order step (0 to 11) map to at least one task, in the plan's order, with the phase table's commit counts matching the task count? [Completeness, plan Work order, tasks Phase order]
- [ ] CHK004 - Is every test file contract §13 names created or edited by exactly the task that needs it, and does no file's edit wander into a task that does not own the behaviour? [Completeness, contract §13, plan Existing tests changed]
- [ ] CHK005 - Do the T001 Verify items (a) to (i) cover every research "Verify" line (R-2, R-3, R-15) and the plan's step-0 greps, each with a recorded outcome? [Completeness, research Verify lines, plan step 0]
- [ ] CHK006 - Is the documents obligation (FR-049) one task with find-by-text passages per the plan's table, run before the final gates? [Completeness, Spec §FR-049, tasks T016]

## Requirement Clarity (executability)

- [ ] CHK007 - Does each task name its test file(s), its RED cases, every source file it edits, and end in one commit whose contents are enumerated? [Clarity, tasks T002-T015]
- [ ] CHK008 - Where a task branches (T015 no stream; T001 main moved; T008 e36 conditional), is each branch a concrete procedure with a recorded outcome? [Clarity, tasks T001, T008, T015]
- [ ] CHK009 - Are expected values stated, not implied — §12 figures, grid header cells, the agreement title string, `step_for` edge values, the §7.2 one-line reason format? [Clarity, contract §2.5, §4.1, §7.2, §12]
- [ ] CHK010 - Is each RED test's failure reason recognisable, and each PIN's first-run-green property plausible at the commit it runs? [Clarity, tasks Tests preamble, SG-6]
- [ ] CHK011 - Does every tree claim a task makes (workflow.py:308, merge/step.py:654, crew/activities.py:349, verdict.py:226, `capture_session`, `dispatch_experiment_compare`, named test files) check out at the base commit? [Clarity, tasks T001, T008, T012, T014]

## Requirement Consistency

- [ ] CHK012 - Do tasks use only names data-model defines (including `BenchmarkSummary.qa_is_copy`), with signatures that agree with it? [Consistency, data-model §1-§6, tasks Standing rules]
- [ ] CHK013 - Does each task's stated behaviour match the clause it cites, with no task contracting what another task contradicts? [Consistency, contract §1-§11, tasks T002-T015]
- [ ] CHK014 - Do counts agree across plan and tasks — 17 tasks, per-phase commit counts, 4 new source modules, the new test files, the written-during-execution files? [Consistency, plan Scale/Scope, tasks Phase order]
- [ ] CHK015 - Are the commands a task tells the executor to run correct for the CLI as it exists (score flags, experiment compare, check scripts, the fingerprint one-liner)? [Consistency, tasks Standing rules, T001, T013, T017]

## Ordering and Dependencies

- [ ] CHK016 - Does any task consume a name, field or behaviour an earlier task has not delivered (grid and gate-oracle into T011; heatmap and sc-rollup into T012; runs into T007)? [Coverage, tasks Dependencies]
- [ ] CHK017 - Can each task's single commit be green on its own — in particular the row re-keying (T004/T005) against `test_benchmark_report.py` and `test_benchmark_experiments.py`, the two-step heatmap swap (T007 keeps the old model, T008 removes it), and the report rewrite (T011) against the writer that composes it (T012)? [Coverage, tasks T004-T008, T011-T012]
- [ ] CHK018 - Is the orchestrator wait (T015's captured stream) enforced by a stop-guard and the reviewer gate, with the no-stream branch recorded? [Coverage, SG-4, tasks T015]

## Scenario and Edge Coverage

- [ ] CHK019 - Is each spec edge case exercised by a named RED — no stage record, code finished but pipeline not, oracle record on a lost run, no-oracle case, mixed-case selection, unknown stage name, attempt without number, ASCII output, empty selection? [Coverage, Spec §Edge Cases, tasks T003, T006, T007, T011]
- [ ] CHK020 - Is every §2.4 mark-table row exercised by T006's RED, including merge `revise` as `first` and qa `copy`? [Coverage, contract §2.4, tasks T006]
- [ ] CHK021 - Are under-five and zero-denominator behaviour exercised for group figures (T003/T006), heatmap cells (T007/T008), gate rates (T009) and criteria (T010)? [Coverage, contract §1.8, §4.2, §6.4, §9.4]

## Verifiability

- [ ] CHK022 - Is each stop-guard fireable in principle, and does each cite the right task ids (SG-4 → T015, SG-6 → T017)? [Measurability, tasks Stop-guards]
- [ ] CHK023 - Are the per-phase checkpoints objectively checkable (files exist, counts, named suites green)? [Measurability, tasks Checkpoints]
- [ ] CHK024 - Are the Stored test's per-task assertions exactly contract §12's rows (T003 run-level, T007 attrition, T009 gates, T010 summaries)? [Measurability, contract §12, tasks T003, T007, T009, T010]

## Standing Rules and Boundaries

- [ ] CHK025 - Does any task need to edit a forbidden path, and is every forbidden-path entry consistent with what the tasks must edit (eval/verdict.py and agreement_matrix.py are not forbidden — are they used as such)? [Consistency, tasks Standing rules, T008, T009]
- [ ] CHK026 - Is the read-only guarantee on `runs/` enforced by a check that detects a violation (fingerprint re-run before every commit, `git ls-files runs/`, `--out` outside runs/)? [Measurability, tasks Standing rules, SG-5]
- [ ] CHK027 - Does the "must pass unedited" list contradict no task, and does every assertion it cites exist at base? [Consistency, tasks Standing rules, T002, T015]

## Format

- [ ] CHK028 - Does every task have a checkbox, a stable id, a story label (or explicit none) and explicit file paths? [Clarity, tasks T001-T017]
- [ ] CHK029 - Is the requirement-coverage table consistent with the per-phase story labels and the spec's priorities? [Consistency, tasks Phase order + Requirement coverage]
- [ ] CHK030 - Are RED/PIN markers present wherever an existing behaviour is pinned or a new one demanded, and is the PIN set exactly the behaviours that exist at base? [Clarity, tasks T002, T007, T010, T012, T015]
