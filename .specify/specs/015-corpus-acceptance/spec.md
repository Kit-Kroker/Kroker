# Feature Specification: Corpus Acceptance

**Feature Branch**: `015-corpus-acceptance`

**Created**: 2026-10-11

**Status**: Approved (GATE 1, 2026-10-11)

**Input**: Round 015, Phase 3 "Fix the corpus" of `docs/reports/2026-10-06-benchmark-improvement-plan.md` (section 4, tasks 3.1 to 3.6 and the Exit line). Seed brief: `.workspace/tmp/015-planner-brief.md`. Advisor consults: `.workspace/tmp/advisor-015-1.md`, `-2.md`, `-3.md` (consensus reached on every point below).

## Context

Rounds 012 to 014 made the benchmark records trustworthy and the scoring
output readable. The corpus those tools read is still weak. One case
discriminates (cat-cafe-monitoring, 12 tests). One is saturated
(todo-api-greenfield, 6 of 6 every time). Six imported DevEval cases have
never been run. No case has ever been run under two arms, and nothing
checks that a case is worth running before model budget is spent on it.

This round adds the check that decides whether a case belongs in the
corpus, applies it to the cases on disk, grows the one private case, puts
the smoke test in front of every run, and adds root-cause labels to the
failure view. It contains real pipeline runs. They are paid, serial, and
each batch sits behind its own user gate.

**This round does not reach the Phase 3 exit, and says so.** The exit asks
for eight accepted cases, two of them private. Tasks 3.1 to 3.6 can
produce at most seven candidates and one private case (see Q1). The round
reports the honest count and names the two rounds that close the gap.

## Terms

- **Arm**: a named role-to-model mix. One case run under one harness and one arm is a cell.
- **Strong arm / weak arm**: two arms that differ only in the model of the harness roles (dev, test, devops). Proposer roles keep the registry default in both.
- **Partial credit**: oracle tests passed over tests total, for one graded run (round 013).
- **Reference**: a complete solution of a case, stored in the case's `reference/` directory, never shown to an agent.
- **Oracle identity**: a hash of the source files of a case's oracle directory (caches and compiled files excluded). The acceptance record stores the test count beside it (amendment A1). Two runs are comparable only when it matches.
- **Role** of a case: `corpus` (measured), `smoke` (run before other runs, never measured), `probe` (no oracle), `parked` (screened out, kept on disk).
- **Visibility** of a case: `private` means authored in this project and not derived from any published dataset or public repository. `public` means derived from one. It is a statement of provenance.
- **Exposure** of a case: where its held-out material (oracle, reference) is stored and whether that place is public.
- **Lost run**: a run that ended before its code stage finished (round 013).
- **Baseline records**: the 111 record files under `runs/benchmarks` at the start of this round.

## User Scenarios & Testing

### User Story 1 - A case is accepted or rejected by a recorded check (Priority: P1)

Someone asks whether a case belongs in the corpus. One command answers
with three checks and a verdict, and writes the answer to a file in the
case's directory that is committed with the case.

**Why this priority**: it is task 3.4 and the unit the Phase 3 exit
counts. Todo-api would have been caught at authoring time by it.

**Independent Test**: run the command on a DevEval case with no worker and
no model call, and read the reference and floor results and the verdict.

**Acceptance Scenarios**:

1. **Given** a case whose reference passes every oracle test, **When** the check runs, **Then** the reference check passes and records the oracle identity.
2. **Given** a case whose reference fails one oracle test, **When** the check runs, **Then** the verdict is rejected with reason `reference`, and the failing test is named.
3. **Given** a case whose oracle passes one or more tests on an empty tree, **When** the check runs, **Then** the floor check records how many, and the verdict is rejected with reason `floor` when the empty tree scores as high as the reference.
4. **Given** a case with no reference directory, **When** the check runs, **Then** the verdict is rejected with reason `reference` and the text says none exists.
5. **Given** a case with graded runs of the strong arm only, not all at 1.0, **When** the check runs, **Then** the separation check reads not assessed and the verdict is `not_assessed`.
6. **Given** one graded run per arm where the strong arm's partial credit exceeds the weak arm's by 0.15 or more, **When** the check runs, **Then** the verdict is `provisional`.
7. **Given** three or more graded runs per arm with the same margin on the means, **When** the check runs, **Then** the verdict is `accepted`.
8. **Given** a strong arm at 1.0 on every graded run, **When** the check runs, **Then** the verdict is rejected with reason `saturated`; a strong arm at 0.0 on every graded run gives `degenerate`; a margin under 0.15 or in the wrong direction gives `no_separation`.
9. **Given** graded runs made against two oracle identities, **When** the check runs, **Then** only runs of the current identity are used and the others are counted as not comparable.
10. **Given** the offline half only (reference and floor), **When** it runs, **Then** it needs no worker, no server and no model call; its only network use is installing packages for the grading environment.

