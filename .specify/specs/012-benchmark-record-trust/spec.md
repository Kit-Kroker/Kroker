# Feature Specification: Benchmark Record Trustworthiness

**Feature Branch**: `012-benchmark-record-trust`

**Created**: 2026-10-06

**Status**: Approved (GATE 1, 2026-10-06)

**Input**: User description: "Round 012, Phase 1 only of `docs/reports/2026-10-06-benchmark-improvement-plan.md`: make the records the benchmark harness writes trustworthy before any new benchmark runs are allowed — rubric scores actually collected, aborted cells recorded as not graded, per-grade isolated oracle environment, real provenance (Kroker commit and prompt hashes on every record), one cell label shared by oracle and code records, real qa/review timings and verdicts, analyze/merge gates repaired or disabled in benchmark mode, plan-stage rubric key fixed."

## Context

An audit of all 1,249 stored benchmark records (report §1, findings F1–F15)
found that the records cannot support any conclusion: rubric scores are
absent, aborted runs count as quality zero, timings and verdicts of some
stages are copies of others, and no record says which Kroker commit or
which prompts produced it. The report mandates that no new benchmark runs
land until the records are trustworthy.

This round delivers Phase 1 of the report's plan (tasks 1.1–1.8) and
nothing else. The reader of a benchmark record — the person comparing two
arms, or a later round's scoring output — is the user of this feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Rubric scores are collected or the cell fails loudly (Priority: P1)

The benchmark operator launches a case that registers rubrics for its
judged stages. Every record for a judged stage carries the rubric score
the judge gave. If a registered rubric or veto file cannot be found, the
cell fails with a message naming the missing file, rather than completing
with silently unjudged stages.

**Why this priority**: 0 of 418 rubric-eligible records carry a score.
Without this, the judged-stage quality axis does not exist, and the round's
exit criterion cannot be met.

**Independent Test**: Run a case with registered rubrics in the same
environment the benchmark worker runs in and confirm judged-stage records
carry scores; then remove one registered rubric file and confirm the cell
fails naming that file.

**Acceptance Scenarios**:

1. **Given** a case whose manifest registers rubrics for clarify and architecture, **When** the cell runs in the worker environment, **Then** the clarify and architecture records each carry a rubric score.
2. **Given** a case manifest that registers a rubric file which does not exist, **When** the cell starts, **Then** the cell fails before spending model budget and the failure names the stage and the missing file.
3. **Given** a case manifest that registers a veto file which does not exist, **When** the cell starts, **Then** the cell fails in the same way.
4. **Given** the cases location is overridden for the environment, **When** the judge, the report, the calibration reader and the case-config loaders resolve case files, **Then** all of them resolve against the same overridden location as the oracle does.
5. **Given** a record for the plan stage and a calibration report for the planner rubric, **When** the trust value for that record's stage is looked up, **Then** the planner rubric's value is returned (not "no rubric").

---

### User Story 2 - An aborted cell is recorded as not graded (Priority: P1)

A cell stops before it produces code (for example in research or clarify).
Its record states that the cell did not complete, names the last stage it
reached, and carries no quality score. Aggregates over graded cells do not
include it; it is counted separately as an incomplete cell.

**Why this priority**: 8 of 18 cat-cafe runs stopped early and were graded
anyway; 7 scored 0.0, pulling the reported mean from 0.71 to 0.421. A
pipeline abort and a wrong implementation are different facts.

**Independent Test**: Force a cell to stop in an early stage and inspect
its records and the cross-run report.

**Acceptance Scenarios**:

1. **Given** a cell that stops before its code stage finishes, **When** the cell ends, **Then** it is recorded as not graded: no oracle score exists for it, it is flagged incomplete, and the record names the last stage reached.
2. **Given** a mix of completed and incomplete cells, **When** the cross-run report computes the oracle mean, **Then** incomplete cells are excluded from the mean and reported as a separate count.
3. **Given** a cell that completes and whose implementation fails every oracle test, **When** the cell ends, **Then** it is recorded as graded with score 0.0 (a real zero stays a zero).
4. **Given** an incomplete cell, **When** its record is read, **Then** it is not labelled with an unrelated integrity error (such as "language mismatch") as the only signal of the abort.

---

### User Story 3 - Each grade runs in its own clean environment (Priority: P1)

