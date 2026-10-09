# Plan Checklist: Benchmark Scoring Output Rework (013)

Domain: plan. Generated at the reviewer plan gate (2026-10-10), base main
`35d1b056`. Each item tests the plan artifacts themselves (plan.md,
research.md, data-model.md, contracts/scoring-output.md, quickstart.md)
against the approved spec (incl. rulings R1 to R5 and amendments A1 to
A5) — completeness, clarity, consistency, measurability, coverage — not
the implementation.

## Requirement Completeness

- [ ] CHK001 - Is every functional requirement FR-001 to FR-049 mapped to at least one step of the plan's work order, and every step's named checks green before the next? [Completeness, Spec §FR-001–FR-049, plan Work order]
- [ ] CHK002 - Is every success criterion SC-001 to SC-012 given a proof in contract §13, and is each proof either a deterministic test, a stored-record assertion, or the quickstart §2 procedure, never an unsupported mixture? [Completeness, Spec §SC-001–SC-012, contract §13]
- [ ] CHK003 - Does the plan state, per new or changed output file (grid.\*, gate-oracle.\*, heatmap.\*, sc-rollup.\*, report.md), which writer writes it and which reader consumes it? [Completeness, contract §11.1, data-model §3–§6]
- [ ] CHK004 - Is the complete set of importers of every removed or reshaped name (`build_heatmap`, `HeatmapCell`, `Heatmap`, `ORACLE_STAGE`, `REWORK_OUTCOMES`, `_TABLE_HEADER`, `load_run_summaries`, `CANONICAL_STAGES`, the composite column) enumerated, including readers outside `src/sdlc/benchmarks/`? [Completeness, Gap, Spec §FR-012, §FR-047, research R-6, R-14]
- [ ] CHK005 - Are the run-status table (research R-2) and the arm-recovery order (R-3) each defined once, with the same body serving the 012 writer (`cell.py`) and the 013 reader (`runs.py`)? [Completeness, Spec §FR-002, §FR-006, research R-2, R-3]
- [ ] CHK006 - Are the two fields written by future runs (`capture_rev` on `SessionDigest` and `WasteBag`) specified on the writer side (`digest_of`, `from_digest`) and the reader side (`waste_measured`), with the stored-record boundary stated (no field of `BenchmarkRecord` changes)? [Completeness, Spec §FR-040, §FR-043, data-model §2, contract §10]
- [ ] CHK007 - Is the documentation obligation (FR-049) planned as a per-passage "now → change to" table with a find-by-text rule, rather than a general instruction? [Completeness, Spec §FR-049, plan Document changes]

## Requirement Clarity

- [ ] CHK008 - Is "the code stage finished", when derived, defined by the same observable signal the 012 writer uses (a post-code stage record), so derivation and recording cannot drift? [Clarity, Spec §FR-002, research R-2, contract §1.2]
- [ ] CHK009 - Are the run statuses total over (code finished, grading), with the `not_graded` → `lost` mapping and the `status_derived` marker specified for every input combination? [Clarity, Spec §FR-004, research R-2, contract §1.3, §1.7]
- [ ] CHK010 - Is "reached a stage" (the attrition denominator) defined by position in `CELL_STAGE_ORDER`, with the disabled-stage, per-task-loop and no-stage-record cases each named (amendment A3)? [Clarity, Spec §FR-014, research R-7, contract §3.2]
- [ ] CHK011 - Is a "wasted token" defined by exactly the three named rules (lost run, superseded attempt, never-passed task), each token counted once, with the handoff-record-without-attempt case covered (amendment A4)? [Clarity, Spec §FR-016, research R-7, contract §3.4]
- [ ] CHK012 - Is the pass/reject reading of every gate verdict (`pass`, `revise` on merge = pass, `revise` elsewhere = reject, `escalated`, `not_evaluated`) decided by one pure function with its evidence cited in code? [Clarity, Spec §FR-030, research R-9, data-model §1.2]
- [ ] CHK013 - Are the fixed colour steps stated as data (four bounds and a direction per layer), with grey, blank and step 0 three distinct appearances and the grey rule's observation unit named per layer? [Clarity, Spec §FR-018 to FR-021, research R-8, contract §4]

## Requirement Consistency