---

### User Story 2 - The smoke test runs before any corpus run (Priority: P1)

Before a corpus case is run, the smoke case has passed on the same Kroker
commit. The run command checks this itself.

**Why this priority**: it is task 3.6, and every real run in this round
depends on it. Today the rule lives in runbook notes.

**Independent Test**: with no stamp for the current commit, start a corpus
run and confirm it is refused before any service is contacted.

**Acceptance Scenarios**:

1. **Given** no passing smoke stamp for the current commit, **When** a corpus case is started, **Then** the command refuses before contacting any service and says how to run the smoke test.
2. **Given** a passing stamp for the current commit, **When** a corpus case is started, **Then** it starts.
3. **Given** the override flag, **When** a corpus case is started with no stamp, **Then** it starts and prints that the smoke check was skipped.
4. **Given** a tree with uncommitted changes, **When** a corpus case is started, **Then** no stamp matches.
5. **Given** a finished smoke run, **When** its result is checked, **Then** the stamp is passing only if clarify and architecture carry rubric scores, every record carries a commit, the cell wrote one record file, and the oracle passed every test; each failed condition is named.
6. **Given** any score or acceptance check, **When** it is computed, **Then** smoke runs enter no corpus count, no acceptance check and no mean.
7. **Given** a case with role `parked`, **When** it is started without the override, **Then** it is refused.

---

### User Story 3 - The failure view names the stage to fix (Priority: P2)

Beside the error-class matrix, the score shows a root-cause view: lost
runs and failed requirements counted under planning, execution,
verification or unattributed, per arm.

**Why this priority**: it is task 3.5. It needs no run and is proven on
the stored records.

**Independent Test**: score cat-cafe on the stored records and read eight
lost runs under planning.

**Acceptance Scenarios**:

1. **Given** a lost run whose last stage is before code, **When** the view is built, **Then** it counts once under planning.
2. **Given** a lost run whose last stage is code, **When** the view is built, **Then** it counts once under execution.
3. **Given** a failed requirement of a graded run with no human label, **When** the view is built, **Then** it counts under unattributed.
4. **Given** a labels file that names a root cause for that run and requirement, **When** the view is built, **Then** it counts under that cause and is marked as labelled by a person.
5. **Given** a labels file that names a requirement the case does not define, or a run that has no records, **When** it is loaded, **Then** loading fails and names the entry.
6. **Given** the stored cat-cafe records, **When** the case is scored, **Then** the view shows 8 lost runs under planning, and states that failed requirements cannot be shown for the 10 graded runs because the case had no requirement mapping when they ran.
7. **Given** any view, **When** it is rendered, **Then** it prints how many failed requirements are labelled and how many are not, and every cell prints its denominator.

---

### User Story 4 - The cat-cafe oracle grows and gains a reference (Priority: P2)

The cat-cafe case ships 30 to 40 oracle tests, a file mapping each test to
a requirement of the case, and a reference solution that passes all of
them.

**Why this priority**: it is task 3.2. Twelve tests give steps of 0.083;
the case cannot pass acceptance without a reference.

**Independent Test**: run the offline acceptance half on cat-cafe.

**Acceptance Scenarios**:

1. **Given** the grown oracle and the reference, **When** the offline acceptance half runs, **Then** the reference passes every test and the empty tree passes none.
2. **Given** the mapping file, **When** it is loaded, **Then** every oracle test belongs to exactly one requirement, and every requirement traces to Task 1, Task 2 or the interface contract of the case text.
3. **Given** the case text, **When** this round ends, **Then** its requirements are unchanged.
4. **Given** any oracle test, **When** it is read, **Then** it reaches the product only through the interface contract and asserts nothing the case text leaves to the implementer.
5. **Given** a run of the case, **When** its worktree is prepared, **Then** nothing from `reference/` is in it.
6. **Given** the ten stored graded runs (12 tests) and a new run (grown oracle), **When** the case is scored, **Then** they are in separate groups and no figure averages across them.