The oracle grades one run. Nothing left behind by any earlier grade —
files, installed packages, caches, running processes — can influence the
result. An integration result with no produced code cannot pass any test.

**Why this priority**: one aborted run scored 6 of 12 on a tree holding
only the init commit, matching the score of the run that finished a minute
earlier (F3). A grade that can leak between runs invalidates every score.

**Independent Test**: Grade a run that passes tests, then immediately
grade an empty-tree run of the same case, and confirm the second scores
zero tests passed.

**Acceptance Scenarios**:

1. **Given** the conditions of the audited empty-tree result, **When** the investigation runs, **Then** its outcome (reproduced with cause, or not reproduced with what was tried) is written down in the round's records.
2. **Given** a grade of a passing run has just finished, **When** an empty-tree run of the same case is graded next, **Then** no oracle test passes for the empty tree.
3. **Given** two grades of the same integration result, **When** they run back to back, **Then** they return the same passed/total counts.
4. **Given** a grade ends (success, failure or timeout), **When** the next grade starts, **Then** no process, file or installed package from the earlier grade is visible to it.

---

### User Story 4 - Every record says what produced it (Priority: P2)

Someone reading a record months later can tell which Kroker commit ran the
pipeline and which prompt content each role was given, and can therefore
group runs by commit and tell a prompt change from noise.

**Why this priority**: the ten graded cat-cafe runs span three days during
which three features landed; none of the records says which code produced
it. Comparison across commits is impossible without this, but it does not
block collecting correct scores.

**Independent Test**: Run a cell and check every record it wrote for a
commit identifier and a non-empty prompt hash where a prompt applies.

**Acceptance Scenarios**:

1. **Given** a benchmark run, **When** any record is written (stage, task, oracle, oracle-task), **Then** it carries the identifier of the Kroker commit that ran it.
2. **Given** the Kroker tree had uncommitted changes when the run started, **When** records are written, **Then** they say so (the commit alone is not presented as the full provenance).
3. **Given** a record produced by a role that was given a prompt, **When** the record is written, **Then** its prompt hash is derived from the prompt content that role actually received, and two runs with identical prompt content yield the same hash.
4. **Given** the prompt content of one role changes between two runs, **When** their records are compared, **Then** that role's prompt hash differs and other roles' hashes do not.
5. **Given** the commit cannot be determined, **When** the run starts, **Then** the run records provenance as explicitly unknown rather than empty.

---

### User Story 5 - One label per cell (Priority: P2)

All records of one cell — stage records, code records, oracle records —
carry the same cell label, so they land in one file and one report row.

**Why this priority**: today oracle records carry the arm name and code
records the model id, producing two files and two report rows per cell and
forcing every reader to join them by hand.

**Independent Test**: Run one cell and count the record files and report
rows it produces.

**Acceptance Scenarios**:

1. **Given** one cell, **When** it finishes, **Then** every record it wrote carries the identical cell label.
2. **Given** one cell, **When** its records are stored and reported, **Then** they form one file and one report row.
3. **Given** a record, **When** it is read, **Then** the model that actually did the work for that record is still recoverable (the shared label does not erase per-role model identity).

---

### User Story 6 - qa and review report their own time, verdict and spend (Priority: P2)

The qa record's wall-clock covers only the qa work, the review record's
only the review work; neither is a copy of the code attempt's. Each carries
the verdict its own role reached. The review record carries the tokens the
review consumed.

**Why this priority**: all 297 code/review pairs differ by under a second,
qa's outcome is copied from code's, and review records have no tokens.
Per-stage speed and cost attribution is the thing Kroker's benchmark
offers that external benchmarks do not; it must be real.

**Independent Test**: Run a task where the code attempt, qa and review
take visibly different times and reach different verdicts, and compare the
three records.

**Acceptance Scenarios**:

1. **Given** a task attempt where coding takes much longer than qa, **When** the records are written, **Then** the qa record's start is the moment qa began and its wall-clock is shorter than the code record's.
2. **Given** a task attempt, **When** the review record is written, **Then** its start and end bracket the review work only.
3. **Given** qa passes and the reviewer rejects, **When** the records are written, **Then** the qa record says pass and the review record says fail (each role's own verdict).
4. **Given** a review that consumed model tokens, **When** its record is written, **Then** the record carries those tokens.
5. **Given** a review or qa lens is disabled for the run, **When** records are written, **Then** no record claims a timing or verdict for work that did not happen.

---

### User Story 7 - Analyze and merge gates do not reject every benchmark run (Priority: P3)

A benchmark run whose implementation passes the oracle is not rejected by
the analyze and merge gates for reasons that only exist because it is a
benchmark run. Where a gate cannot be meaningful in benchmark mode, its
record says it was not evaluated instead of reporting a failure.

**Why this priority**: 14 of 14 runs on the two oracle cases are rejected,
including four that scored 6 of 6. The gate records are noise today, but
they do not corrupt the other measurements.

**Independent Test**: Run the todo-api case to a full oracle pass and read
the analyze and merge records.

**Acceptance Scenarios**:

1. **Given** the reason the gates reject every benchmark run has been identified, **When** the round closes, **Then** that reason is written down per gate.
2. **Given** a benchmark run whose implementation passes the oracle, **When** the analyze and merge stages finish, **Then** neither record reports a rejection caused by benchmark-mode conditions (for example the absence of a remote).
3. **Given** a gate is not evaluated in benchmark mode, **When** its record is written, **Then** the record says "not evaluated" with the reason, and is not counted as a pass or a fail.
4. **Given** a non-benchmark pipeline run, **When** it reaches analyze and merge, **Then** gate behaviour is unchanged.

---

### Edge Cases

- A cell fails after its code stage finished but before the pipeline finished (for example in merge): it is graded; the record still names the last stage reached and is flagged as not finished.
- A cell dies part-way through the code stage with some tasks integrated: the code stage did not finish, so it is not graded.
- A cell's code stage finishes but produced no change against the base: it is graded, with zero tests passed.
- A cell is killed from outside (worker restart, cancellation): its records must not present it as graded-zero.
- The oracle itself cannot run (environment build failure, timeout): recorded as a grading failure, distinct from both "not graded because aborted" and "graded zero".
- A rubric file exists but is empty: treated as missing.
- A case registers no rubrics at all: no failure; judged stages are recorded as having no rubric.
- Records written before this round lack the new fields: readers must keep loading them and must not present absent provenance as a real value.
- The run starts from a tree with uncommitted changes, or from an install with no repository metadata.
- Two roles in one cell use different models: the shared cell label must still be one label.
- A task has several attempts: each attempt's qa and review records carry that attempt's own timing.

## Requirements *(mandatory)*

### Functional Requirements

**Rubric collection (report 1.1, 1.8 — F1, F15)**

- **FR-001**: Every reader of case files — the judge's rubric loader, the report, the calibration reader and the case-config loaders — MUST resolve the cases location the same way the oracle does, honouring the environment's override.
- **FR-002**: A rubric or veto file registered in a case manifest that is missing or empty MUST fail the cell, naming the stage and the file. The failure MUST occur before the cell spends model budget.
- **FR-003**: For every stage with a registered, present rubric, the stage's record MUST carry the judge's score.
- **FR-004**: The plan stage MUST map to its rubric key under the stage name records actually use, so its trust value is shown.
- **FR-005**: The stage-to-rubric mapping MUST be checked against the stage names records use, so a renamed stage cannot silently lose its mapping again.

**Not-graded cells (report 1.2 — F2)**

- **FR-006**: Each cell MUST record whether it completed and the last stage it reached.
- **FR-007**: A cell whose code stage did not finish MUST be recorded as not graded: no quality score, incomplete flag set. The oracle MUST NOT assign it a score. The existence of an integration branch is not evidence that the code stage finished.
- **FR-008**: Aggregates of oracle quality MUST exclude not-graded cells and MUST report their count separately.
- **FR-009**: A grading failure (the oracle could not run) MUST be distinguishable in the record from both a not-graded cell and a graded zero.

**Oracle isolation (report 1.3 — F3)**

- **FR-010**: The round MUST attempt to reproduce the audited empty-tree 6-of-12 result and record the outcome and, if found, the cause.
- **FR-011**: Each grade MUST run in an environment created for that grade and destroyed after it; only the integration result under test and the case's held-out oracle may enter it.
- **FR-012**: No state from one grade (files, installed packages, caches, processes) may be visible to another grade.
- **FR-013**: An integration result containing no produced code MUST score zero tests passed.

**Provenance (report 1.4 — F10)**

- **FR-014**: Every record MUST carry the identifier of the Kroker commit that ran the pipeline, and whether the tree had uncommitted changes.
- **FR-015**: Every record produced by a prompted role MUST carry a hash of the prompt content that role received; the hash MUST be stable for identical content and MUST change when the content changes.
- **FR-016**: Provenance that cannot be determined MUST be recorded as explicitly unknown, never as an empty value indistinguishable from "not recorded".

**Cell label (report 1.5 — F11)**

- **FR-017**: All records of one cell MUST carry one identical cell label, producing one stored file and one report row per cell. The canonical cell label is the arm name (ruling R1): a cell is a case under an arm.
- **FR-018**: The model that performed the work of a record MUST remain recoverable from the record.

**qa and review (report 1.6 — F4, F5 review part, F7 qa part)**

- **FR-019**: The qa record's timing MUST cover the qa work only; the review record's timing MUST cover the review work only.
- **FR-020**: The qa record's outcome MUST be the qa role's own verdict; the review record's outcome MUST be the reviewer's own verdict.
- **FR-021**: The review record MUST carry the tokens the review consumed.
- **FR-022**: No record may be written with timing or verdict for a role that did not run.

**Gates in benchmark mode (report 1.7 — F8)**

- **FR-023**: The round MUST identify and record why the analyze and merge gates reject every benchmark run.
- **FR-024**: In benchmark mode the analyze and merge gates MUST NOT reject a run for a condition that exists only because it is a benchmark run. Repair versus "not evaluated" is decided per gate after the FR-023 diagnosis (ruling R2): a gate that depends on something a benchmark run cannot have is recorded as not evaluated (FR-025); any other gate is repaired.
- **FR-025**: A gate not evaluated in benchmark mode MUST be recorded as not evaluated, with its reason, and counted as neither pass nor fail.
- **FR-026**: Gate behaviour outside benchmark mode MUST NOT change.

**Compatibility and validation**

- **FR-027**: Records written before this round MUST remain loadable; absent new fields MUST read as "not recorded". The existing 1,249 records stay untouched on disk (ruling R3); reports MUST mark them, and any aggregate that includes them, as pre-012 (untrusted).
- **FR-028**: No benchmark runs other than the validation smoke run land in this round.
- **FR-029**: The round's validation MUST be one todo-api smoke run whose records show rubric scores on clarify and architecture, a commit on every record, and one file per cell.
- **FR-030**: Documentation describing the harness's records and the affected stages' behaviour MUST be updated in the same change as the behaviour.

### Key Entities

- **Benchmark record**: one measurement of one stage, task attempt or oracle grade within a cell. Gains: Kroker commit and dirty flag, real prompt hash, shared cell label.
- **Cell**: one case run under one arm. Gains: completion flag, last stage reached, graded / not graded / grading-failed status.
- **Oracle grade**: the held-out test result for a cell's integration result; produced in a single-use environment.
- **Case manifest**: declares the case's rubrics, vetoes and oracle; registered files are now mandatory to exist.
- **Stage-to-rubric mapping**: ties a record's stage name to the rubric (and calibration bucket) that judges it.
- **Gate record**: the analyze or merge outcome; gains a "not evaluated" state for benchmark mode.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the validation smoke run, 100% of records for stages with a registered rubric carry a rubric score (baseline: 0 of 418).
- **SC-002**: In the validation smoke run, 100% of records carry a Kroker commit identifier, and 100% of prompted-role records carry a non-empty prompt hash (baseline: 0%).
- **SC-003**: The validation smoke run produces exactly one record file and one report row per cell (baseline: two).
- **SC-004**: A deliberately aborted cell yields zero scored oracle records and appears in the report as one incomplete cell (baseline: scored 0.0).
- **SC-005**: An empty-tree integration result graded immediately after a passing one scores 0 passed tests in 100% of repeated trials.
- **SC-006**: In the validation smoke run, qa and review wall-clock each differ from the code attempt's by more than measurement noise, and each is no longer than the interval its role actually worked.
- **SC-007**: A benchmark run that passes the oracle in full records zero analyze/merge rejections attributable to benchmark-mode conditions (baseline: 14 of 14 rejected).
- **SC-008**: A missing registered rubric file stops the cell with a named cause at zero model spend.
- **SC-009**: All pre-existing record files still load after the change.

## Rulings (GATE 1, user, 2026-10-06)

- **R1 (FR-017)**: the canonical cell label is the arm name (for example `zai-coding-plan-glm-5.2`). A cell is a case under an arm. The per-role model id remains its own record field (FR-018 unchanged).
- **R2 (FR-024)**: the analyze and merge gates in benchmark mode are decided per gate after the FR-023 diagnosis. Where a gate depends on something a benchmark run cannot have, the record says "not evaluated" (the FR-025 state) instead of reporting a failure.
- **R3 (FR-027)**: the existing 1,249 pre-012 records stay untouched on disk and loadable. Reports mark them as pre-012 (untrusted aggregates). Phase 2 re-scores the existing cat-cafe records.

## Assumptions

**Audit claims verified in the current tree (2026-10-06, main `7f5191d0`)**

- **F1 holds.** The judge's rubric loader derives the cases location from the module's own file path and ignores the environment override; a missing rubric file is skipped by design ("that stage simply won't be judged"). The report reader imports the same path. The oracle and the task loader honour the override, which the worker image sets. The exact in-container path quoted in the report was not re-observed; the mechanism was.
- **F2 holds, mechanism confirmed.** The benchmark workflow swallows a failed cell and then grades the oracle unconditionally whenever the case declares a language. The record derives fail from "score below 1.0" with a missing score read as zero. The count "8 of 18" is the report's and was not recounted.
- **F4 holds.** The qa record is written with the attempt's start time as its start. The audited line number is still accurate.
- **F10 holds.** The record builder writes an empty prompt hash on every record, and no record field carries a Kroker commit.
- **F15 holds.** The stage-to-rubric mapping is keyed on `planning`; records use `plan`.

**Audit claims not settled — the round must establish them**

- **F3 cause unknown.** The oracle already checks out each run into a fresh temporary tree, so the leak is not simply a reused checkout. The report itself says the cause was not found. The spec requires a reproduction attempt first (FR-010); isolation (FR-011/012) lands regardless of whether it reproduces.
- **F8 cause unknown.** The merge stage already has a benchmark-mode skip for the missing remote, so that is not the whole story. FR-023 requires the diagnosis before repair-or-disable is implemented.
- **F7 is only partly in scope.** "Quality is pass/fail re-encoded" is closed for qa's copied verdict (FR-020); first-attempt versus after-repair scoring is Phase 2 (2.6).
- **F5 is only partly in scope.** Review tokens are in (FR-021). The $0.00 code cost on subscription-billed harness runs is not addressed here.

**Defaults taken**

- A rubric failure is a pre-flight failure (before model spend), not an after-the-fact cell error.
- The line between not graded and graded is "the code stage finished". The first draft said "the code stage produced an integration result the oracle can check out"; the skeptic pass showed that the integration branch is created before any code task runs, so that wording would have graded the audited empty-tree run. Amended after GATE 1 (plan research R-4); listed for GATE 2.
- The prompt hash covers the role's instruction content as resolved for the run; per-request rendered text is not hashed.
- Per-role model identity stays on the record alongside the shared cell label.
- If the empty-tree result cannot be reproduced, the round records what was tried and proceeds on the strength of the isolation requirement.
- The validation smoke run is a single todo-api cell on the existing arm, run alone (no parallel pipeline runs on this machine).

## Out of Scope

- Phase 2 (scoring output: composite, heatmap layers, run-by-run view, partial credit, gate-versus-oracle agreement, first-attempt versus after-repair, case-scoped success criteria, opencode waste counters, erosion and verbosity) — findings F6, F9, F12, F14.
- Phase 3 (corpus: DevEval runs, larger cat-cafe oracle, NL2Repo-Bench imports, case acceptance check, root-cause labels).
- Phase 4 (calibration fixtures, baseline, paired comparisons) — finding F13.
- Any benchmark run beyond the single validation smoke run.
- Why the eight cat-cafe runs died in research and clarify (report §5).
- Rewriting or re-grading existing records.
- Editing, staging or committing the source report.

## Dependencies

- `docs/reports/2026-10-06-benchmark-improvement-plan.md` (read-only source of findings and plan).
- `BENCHMARK.md` and the nearest `AGENTS.md` files for the harness and the code, review, qa, analyze and merge stages.
- Repo rules: 1000-line file ceiling, cross-stage call ban, producer owns its artifacts, behaviour and its clauses change in the same diff.
- A dedicated benchmark environment for the smoke run, per the benchmark launch runbook.