- [ ] CHK014 - Are the GATE 1 rulings R1 to R5 and the post-gate amendments A1 to A5 carried unchanged into plan, research, data-model and contract? [Consistency, Spec §Rulings, §Amendments, research R-2, R-7, R-9, R-15]
- [ ] CHK015 - Is the run-group key identical in research (R-4), data-model §1.1 (`Group`) and contract §1.8, including the harness component, so a two-harness case under one arm name never merges? [Consistency, Spec §FR-007, research R-4, contract §1.8]
- [ ] CHK016 - Do the plan's projected file sizes agree with the base line counts it cites, and does every projected size sit under the SG-3 stop-guard (800)? [Consistency, plan Constraints, Constitution Check]
- [ ] CHK017 - Is the "Not touched" list consistent with the design — no file named there imports a removed name, exports a changed symbol, or is otherwise forced to change? [Consistency, plan Project Structure, research R-6]
- [ ] CHK018 - Are the quickstart §2 expectations exactly the contract §12 figures, and is every §12 figure either recomputed on the stored records (recounted, not copied) or assigned to a deterministic test? [Consistency, contract §12, quickstart §2]
- [ ] CHK019 - Is `MIN_OBSERVATIONS` the single under-five threshold for grid headers, heatmap cells, gate rates and criteria, with `sc_rollup.MIN_RUNS` reduced to an alias of it? [Consistency, Spec §FR-020, §FR-032, §FR-039, research R-8, data-model §6]

## Acceptance Criteria Quality

- [ ] CHK020 - Is every §12 figure mechanically decidable from the score outputs alone (totals line, group headers, layer cells, gate rows, criteria line), with no judgement call? [Measurability, contract §12, quickstart §2]
- [ ] CHK021 - Is SC-012 (one case scored in under a minute) given a concrete measurement procedure (quickstart §2, timed, no service running)? [Measurability, Spec §SC-012, quickstart §2]
- [ ] CHK022 - Are the stop-guards SG-1 to SG-7 each tied to a falsifiable condition with a named escalation path (orchestrator), rather than to a feeling? [Measurability, plan Stop-guards]

## Scenario Coverage

- [ ] CHK023 - Does the plan give every spec edge case a named home (contract clause, view or test) — no-stage-record runs, finished-code-unfinished-pipeline runs, the pre-012 todo-api full-pass-oracle run, no-oracle cases, mixed-case selections, two-arm matrix runs, partial token coverage, drift records, empty selections, unknown stage names, attempt-less attempts, ASCII output? [Coverage, Spec §Edge Cases, contract §1–§4]
- [ ] CHK024 - Is the read-only rule (FR-043, SC-010) proven by a defined procedure (records fingerprint at baseline compared before every commit, `git ls-files runs/` empty, scores written outside `runs/`) rather than by assertion? [Coverage, plan rule 1, SG-5, quickstart §2]
- [ ] CHK025 - Does step 9b's negative branch (no captured stream by round's end) have a recorded outcome (FR-041 reported open, SG-4 forbidding a hand-written fixture as proof), so it cannot silently pass? [Coverage, Spec §FR-041, plan step 9b, SG-4]

## Edge Case Coverage

- [ ] CHK026 - Is a mixed-generation run (records of both kinds under one `run_id`) defined (contract §1.6), and a qa row that mixes copy and non-copy runs (§3.3, §5.5)? [Edge Case, Spec §FR-005, contract §1.6, §3.3]
- [ ] CHK027 - Are under-five and zero-denominator behaviour defined for every rate the round shows — heatmap cells (§4.2), gate rates (§6.4), group figures (§1.8), success criteria (§9.4) — with the same reading (`n/a`, grey, value printed)? [Edge Case, Spec §FR-020, §FR-032, §FR-039]

## Dependencies & Assumptions

- [ ] CHK028 - Is every tree claim the design rests on either verified before acceptance or listed as a step-0 "Verify" item with a stop-guard behind it? [Assumption, research Verify lines, plan step 0, SG-2]
- [ ] CHK029 - Are the environment assumptions (kroker-dev container binding, stored records visible at `runs/benchmarks`, git on the host, scores outside `runs/`) each tied to a check rather than left as prose? [Assumption, quickstart §Prerequisites, plan step 0]
- [ ] CHK030 - Does the plan record its departures from advisor/skeptic recommendations with a reason, so no rejected recommendation reads as an oversight? [Dependency, research Consult log]

## Ambiguities & Conflicts

- [ ] CHK031 - Is the scope boundary against report 2.9 and Phases 3–4 stated as an explicit exclusion list, with the two record-based view exceptions (task/error matrices, reviewer-versus-adversary) named in the plan's rules? [Ambiguity, Spec §Out of Scope, plan rule 2, Follow-ups]
- [ ] CHK032 - Where the plan asserts a negative ("nothing outside tests reads the heatmap JSON content", "no stored case has two arms", "no reader of `## Cells` outside the package"), is the assertion checkable and scoped, with the step-0 grep behind it? [Ambiguity, plan Risks, research R-6, R-14]