---

### User Story 5 - The DevEval cases are screened (Priority: P2)

Each of the six imported DevEval cases is run once under the strong arm.
A case whose result is strictly between 0 and 1 stays in the corpus. The
others are parked.

**Why this priority**: it is task 3.1 and supplies most of the corpus. It
costs real runs.

**Independent Test**: after batch R1, read each case's role and acceptance
record.

**Acceptance Scenarios**:

1. **Given** a screening run with partial credit strictly between 0 and 1, **When** it is recorded, **Then** the case keeps role `corpus`.
2. **Given** a screening run at 0.0 or 1.0, **When** it is recorded, **Then** the case gets role `parked` and its acceptance record says why; no file is deleted.
3. **Given** a lost screening run, **When** it is recorded, **Then** the case is run once more; a second lost run gives the case the result `no result`, and the case is parked.
4. **Given** a screening run, **When** it is scored, **Then** its figures come from the round 013 output with no new scoring rule.

---

### User Story 6 - Each surviving case gets a second arm (Priority: P3)

Cat-cafe (on the grown oracle) and every DevEval case that screened in are
run once under the weak arm, so the separation check has data.

**Why this priority**: it is the second half of task 3.4. It is the most
expensive part and the first part to cut if the user stops early.

**Independent Test**: after batches R2 and R3, read the separation check
of each case.

**Acceptance Scenarios**:

1. **Given** one graded run per arm, **When** acceptance is run, **Then** the verdict is `provisional` or rejected with its reason, never `accepted`.
2. **Given** the end of the round, **When** the corpus status is printed, **Then** it lists every case with its role, visibility, exposure and verdict, and states "N of 8 accepted or provisional, M of 2 private".

---

### User Story 7 - The NL2Repo-Bench licence is checked before anything is imported (Priority: P3)

The licence finding is written down and no NL2Repo-Bench content enters
the repository.

**Why this priority**: it is the precondition of task 3.3, and the finding
already blocks the import.

**Acceptance Scenarios**:

1. **Given** the finding, **When** the round ends, **Then** a dated note in the round's directory states what was checked, where, and the result.
2. **Given** the repository after the round, **When** it is searched, **Then** it contains no file taken from NL2Repo-Bench: the round's diff adds no case directory or file of that provenance.

---

### Edge Cases

- A case with a reference whose oracle needs dependencies: the reference and floor checks run in the same fresh per-grade environment the oracle uses in a real run (round 012).
- A case whose oracle passes some tests on an empty tree but fewer than the reference: floor passes, and the count is recorded.
- A case edited after its acceptance record was written: the record names an oracle identity that no longer matches, and the corpus status shows it as stale.
- A two-arm case where one arm has only lost runs: separation reads not assessed.
- A weak arm that scores higher than the strong arm: rejected with `no_separation`, and both means are recorded.
- A smoke stamp from another commit, or older than the newest commit: does not match.
- A corpus run started from a detached worktree: the stamp is found by commit, wherever the run is started.
- A labels file for a run of another case: refused at load.
- A requirement with several mapped tests where some pass: counted as failed in the root-cause view, with its partial score kept in the error-class matrix as today.
- A probe case (no oracle): acceptance reads `not_assessed` with the text "no oracle"; it enters no count.
- A baseline record file: byte-identical at every commit of the round.

## Requirements

### Functional Requirements

**Case metadata**

- **FR-001**: A case manifest MUST be able to state a role (`corpus`, `smoke`, `probe`, `parked`) and a visibility (`private`, `public`). A manifest that states neither MUST load as before, with role `corpus`.
- **FR-002**: The ten cases on disk MUST state both. Before any run they read: todo-api-greenfield `smoke`; cat-cafe-monitoring `corpus`, `private`; the six DevEval cases `corpus`, `public`; add-login-greenfield and crew-probe `probe`, `private`.
- **FR-003**: Cases with role `smoke`, `probe` or `parked` MUST enter no corpus count and no acceptance tally.

**Acceptance check (report 3.4)**

