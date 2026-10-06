# Tasks Checklist: Benchmark Record Trustworthiness (012)

Domain: tasks. Generated at the reviewer tasks gate (2026-10-07), base main
`7f5191d0`, against tasks.md T001–T024 and the approved plan, research,
data-model, contract and quickstart. Items test the task list as a
requirements artifact — coverage, executability, ordering, verifiability —
not the implementation.

## Requirement Completeness

- [ ] CHK001 - Does every FR-001 to FR-030 and SC-001 to SC-009 appear in the requirement-coverage table with at least one task? [Completeness, Spec §FR/SC, tasks Requirement coverage]
- [ ] CHK002 - Does every contract clause §1.1 to §7.9 have a task that implements it and a task that tests it? [Completeness, contract §1–§7]
- [ ] CHK003 - Does every plan work-order step (0 to 11) map to at least one task, in the plan's order? [Completeness, plan Work order, tasks Phase order]
- [ ] CHK004 - Is every test file named in contract §8 created or edited by exactly the task that needs it? [Completeness, contract §8]
- [ ] CHK005 - Are the document and clause obligations (FR-030, plan Document changes) distributed to the tasks whose behaviour they describe? [Completeness, Spec §FR-030]
- [ ] CHK006 - Are the step-0 verify items (R-4, R-5, R-7, R-9, R-6) all present in T001 with a recorded outcome? [Completeness, research Verify lines]

## Requirement Clarity (executability)

- [ ] CHK007 - Does each task name every file it edits and every test it writes, such that nothing must be located by searching? [Clarity, tasks T002–T024]
- [ ] CHK008 - Where a task has an "if X then … else …" (T013 harness, T016 timeout, T021 answer branches, T014 reachability), is each branch a concrete procedure? [Clarity, tasks T013, T014, T016, T021]
- [ ] CHK009 - Are expected values stated, not implied (message formats, enum values, sentinel strings, the 997-line budget, the 500-char truncation)? [Clarity, contract §1.2, data-model §1.2]
- [ ] CHK010 - Is each RED test's failure reason stated so the executor can recognise it, and each PIN's first-run-green property plausible at base? [Clarity, tasks Tests preamble, SG-8]
- [ ] CHK011 - Does every tree claim a task makes (file, line, function, existing test, activity registration site) check out at the base commit? [Clarity, tasks T003–T020]

## Requirement Consistency

- [ ] CHK012 - Do tasks use only names data-model defines, with signatures that agree with it? [Consistency, data-model §2, plan rule 4]
- [ ] CHK013 - Does each task's stated behaviour match the contract clause it cites, with no task contracting a clause another task contradicts? [Consistency, contract §1–§7]
- [ ] CHK014 - Do counts agree across plan and tasks (new modules, new test files, modified files)? [Consistency, plan Scale/Scope, tasks]
- [ ] CHK015 - Are the commands a task tells the executor to run actually correct for the CLI they invoke? [Consistency, tasks T023, T024, quickstart §2–§3]

## Ordering and Dependencies

- [ ] CHK016 - Does any task consume a name, field or behaviour an earlier task has not delivered? [Coverage, tasks Dependencies]
- [ ] CHK017 - Can each task's single commit be green on its own (RED test + code together, PINs passing at base)? [Coverage, tasks Tests preamble]
- [ ] CHK018 - Are the orchestrator waits (T019→T021, pre-T024) enforced by a stop-guard and the reviewer gate? [Coverage, SG-5, SG-7]

## Scenario and Edge Coverage

- [ ] CHK019 - Do tasks cover the spec's edge cases (kill from outside, oracle build failure, empty rubric file, no-rubric case, pre-012 readers, uncommitted tree, mixed models, multi-attempt timing)? [Coverage, Spec §Edge Cases, contract §3–§7]
- [ ] CHK020 - Is each contract §3 table row exercised by a named test in T012 or T013? [Coverage, contract §3]
- [ ] CHK021 - Are both the fast/seam path and the slow/real path specified where the plan demands a seam (oracle environment)? [Coverage, research R-6, contract §4]

## Verifiability

- [ ] CHK022 - Is each stop-guard fireable in principle, and does any fire spuriously on the happy path? [Measurability, tasks SG-1–SG-9]
- [ ] CHK023 - Are the checkpoints per phase objectively checkable (files exist, counts, green suites)? [Measurability, tasks Checkpoints]
- [ ] CHK024 - Is every diagnosis/evidence task's evidence source verifiably present on this checkout? [Measurability, tasks T014, T019]

## Standing Rules and Boundaries

- [ ] CHK025 - Does any task need to edit a forbidden path, and is every forbidden-path entry consistent with what the tasks must edit? [Consistency, tasks Standing rules]
- [ ] CHK026 - Are the read-only guarantees on `runs/` enforced by a check that can actually detect a violation? [Measurability, tasks Standing rules, SG-6]
- [ ] CHK027 - Do tier-marked tests (slow, temporal) run in the environment the tasks assume (network, container, time)? [Assumption, tasks T013, T016]

## Format

- [ ] CHK028 - Does every task have a checkbox, a stable id, a story label (or explicit none) and explicit file paths? [Clarity, tasks T001–T024]
- [ ] CHK029 - Is the requirement-coverage table consistent with the per-phase story labels? [Consistency, tasks Phase order + Requirement coverage]
- [ ] CHK030 - Are RED/PIN markers present wherever an existing behaviour is pinned or a new one is demanded, and is the PIN set exactly the behaviours that exist at base? [Clarity, tasks T002, T008, T011, T018]
