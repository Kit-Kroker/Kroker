# Plan Checklist: Benchmark Record Trustworthiness (012)

Domain: plan. Generated at the reviewer plan gate (2026-10-06), base main
`7f5191d0`. Each item tests the plan artifacts themselves (plan.md,
research.md, data-model.md, contracts/records-and-harness.md,
quickstart.md) against the approved spec — completeness, clarity,
consistency, measurability, coverage — not the implementation.

## Requirement Completeness

- [ ] CHK001 - Is every functional requirement FR-001 to FR-030 mapped to at least one implementation step in the plan's work order? [Completeness, Spec §FR-001–FR-030, plan Work order]
- [ ] CHK002 - Is every success criterion SC-001 to SC-009 given a proof in contract §8, and is each proof either a deterministic test or the smoke run, never an unsupported mixture? [Completeness, Spec §SC-001–SC-009, contract §8]
- [ ] CHK003 - Does the plan state, per new/changed record field, which writer sets it and which reader consumes it? [Completeness, data-model §1–§2, contract §2, §7]
- [ ] CHK004 - Is the complete set of readers of `record.model`, `record.harness`, the outcome value and the cell file name enumerated anywhere in the plan, including readers outside `src/sdlc/benchmarks/`? [Completeness, Gap, Spec §FR-017, §FR-025]
- [ ] CHK005 - Are all five case-file derivations named in research R-1 accounted for, and does the plan distinguish cases-location derivations from other `parents[3]` repo-root derivations that must not move? [Completeness, Spec §FR-001, research R-1]
- [ ] CHK006 - Does the plan name every benchmark-record writer (stage steps, lenses, tool approval, oracle, drift) and state the provenance/prompt-hash treatment of each, including writers outside benchmark runs? [Completeness, Spec §FR-014–FR-016, research R-7]
- [ ] CHK007 - Is the documentation obligation (FR-030) planned as an exhaustive table with a per-file "now → change to" delta, rather than a general instruction? [Completeness, Spec §FR-030, plan Document changes]

## Requirement Clarity

- [ ] CHK008 - Is "the code stage finished" defined by an observable, testable signal (a post-code stage record) rather than by control-flow narration? [Clarity, Spec §FR-007, contract §3.1]
- [ ] CHK009 - Are the four grading statuses (`graded`, `not_graded`, `grading_failed`, `no_oracle`) defined by a total function over (has oracle, code finished, oracle result), with no input combination unassigned? [Clarity, Spec §FR-006–FR-009, contract §3]
- [ ] CHK010 - Is the provenance tri-state (commit id / `unknown` / pre-012 `None`) specified on both the writer side (never `None` from a 012 writer) and the reader side (`is_pre012`)? [Clarity, Spec §FR-014, §FR-016, contract §2.1, §7.2]
- [ ] CHK011 - Are the two `prompt_sha` sentinels (`none:deterministic`, `none:no-registry-prompt`) defined so that every record writer's value is determined without case-by-case judgement? [Clarity, Spec §FR-015, contract §2.5]
- [ ] CHK012 - Is the "not evaluated" evidence standard operational — who writes `gate-diagnosis.md`, what it must contain, and which rule decides repair versus not-evaluated per gate — before any gate code is written? [Clarity, Spec §FR-023–FR-025, research R-10, contract §6.5]
- [ ] CHK013 - Does the plan state the retry semantics of the new failing activity (`load_case_assets`) under the existing retry policy, so "non-retryable" is a mechanism rather than an adjective? [Clarity, contract §1.4, data-model §2.1]

## Requirement Consistency