- **FR-004**: One command MUST run the acceptance check for one case and write an acceptance record into the case's directory.
- **FR-005**: The **reference check** MUST pass only when the case's reference passes every oracle test, run the way a real grade runs the oracle. The existing reference verification for imported cases MUST keep working.
- **FR-006**: The **floor check** MUST run the oracle against an empty tree, in a fresh environment, and record tests passed. It fails when the empty tree scores as high as the reference.
- **FR-007**: The **separation check** MUST use graded runs of the current oracle identity only, under exactly two named arms. It passes when mean partial credit of the strong arm minus that of the weak arm is at least 0.15.
- **FR-008**: The verdict MUST be one of: `accepted` (all three checks pass, at least three graded runs per arm); `provisional` (all three pass, fewer than three graded runs on either arm); `rejected` with one reason of `reference`, `floor`, `saturated`, `degenerate`, `no_separation`; `not_assessed` (separation has no data, or the case has no oracle).
- **FR-009**: `saturated` MUST mean the strong arm scored 1.0 on every graded run; it needs no weak-arm run. `degenerate` MUST mean the strong arm scored 0.0 on every graded run; it needs no weak-arm run either. So a case parked by the screen records `saturated` or `degenerate` as its reason. Reasons are tested in this order and the first that applies is recorded: `reference`, `floor`, `saturated`, `degenerate`, `no_separation`.
- **FR-010**: The acceptance record MUST carry: case, verdict and reason, the three checks with their evidence (oracle identity, tests passed and total for reference and floor, arm names, run ids, means and run counts per arm, the margin), visibility, exposure, the Kroker commit and the date.
- **FR-011**: Which arm is strong and which is weak MUST be stated by the case manifest, not inferred from scores.
- **FR-012**: The reference and floor checks MUST run with no worker, no server and no model call. Installing packages for the grading environment is their only network use.
- **FR-013**: A corpus status command or view MUST list every case with role, visibility, exposure, verdict and whether its record is stale, and MUST print the tally against the Phase 3 exit (accepted or provisional cases of 8; private ones of 2).

**Oracle identity**

- **FR-014**: The cell record, the oracle record and the oracle-task records of a new run MUST carry the oracle identity of the case at the time the cell ended (amendment A1).
- **FR-015**: No aggregate may combine runs of different oracle identities. A baseline record has no stored identity and forms its own group.

**Smoke test (report 3.6)**

- **FR-016**: One command MUST run the smoke case and check the conditions of US2 scenario 5.
- **FR-017**: The result MUST be written as a stamp keyed by Kroker commit, outside `runs/benchmarks`.
- **FR-018**: Starting a `corpus` case MUST be refused when no passing stamp exists for the current commit or the tree has uncommitted changes, before any service is contacted. An explicit flag MUST override the refusal, and the override MUST be printed.
- **FR-019**: Starting a `parked` case MUST be refused without the same kind of explicit override. Starting a `smoke` or `probe` case needs no stamp.

**Root-cause labels (report 3.5)**

- **FR-020**: The score MUST add a root-cause view with the columns planning, execution, verification, unattributed, per arm and record generation. The error-class matrix stays.
- **FR-021**: A lost run MUST count once: under planning when its last stage is before code, under execution when it is code.
- **FR-022**: A failed requirement of a graded run (requirement score below 1) MUST count under unattributed unless a human label names its cause. No cause may be assigned automatically to a graded run.
- **FR-023**: Human labels MUST live in the repository, one file per run, keyed by requirement, and MUST be validated at load against the case's requirement mapping and the run's records.
- **FR-024**: The view MUST print labelled and unlabelled counts, a denominator in every cell, and MUST follow round 013's rules for fewer than five observations and for record generations.
- **FR-025**: Labels MUST be applied at score time. No stored record may be changed.

**cat-cafe (report 3.2)**

- **FR-026**: The cat-cafe oracle MUST hold 30 to 40 tests, the 12 existing ones included unless one is shown to be wrong.
- **FR-027**: A requirement mapping MUST assign every oracle test to exactly one requirement and give each requirement an error class. Every requirement MUST trace to the case text.
- **FR-028**: The case text in the manifest MUST NOT change.
- **FR-029**: Every test MUST reach the product only through the interface contract, and MUST NOT assert a value the case text leaves free (zone coordinates, thresholds, activity rules beyond what the text states).
- **FR-030**: A reference solution MUST be added and MUST pass every test. The offline acceptance half MUST be green for cat-cafe.
- **FR-031**: It MUST be proven by test that no file of a case's `reference/` reaches a run's worktree or prompt.

**DevEval screen and arm runs (report 3.1, 3.4)**

- **FR-032**: Each DevEval case MUST be run once under the strong arm, serially. The result decides its role per US5.
- **FR-033**: Cat-cafe and each case that screened in MUST be run once under the weak arm. Cat-cafe MUST also be run once under the strong arm on the grown oracle.
- **FR-034**: Before the first run of the weak arm, one model call MUST prove the weak model answers on the harness.
- **FR-035**: No two runs may execute at the same time, and no run may start while a pipeline run is executing on the machine.
- **FR-036**: Each batch (R0 to R3) MUST start only after the user approves it, with the estimate shown.

**NL2Repo-Bench (report 3.3)**

- **FR-037**: The licence finding MUST be recorded in the round's directory. No NL2Repo-Bench content may be added to the repository or downloaded into a case directory.

**Records and documents**

- **FR-038**: Every baseline record file MUST stay byte-identical. A per-file manifest MUST be taken before the first run and committed in this round's spec directory (outside `runs/`, not a `.jsonl` file); the records fingerprint (`111 2a32da97...e56831`) MUST be unchanged until batch R0 starts; after that the manifest is the check, and runs only add files.
- **FR-039**: Nothing under `docs/reports/` may be edited, staged or committed.
- **FR-040**: `BENCHMARK.md` (corpus section, error matrix, how to run) MUST be updated in the same change as the behaviour.

### Key Entities

- **Case**: gains role, visibility and the names of its strong and weak arm.
- **Acceptance record**: one file per case; three checks with evidence, a verdict, exposure, commit, date.
- **Oracle identity**: test count and content hash of a case's oracle.
- **Smoke stamp**: commit, time, verdict, the failed conditions if any.
- **Root-cause label**: run, requirement, cause, and whether a rule or a person assigned it.
- **Requirement mapping**: the existing per-case task file; cat-cafe gains one.

## DAG

```text
A  case metadata (FR-001..003) ──────────────┬──────────────┬─────────────┐
                                             │              │             │
B  oracle identity (FR-014, 015) ────────────┤              │             │
                                             ▼              ▼             │
C  acceptance, offline half (3.4a) ──► E  cat-cafe oracle,  D  smoke command │
   FR-004..006, 010, 012                   mapping, reference    and run gate  │
        │                                  (3.2) FR-026..031     (3.6) FR-016..019
        │                                       │                    │
F  root-cause view (3.5) FR-020..025            │                    ▼
   (needs A only; proven on stored records)     │           ── GATE R0 ── smoke run
G  licence note (3.3) FR-037 (needs nothing)    │                    │
                                                │                    ▼
        │                                       │           ── GATE R1 ── six DevEval
        ▼                                       │               screening runs (3.1)
H  acceptance, separation half (3.4b)           │                    │
   FR-007..009, 011  ◄──────────────────────────┴────────────────────┤
        │                                                            ▼
        │                                   ── GATE R2 ── cat-cafe strong + weak
        │                                   ── GATE R3 ── weak arm on screened-in
        ▼                                                    DevEval cases
I  acceptance records committed, corpus status, tally (FR-013)
```

| Node | Report task | Needs | Real runs |
|---|---|---|---|
| A case metadata | 3.4, 3.6 | none | no |
| B oracle identity | 3.2, 3.4 | none | no |
| C acceptance, offline half | 3.4 | A, B | no |
| D smoke command and run gate | 3.6 | A | no (built), R0 (used) |
| E cat-cafe oracle, mapping, reference | 3.2 | B, C | no |
| F root-cause view | 3.5 | A | no |
| G licence note | 3.3 | none | no |
| H acceptance, separation half | 3.4 | C | no (built on fixtures) |
| R0 smoke run | 3.6 | D | 1 |
| R1 DevEval screen | 3.1 | R0, C | 6 (up to 12 with retries) |
| R2 cat-cafe two arms | 3.2, 3.4 | R0, E, H | 2 |
| R3 DevEval weak arm | 3.4 | R1, H | up to 6 |
| I records and tally | exit | all above that ran | no |

The table is the build order. In the diagram the arrows into H from E
and from the run gates are data at verdict time, not build dependencies:
H is built and tested on fixtures.

A to H are code and authoring and can merge without any run. D, F and G
are independent of each other and of E. Stopping after any gate leaves a
complete increment.

## Run Gates and Estimate