- [ ] CHK014 - Are the spec's GATE 1 rulings R1 (arm label), R2 (per-gate decision) and R3 (pre-012 untouched) carried unchanged into plan, research, data-model and contract? [Consistency, Spec §Rulings, research R-8, R-10, R-11]
- [ ] CHK015 - Is the post-GATE-1 amendment of the graded line (integration-branch wording → code-stage-finished) applied consistently across spec FR-007, research R-4 and contract §3.1? [Consistency, Spec §FR-007, research R-4]
- [ ] CHK016 - Do the plan's line-count expectations for `S/code/step.py` agree across plan Constraints and research R-9, and does every projected file size sit under the 1000-line ceiling with a stop-guard? [Consistency, plan Constraints, research R-9, SG-3]
- [ ] CHK017 - Is the "Not touched" list consistent with the design (no change required in any file named there), and is any tension between "not touched" and behaviour change explicitly resolved? [Consistency, plan Project Structure]
- [ ] CHK018 - Are the smoke-run claims (quickstart §3) exactly the subset R-12 says a green todo-api run can show, with every negative-path criterion assigned to a deterministic test? [Consistency, Spec §FR-028–FR-029, research R-12, quickstart §3–§4]

## Acceptance Criteria Quality

- [ ] CHK019 - Is each smoke-run check in quickstart §3 mechanically decidable from the run directory alone (file count, field presence, ordering), with no judgement call? [Measurability, quickstart §3]
- [ ] CHK020 - Is SC-005 ("empty tree scores 0 in 100% of repeated trials") given a concrete repetition count or bounded procedure in the proof, so "100%" is checkable? [Measurability, Spec §SC-005, contract §4.5–§4.6]
- [ ] CHK021 - Is SC-006's "more than measurement noise" made concrete (e.g. the §5.4 ordering plus strict containment) wherever it is checked? [Measurability, Spec §SC-006, contract §5.4]
- [ ] CHK022 - Are the stop-guards (SG-1 to SG-8) each tied to a falsifiable condition with a named escalation path (orchestrator), rather than to a feeling? [Measurability, plan Stop-guards]

## Scenario Coverage

- [ ] CHK023 - Does the plan cover every spec edge case (kill from outside, oracle build failure, empty rubric file, no-rubric case, pre-012 readers, uncommitted tree, mixed models per cell, multi-attempt timing) with a named home (task, contract clause or test)? [Coverage, Spec §Edge Cases]
- [ ] CHK024 - Is the non-benchmark invariance requirement (rule 2 / FR-026) proven by a defined baseline procedure (step 0) rather than by assertion? [Coverage, plan Work order step 0, quickstart §1]
- [ ] CHK025 - Does the plan cover the F3 reproduction's negative branch (not reproduced) with an explicit recorded outcome, so FR-010 cannot silently pass? [Coverage, Spec §FR-010, research R-6]

## Edge Case Coverage

- [ ] CHK026 - Are readers specified for mixed directories (a case with both pre-012 and 012 records, plus non-benchmark `_production` drift records) so no aggregate mixes kinds and no post-012 record is mislabelled pre-012? [Edge Case, Spec §FR-027, research R-11, contract §7]
- [ ] CHK027 - Is the behaviour when `summarize_cell` finds no records at all (cell died before its first record) defined — status, `last_stage`, file? [Edge Case, contract §3.2, data-model §2.4]

## Dependencies & Assumptions

- [ ] CHK028 - Is every tree claim the design rests on either verified in the review or listed as a step-0 "Verify" item with a stop-guard behind it? [Assumption, research "What the tree shows" + Verify lines, SG-2]
- [ ] CHK029 - Are the assumptions about the runtime environment (worker cannot read git; container binding; scratch repo state; `SDLC_CASES_ROOT` in the image) each tied to a mechanism (env var, Dockerfile arg, runbook step) rather than left as prose? [Assumption, quickstart §Prerequisites, research R-6, R-7]
- [ ] CHK030 - Does the plan record its departures from advisor/skeptic recommendations with a reason, so no rejected recommendation reads as an oversight? [Dependency, research Consult log]

## Ambiguities & Conflicts

- [ ] CHK031 - Is the scope boundary against report Phases 2–4 stated as an explicit exclusion list, with any item that could be read as Phase 2 work justified as Phase 1? [Ambiguity, Spec §Out of Scope, plan R-13]
- [ ] CHK032 - Where the plan asserts a negative ("no reader outside the package", "no replay history", "corpus is clean"), is the assertion checkable and scoped, so one counterexample does not invalidate a design decision silently? [Ambiguity, plan Constitution Check, GATE 2]