Measured on the stored records, runs that reached code: cat-cafe mean
3.4 h (max 4.7 h), $1.91 and 2.2M tokens per run; todo-api mean 1.6 h (max
2.2 h), $1.63. Code-stage cost is $0 on the subscription; the dollars are
research and judging. DevEval cases have research off and have never been
run, so their figures are estimates.

| Gate | Batch | Runs | Wall clock | Dollars |
|---|---|---|---|---|
| R0 | smoke: todo-api once | 1 | about 1.6 h | about $1.6 |
| R1 | six DevEval cases, strong arm | 6 (to 12) | 6 to 12 h | under $6 |
| R2 | cat-cafe, grown oracle, strong then weak | 2 | 7 to 9 h | about $4 |
| R3 | weak arm on screened-in DevEval cases | up to 6 | 6 to 12 h | under $6 |
| | Total | about 15 | 20 to 35 h | $15 to $25 |

Rules for every batch: serial; dedicated Temporal on port 7234; clean
detached worktree of the commit under test; no pipeline run executing;
gate policy off. R0 is repeated whenever the commit under test changes.
Each repeat (about 1.6 h, about $1.6) is outside the total above and is
approved at the gate of the batch it precedes; two repeats would bring
the round to about 17 runs.
After R1 the estimate for R3 is restated from R1's measured times.

## Success Criteria

- **SC-001**: The offline acceptance half is green (reference passes all, floor passes fewer) for cat-cafe and for all six DevEval cases, with no worker, no server and no model call.
- **SC-002**: On a fixture shaped like todo-api's history (reference passes, strong arm at 1.0 on every graded run) the verdict is rejected with reason `saturated`. Todo-api itself, which ships no reference, reads rejected with reason `reference`.
- **SC-003**: The cat-cafe oracle has 30 to 40 tests, each in exactly one requirement; the reference passes all; the empty tree passes none.
- **SC-004**: With no stamp, starting a corpus case is refused in under five seconds with no service contacted; with a passing stamp it starts.
- **SC-005**: Scoring cat-cafe on the stored records shows 8 lost runs under planning in the root-cause view, and every figure round 013 pinned is unchanged.
- **SC-006**: All 111 baseline record files are byte-identical at the end of the round.
- **SC-007**: Every case on disk has a role and a visibility; every corpus case has a committed acceptance record whose oracle identity matches the case.
- **SC-008**: The round's closing report states "N of 8 accepted or provisional, M of 2 private" from the committed records, and lists each parked case with its reason.
- **SC-009**: Zero files from NL2Repo-Bench are in the repository: the round's diff adds none, and the licence note records what was inspected and where.
- **SC-010**: No verdict of `accepted` is recorded on fewer than three graded runs per arm.
- **SC-011**: (If R1 runs) each of the six DevEval cases has a screening result or `no result`, and a role that follows from it.
- **SC-012**: (If R2 runs) cat-cafe has one graded run per arm on the grown oracle and a separation verdict.

## Rulings (GATE 1, user, 2026-10-11)

All nine open questions were answered as recommended. Q4 was completed
with the model id.

- **R1 (Q1)**: round 015 does not claim the Phase 3 exit; rounds 016 and 017 follow.
- **R2 (Q2)**: task 3.3 is the licence finding only; nothing is imported.
- **R3 (Q3)**: three checks, a margin of 0.15, `provisional` under three graded runs per arm.
- **R4 (Q4)**: the weak arm is `zai-coding-plan/glm-5.3-flash` on opencode for dev, test and devops. Rationale (user): the flash tier of the current generation, clearly below the strong arm (glm-5.2, variant max) and not old enough to fall to guaranteed zeros; glm-4.7 was rejected as a capability cliff. Chosen from the coding-plan list: glm-4.7, glm-5-turbo, glm-5.2, glm-5.2-highspeed, glm-5.3, glm-5.3-flash, glm-5.3-highspeed. The FR-034 probe still applies.
- **R5 (Q5)**: the four batches R0 to R3 are approved as a shape; each batch keeps its own gate.
- **R6 (Q6)**: a rule for lost runs only; graded runs are unattributed unless a person labels them.
- **R7 (Q7)**: the grown cat-cafe oracle and its reference are committed this round, with exposure `repo_public`.
- **R8 (Q8)**: a corpus run is refused without a passing stamp, with a printed override.
- **R9 (Q9)**: the crew authors the cat-cafe tests and reference; the user approves the requirement list at GATE 2 before any test is written.

## Amendments after GATE 1 (plan, 2026-10-11; listed for GATE 2)

Each was checked in code before the spec changed.

- **A1 (Terms, FR-014)**: the oracle identity is the content hash alone; the test count is stored beside it in the acceptance record. FR-014 is narrowed from "every record of a new run" to the cell, oracle and oracle-task records of a run: the run takes its identity from them, and stage records are written by the pipeline, which knows nothing of the oracle.
- **A2 (FR-032, FR-033)**: a case names both arms in its manifest, so the run command gains a way to run one named arm. Without it R1 would run both arms and R3 would repeat the strong one.
- **A3 (FR-005)**: an imported case keeps its dependency list outside `reference/` (in `reference_env/`). The reference check installs that list; the existing `verify-case` does not and depends on the caller's environment.
- **A4 (FR-006)**: scratch repositories start empty, so "the empty tree" is the only floor. The floor is compared with the reference by tests passed, because a suite that cannot be collected reports fewer tests in total.
- **A5 (Run gates)**: batches R0 to R3 all run on one commit, the one the code half is merged at. Role changes and acceptance records are committed afterwards and do not move it, so R0 runs once unless a defect forces a code fix.

## Open Questions as put to GATE 1 (resolved above)

Each had a recommendation, and the spec is written to it.

- **Q1 — This round cannot reach the Phase 3 exit. Accept that?** Recommendation: **yes.** Cat-cafe is the only private case with an oracle. This round yields at most seven candidates (cat-cafe and six DevEval) and one private case. The round's own exit is SC-001 to SC-010 plus the honest tally. Two follow-up rounds close the gap: 016, a second private case (a kata that forces planner decomposition, the top gap named in `BENCHMARK.md` section 5); 017, more public cases. `add-login-greenfield` is not promoted: it is one route with no oracle and would saturate like todo-api.
- **Q2 — Task 3.3 after the licence check.** Recommendation: **deliver the finding only; import nothing.** The NL2Repo-Bench repository has no licence file and GitHub reports none, so there is no grant to copy its requirement documents; this repository is public, which rules out vendoring. A git-ignored local copy is also rejected: it is an unreviewable corpus and still copies unlicensed text. Public cases come in round 017 from sources with a clear licence (the rest of DevEval's Python set, then PRDBench or Commit0, each licence checked first).
- **Q3 — What "score differently" means.** Recommendation: **three checks (reference, floor, separation), a margin of 0.15 in partial credit, and `provisional` until three graded runs per arm.** One run per arm cannot prove separation on a case whose run-to-run standard deviation is 0.23, so this round can reach `provisional` at best. `accepted` arrives with the Phase 4 baseline. 0.15 equals the tolerance the calibration command already uses. The margin is the user's to move.
- **Q4 — The weak arm's model.** Recommendation: **the smallest GLM model the coding subscription covers, on opencode, for dev, test and devops only.** The strong arm is today's cell (glm-5.2, variant max). Dropping `--variant max` on the same model is too close to separate anything. Answered at GATE 1 (R4): `zai-coding-plan/glm-5.3-flash`; it is probed with one call before any run.
- **Q5 — The four run batches and their budget.** Recommendation: **approve the plan of R0 to R3 as a shape (about 15 runs, 20 to 35 h, $15 to $25), with each batch still gated on its own.** Cat-cafe (R2) comes before the DevEval weak arm (R3) so the private case is covered if the round is stopped early.
- **Q6 — Where root-cause labels come from.** Recommendation: **a rule for lost runs only (before code is planning, in code is execution); failed requirements of graded runs stay unattributed unless a person labels them in a committed file.** Nothing on a record links a requirement to the stage that broke it. A rule such as "all gates passed, so it is a verification escape" would blame qa for what the source paper found to be planner omissions more than half the time. An LLM labeller is an uncalibrated judge until Phase 4.
- **Q7 — Publish the grown cat-cafe oracle and its reference?** Recommendation: **yes for this round, labelled.** The repository is public and the 12 existing tests are in its history for good. The acceptance record states visibility `private` (provenance) and exposure `repo_public`. Private storage outside the repository is built in round 016, so the second private case is never published. The alternative, private storage now, needs a second cases root that overlays the first (today the override replaces it wholesale), leaves CI unable to check the case, and adds a backup duty.
- **Q8 — How strict is the smoke gate?** Recommendation: **refuse a corpus run without a passing stamp for the current commit, with a printed override flag.** The alternative is a warning only.
- **Q9 — Who authors the cat-cafe tests and reference?** Recommendation: **the crew authors them; the user approves the requirement list (the mapping file) at GATE 2 before any test is written.** The requirement list decides what the benchmark measures, and it must add nothing to the case text.

## Assumptions

**Verified in the current tree (main `c3f6319c`, 2026-10-11)**

- Ten cases on disk. The six DevEval cases each have an oracle, a reference, a requirement mapping and no network requirement: 79 tests, 31 requirements.
- Cat-cafe has 12 oracle tests, no requirement mapping and no reference. Todo-api has 6 tests, a mapping, no reference. Add-login has no oracle and no language. Crew-probe has no oracle.
- `sdlc benchmark verify-case` already runs a case's oracle against its reference through the real grading command. It is the reference check for cases that ship a reference.
- The case manifest supports named arms. Every oracle case is a one-arm matrix today.
- The error matrix is error class by arm, built from per-requirement oracle records. Its six classes validate every mapping file.
- No integration branch of a stored run survives, so stored runs cannot be re-graded on a larger oracle.
- There is no batch command; runs start one case at a time.
- The records fingerprint hashes every `*.jsonl` under `runs/benchmarks`, so it changes with the first new run. FR-038 states the rule that replaces it after R0.
- The cases-root override replaces the root wholesale; it is not an overlay.
- The repository `Kit-Kroker/Kroker` is public. The seed brief's "private repo" is wrong.
- NL2Repo-Bench: no licence file at the repository root, GitHub reports no licence, tasks are in-repo under `test_files/`.

**Not verified — the plan must establish**

- Whether records already carry anything usable as an oracle identity.
- Whether the floor check can reuse the per-grade environment of round 012 without a worker.
- How a run's worktree is seeded, to prove FR-031.
- Whether `zai-coding-plan/glm-5.3-flash` answers on opencode under the subscription. The model is ruled (R4); the FR-034 probe proves it before any weak-arm run.
- How long a DevEval case takes to run.
- Whether a DevEval reference's licence file and attribution survive in the form the dataset licence requires once a case is parked.
- The advisor's note that only two non-quarantined DevEval Python repositories remain (hybrid-images, textcnn). It matters to round 017 only.

**Defaults taken**

- A requirement counts as failed when its score is below 1.
- Screening uses the report's rule as written: one run, kept when strictly between 0 and 1.
- Parking changes a case's role and writes its acceptance record. It deletes nothing.
- The 12 existing cat-cafe tests are kept unless one is shown to be wrong.
- Smoke runs are todo-api under its existing one-arm matrix.

## Out of Scope

- A second private case (round 016) and private storage for held-out material (round 016).
- Importing more public cases from any source (round 017).
- An automatic root-cause labeller (Phase 4, with calibration).
- Erosion and verbosity (report 2.9).
- Phase 4: calibration, the baseline of three to five runs per case, paired comparison and significance tests.
- The report's own open questions (what killed eight cat-cafe runs, whether token counts can stand for cost, a checkpointed case).
- Keeping a run's research stage from reaching this project's own public repository.
- A batch runner.
- Changes to the web console.
- Editing, staging or committing anything under `docs/reports/`.
- Rewriting, re-grading or deleting stored records.

## Follow-ups

- **Round 016**: second private case, stored outside the public repository from its first commit, with the overlay cases root that needs.
- **Round 017**: public cases from licence-checked sources, to reach eight.
- **Phase 4**: a calibrated labeller that reads the plan against a failed requirement; three runs per arm turn `provisional` into `accepted`.
- **Per-task gate-versus-oracle agreement** (round 013 follow-up): unblocked for cat-cafe once the mapping file exists.
- **Research egress**: a research-enabled run can in principle find a published oracle or reference.

## Dependencies

- `docs/reports/2026-10-06-benchmark-improvement-plan.md` (read-only: section 4 Decisions, Phase 3, Exit).
- Rounds 012 to 014: cell status, provenance, the per-grade oracle environment, the run-based scoring output, the lost-run rule, record generations.
- `BENCHMARK.md` sections 4.4 and 5, and the root `AGENTS.md` (1000-line ceiling; behaviour and its documents change in one diff).
- The stored records under `runs/benchmarks` as the validation corpus for US3.
- For the runs: the benchmark launch runbook (dedicated Temporal, clean worktree, serial), the weak model of ruling R4, and user approval at each of R0 to R3.
