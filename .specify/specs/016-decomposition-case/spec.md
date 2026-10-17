# Feature Specification: Decomposition Case

**Feature Branch**: `016-decomposition-case`

**Created**: 2026-10-17

**Status**: Approved (GATE 1, 2026-10-17; all seven questions ruled as recommended, see Rulings). GATE 2 cleared 2026-10-17. A1 is approved as written: no frozen internal entry points, and FR-002 stands. A2 to A8 are approved as folded in, along with the pre-commit hook, the three environment variables, the double worker recreation and the cat-cafe chain-of-7 correction. Plan and tasks are approved. The requirement-list approval (GATE 2 item 2) is deferred by design to T015's stop, relayed by the orchestrator.

**Input**: Round 016, Phase 3 "Fix the corpus" of `docs/reports/2026-10-06-benchmark-improvement-plan.md` (Exit line: eight accepted cases, two of them private). The gap is named in `.specify/specs/015-corpus-acceptance/spec.md` (Q1, Out of Scope, Follow-ups) and in `BENCHMARK.md` sections 1 (limit 2), 3 and 5. Orchestrator task brief of 2026-10-17.

## Context

Round 015 closed at **1 of 8 accepted or provisional, 1 of 2 private**
(`BENCHMARK.md` 5.1, commit `f61261ba`). Cat-cafe-monitoring is the only
private case and the only case where the harness agrees with the public
model ordering (strong 0.833, weak 0.472, margin 0.361, one run per arm).
Deveval-geotext inverts the ordering (margin -0.556) and deveval-readtime
is a near-tie (margin 0.083). This round authors the second private
case and runs it under both arms, so the tally can reach **2 of 8, 2 of
2 private**. The six public cases still missing are round 017's.

The case has a second purpose: `BENCHMARK.md` limit 2 says planner
decomposition is not exercised, because every case is sized for a single
short run. The bar is E-27's: *large enough to require decomposition and
small enough to specify completely.*

**What the stored runs say about "require decomposition".** The planner
already splits small cases into many tasks. The stored plan of cat-cafe
run `bench-cat-cafe-monitoring-1792148180` has 10 tasks and a dependency
chain 7 tasks long (18 dependency edges) for a 186-line reference; the
weak-arm plan has 10 tasks, a chain of 6 and 16 edges (corrected at plan
review from "8"). The 015 DevEval runs reached
the code stage with 7 to 12 tasks each. So task count cannot show that a
case forces decomposition. ~~This spec defines the property as: how the
plan cuts the work changes the oracle result.~~ Amendment A1 corrects
this: the oracle cannot see the cut, so the case *exercises*
decomposition and does not force it. The case text fixes only the external
interface. The internal seams between components are left to the
planner, and the evidence shows how the plan cut the work (Q2, US5).

**Round 015 left storage to this round.** 015 Q7 committed cat-cafe's
oracle and reference to the repository (exposure `repo_public`) on the
condition that "private storage outside the repository is built in round
016, so the second private case is never published". The repository
`Kit-Kroker/Kroker` is public (checked 2026-10-17). The `isolated`
exposure value exists in `src/sdlc/benchmarks/acceptance.py`, but nothing
implements it. The cases root is one directory chosen by an environment
variable, which replaces the default rather than adding to it, and the
worker image bakes the in-repo cases in. The task brief says
`benchmarks/cases/<slug>/`. This spec follows 015's commitment instead
and puts the question to GATE 1 (Q1).

The round contains real pipeline runs. They are paid, run one at a time,
and each batch has its own user gate.

## Terms

Terms from 015 are used unchanged: arm, strong arm, weak arm, partial
credit, reference, oracle identity, role, visibility, exposure, lost run.
New terms:

- **Private store**: a location outside the public repository that holds the full directory of an `isolated` case. It is read together with the in-repo cases, not instead of them.
- **Seam**: an internal contract between two components of the produced program (data shape, call, shared state) that the case text does not fix.
- **Cross-component requirement**: a requirement whose oracle tests drive one externally visible flow through two or more components, so it passes only when the seams between them agree.
- **Requirement tier**: a tag on each requirement in the mapping. `basic` covers one component through its own interface. `rule` covers a stated business rule inside one component. `cross` is a cross-component requirement.
- **Plan shape**: for one run, read from its stored plan artifact: the number of tasks, the number of dependency edges, and the longest dependency chain.
- **Review record**: a dated file in the private store. It records the hand-verification of the oracle and the reference before any model run.

## User Scenarios & Testing

### User Story 1 - The case passes the offline acceptance half on its own (Priority: P1)

The benchmark owner runs the existing acceptance command on the new case
with no worker, no server and no model call. The reference passes every
oracle test and the empty tree passes strictly fewer.

**Why this priority**: an offline-green case is the smallest complete
deliverable. It is also the precondition for spending any run budget.

**Independent Test**: run the offline acceptance half on the new case and
read reference, floor and verdict `not_assessed`.

**Acceptance Scenarios**:

1. **Given** the case's reference, **When** the offline acceptance half runs, **Then** the reference passes every oracle test in the same fresh per-grade environment a real grade uses.
2. **Given** an empty tree, **When** the floor check runs, **Then** it passes strictly fewer tests than the reference, and the count is recorded.
3. **Given** the offline half, **When** it runs three times on the reference, **Then** all three results are identical, test by test.
4. **Given** the case manifest, **When** it is loaded, **Then** it states role `corpus`, visibility `private`, the round 015 strong and weak arms, a judge that shares no family with any arm, and its own scratch repository.

---

### User Story 2 - The oracle and the reference are verified by hand before any run (Priority: P1)

Before any model run, the benchmark owner can show that every oracle test
traces to the case text, fails when the behaviour it covers is missing,
and does not depend on a choice the text leaves free.

**Why this priority**: the oracle is the instrument. A wrong test spends
paid runs measuring the test, not the arms. PRDBench's figure of about
eight human hours per project is the budget this protects.

**Independent Test**: read the review record and re-run its mechanical
checks offline.

**Acceptance Scenarios**:

1. **Given** the requirement list, **When** it is approved by the user, **Then** no oracle test exists yet (approval comes first).
2. **Given** any requirement, **When** a variant of the reference with that requirement's behaviour removed is graded, **Then** at least one of that requirement's tests fails.
3. **Given** a second variant of the reference that changes every choice the case text leaves free (internal structure and seams, internal names, any parameter the text does not fix), **When** it is graded, **Then** it passes every oracle test.
4. **Given** any oracle test, **When** it is read, **Then** it reaches the product only through the interface contract in the case text.
5. **Given** the review record, **When** it is read, **Then** it names the reviewer, the date, the oracle identity reviewed, the result of each mechanical check, and the human hours spent on authoring and review.

---

### User Story 3 - The case's held-out material is never published (Priority: P1, if Q1 is answered "isolated")

The case lives in the private store. Every reader of cases finds it there:
the run command, the worker, the judge, the oracle, the acceptance
command and the corpus status. Nothing that identifies its tests or
requirements reaches the public repository.

**Why this priority**: it is the condition 015 attached to publishing
cat-cafe. A research-enabled run can in principle find a published oracle
(015 Follow-ups, research egress).

**Independent Test**: with the private store present, list the corpus and
start the case's offline check. With it absent, run the fast test tier
and the corpus status and see the in-repo cases behave as before.

**Acceptance Scenarios**:

1. **Given** a private store holding the case, **When** the corpus status is printed, **Then** the case is listed with exposure `isolated` beside the in-repo cases.
2. **Given** no private store, **When** any benchmark command runs, **Then** in-repo cases behave exactly as today, and the corpus status says the private store is absent.
3. **Given** a case id present both in the repository and in the private store, **When** any case is loaded, **Then** loading fails and names both locations.
4. **Given** a run of the private case, **When** the worker grades it, **Then** it reads the oracle from the private store, and nothing from the case's `oracle/` or `reference/` reaches the run's worktree or any prompt.
5. **Given** the round's diff, **When** it is searched, **Then** it contains none of the case text, requirement list, test names, test code or reference code of the private case.
6. **Given** a worker that cannot see the private store, **When** the private case is started, **Then** the run stops before any model call and says the store is missing.

---

### User Story 4 - The case reaches a corpus verdict after a cleared run batch (Priority: P2)

After the user clears the batch, the case is run once under the strong
arm and once under the weak arm. The acceptance command then records a
verdict.

**Why this priority**: this produces the tally. It is paid and gated, and
it is the first part to cut if the user stops early.

**Independent Test**: after the batch, read the case's acceptance record
and the corpus tally.

**Acceptance Scenarios**:

1. **Given** one graded run per arm with a margin of 0.15 or more, **When** acceptance runs, **Then** the verdict is `provisional`, and the tally reads 2 of 8 accepted or provisional, 2 of 2 private.
2. **Given** a margin under 0.15, a weak arm above the strong arm, or a strong arm at 1.0 or 0.0 on every graded run, **When** acceptance runs, **Then** the 015 rejection reason is recorded with both means. The round reports it as it came out.
3. **Given** a lost run, **When** it is recorded, **Then** that arm is run once more after its own clearance. A second lost run leaves that arm without data and the verdict `not_assessed`.
4. **Given** the batch, **When** it is cleared, **Then** the estimate shown names runs, wall clock and dollars, and nothing else runs on the machine while it executes.

---

### User Story 5 - The closing report shows whether decomposition was exercised (Priority: P3)

The closing report puts each run's plan shape next to cat-cafe's, and the
oracle result per requirement tier per arm. A reader can see whether the
plans cut the work along the seams, and where each arm lost credit.

**Why this priority**: this is the evidence for the case's second purpose.
It is read from stored artifacts and costs no run.

**Acceptance Scenarios**:

1. **Given** the stored plan artifact of each run, **When** the report is written, **Then** it gives the plan shape of each run and of the stored cat-cafe runs.
2. **Given** the per-requirement oracle results, **When** the report is written, **Then** it gives partial credit per tier (`basic`, `rule`, `cross`) per arm, each with its denominator.
3. **Given** the report, **When** it is read, **Then** it names no test and quotes no requirement text of the private case.

---

### Edge Cases

- **Plan validation loss.** Deveval-particle-swarm-optimization was lost twice at plan validation (dangling task dependencies). A larger plan raises that risk. Such a run is a lost run and falls under US4 scenario 3.
- **Harness time limit.** A larger case means larger tasks. A task that hits the harness time limit is an ordinary failed attempt, not a defect of the case.
- **Judge output limit.** The planner rubric judge already fails on cat-cafe's plans ("Model token limit (provider default) exceeded before any response was generated", both 015 R2 runs). A larger plan makes this more likely (Q3).
- **Weak arm wins.** Rejected with `no_separation`, both means recorded (the geotext precedent). The oracle is not edited to reverse it.
- **Oracle defect found after a run.** The fix changes the oracle identity. Earlier runs become not comparable and are kept. A re-run needs a new clearance.
- **Fresh clone or CI.** No private store: the in-repo corpus and every existing test behave as today.
- **Stored-score test pins.** The fast tier reads every record under the shared runs root. New runs must not break pinned figures of other cases (the 015 contamination lesson).
- **Research stage.** Disabled for this case (A2). It could not find the oracle anywhere public, but it would send the case text to search providers, cost about a third of a run's dollars, and could end a run (4 of 18 early cat-cafe runs ended there).
- **Requirement with several tests, some passing.** Counted as failed in the root-cause view (015 default). Its partial score is kept.

## Requirements

### Functional Requirements

**The case**

- **FR-001**: The round MUST add exactly one new case, with role `corpus`, visibility `private`, the round 015 arm pair (strong `zai-coding-plan-glm-5.3-flash`, weak `zai-coding-plan-glm-5.2`), the judge `anthropic:claude-sonnet-5`, opencode as harness, and a scratch repository of its own.
- **FR-002**: The case text MUST describe at least four features, each delivered by its own component. It MUST freeze only the external interface contract (the cat-cafe device). It MUST leave every internal seam to the implementer and say so.
- **FR-003**: The case text MUST be complete for every behaviour the oracle asserts. A rule the oracle checks is stated in the text with its values. Anything else is the implementer's choice, and no test may depend on it.
- **FR-004**: The interface contract MUST be gradable with no network, no wall clock and no randomness. Time comes from caller-supplied timestamps, as in cat-cafe. Importing the program MUST start nothing.
- **FR-005**: The reference MUST be between 500 and 1,500 non-blank lines of code over at least four modules. Cat-cafe's reference is 186 lines.
- **FR-006**: The oracle MUST hold 40 to 60 tests over 15 to 25 requirements. Each test belongs to exactly one requirement. Each requirement has an error class (the existing six) and a tier.
- **FR-007**: The tier spread MUST leave no guaranteed zero and no easy saturation. At least 25% of the tests are `basic`, at least 20% of the requirements are `cross`, and every feature has at least one `rule` requirement.
- **FR-008**: The case MUST ship the same file set cat-cafe ships: manifest, oracle with its own dependency list, reference, requirement mapping, acceptance record, and rubrics (clarifier, architect, planner, qa). The planner rubric scores the plan against the case's seams.

**Authoring and hand-verification (before any model run)**

- **FR-009**: The requirement list MUST be approved by the user before any oracle test is written (015 R9 precedent). It is stored with the case, not in this public spec directory.
- **FR-010**: The offline acceptance half MUST be green: reference 100%, floor strictly below.
- **FR-011**: For every requirement, a variant of the reference with that requirement's behaviour removed MUST fail at least one of its tests (ablation check).
- **FR-012**: A second variant of the reference that changes every free choice MUST pass every test (free-choice check). FR-003 is proven this way, not by reading alone.
- **FR-013**: The oracle run on the reference MUST give identical results three times in a row.
- **FR-014**: A person MUST read the case text, the requirement list and every test, and record the result in the review record with the oracle identity reviewed. The record MUST also carry the outcomes of FR-010 to FR-013 and the human hours spent.
- **FR-015**: No paid run of the case MAY start until FR-010 to FR-014 are done for the oracle identity being run.

**Storage (if Q1 is answered "isolated")**

- **FR-016**: An `isolated` case MUST live whole in the private store: manifest, case text, oracle, reference, mapping, rubrics, acceptance record and review record.
- **FR-017**: Every reader of case files MUST resolve cases from the in-repo root and the private store together, through the one resolution point that exists today. A case id present in both MUST be an error naming both.
- **FR-018**: With no private store configured or present, every in-repo behaviour, command and test MUST be unchanged.
- **FR-019**: The worker MUST read the private store at run time without the store entering the worker image. A run of a private case on a worker that cannot see it MUST stop before any model call.
- **FR-020**: Changes to the private store MUST be version-controlled outside the public repository, so that every change to the instrument is a reviewable diff.
- **FR-021**: Nothing committed to the public repository in this round MAY contain the private case's text, requirement list, test names, test code or reference code. The case id, its role, visibility, exposure, verdict, means, margin and run counts MAY be published (as cat-cafe's are in `BENCHMARK.md` 5.1).
- **FR-022**: The existing proof that no file of a case's `reference/` reaches a run's worktree or prompt MUST also cover a case in the private store.

**Run batch**

- **FR-023**: Batch R1 MUST be one run under the strong arm and one under the weak arm, one at a time, after the user clears it with the estimate shown. R0 (smoke) runs before it whenever the commit under test differs from the last passing smoke stamp.
- **FR-024**: A lost run MAY be repeated once per arm, each repeat cleared on its own.
- **FR-025**: Every run MUST follow the standing rules: smoke stamp for the commit, clean tree, the case's own scratch repository, the compose worker rebuilt on the commit under test with its commit stamped, nothing else running on the machine.
- **FR-026**: After the batch, the acceptance command MUST record the verdict. The oracle MUST NOT be changed in response to the arms' scores. Only a defect shown against the case text may change it, and that change starts a new oracle identity.

**Reporting**

- **FR-027**: The closing report MUST state the tally "N of 8 accepted or provisional, M of 2 private" from the acceptance records of both roots.
- **FR-028**: The closing report MUST give the plan shape of each run beside the stored cat-cafe plans, and partial credit per tier per arm with denominators. It MUST name no test and quote no requirement of the private case.
- **FR-029**: `BENCHMARK.md` (section 5: the private store, the new case's corpus row, how to run a private case) MUST change in the same diff as the behaviour. Nothing under `docs/reports/` may be edited, staged or committed.
- **FR-030**: Stored records MUST NOT be rewritten, re-graded or deleted.

### Key Entities

- **Case** (existing): gains exposure `isolated` as a real location.
- **Private store**: a second cases location outside the public repository, under its own version control.
- **Requirement mapping** (existing per-case task file): gains a tier per requirement.
- **Review record**: reviewer, date, oracle identity, outcomes of the four mechanical checks, hours spent.
- **Plan shape**: tasks, edges and longest chain per run, derived from the stored plan artifact.

## Run Gates and Estimate

Measured on the stored records: cat-cafe ran a mean of 3.4 h (max 4.7 h)
at $1.91 and 2.2M tokens per run. Code-stage dollars are $0 on the
subscription; the dollars go to research and judging. This case has a
reference 3 to 8 times larger, so the figures below are estimates.

| Gate | Batch | Runs | Wall clock | Dollars |
|---|---|---|---|---|
| R0 | smoke: todo-api once (the storage code moves the commit) | 1 | about 1.6 h | about $1.6 |
| R1 | new case, strong arm then weak arm, research off (A2) | 2 | 6 to 9 h | $2 to $4 |
| R1-retry | one repeat per lost arm, each cleared on its own | 0 to 2 | 3 to 4.5 h each | $1 to $2 each |
| | Total | 3 to 5 | 8 to 20 h | $4 to $10 |

(Restated by amendment A7 from the 015 R2 cat-cafe records: 2.9 h and 3.2 h, about $1.0 to $1.2 of stage dollars per run, of which research was $0.71 and $0.79.)

## Success Criteria

- **SC-001**: The offline acceptance half of the new case is green (reference passes every test, floor strictly fewer) with no worker, no server and no model call, and it gives identical results on three consecutive runs.
- **SC-002**: The review record exists for the oracle identity that is run. Every requirement passes the ablation check, the free-choice variant passes 100%, and the hours spent are recorded.
- **SC-003**: The oracle holds 40 to 60 tests in 15 to 25 requirements and meets the tier spread of FR-007. The reference is 500 to 1,500 non-blank lines over at least four modules.
- **SC-004**: (Q1 "isolated") Zero lines of the private case's text, requirement list, tests or reference are in any commit of the public repository. With no private store, the fast test tier gives the same result as on `f61261ba`.
- **SC-005**: (If R1 runs) the case has one graded run per arm and a recorded verdict. The closing report states the tally from the records; the target is 2 of 8, 2 of 2 private.
- **SC-006**: (If R1 runs) the closing report gives the plan shape of every run and partial credit per tier per arm, with denominators.
- **SC-007**: No `accepted` verdict is recorded on fewer than three graded runs per arm, and no oracle change follows a score.

## Rulings (GATE 1, user, 2026-10-17)

All seven open questions were answered as recommended.

- **R1 (Q1)**: isolated. The whole case lives in a private store outside the repository, under its own local git history, read alongside the in-repo cases. No off-machine backup is assumed. **Orchestrator caveat:** the plan MUST check in code that a private store can be read alongside the in-repo cases (today the `SDLC_CASES_ROOT` override replaces the default) without deep rework. The claim "`isolated` exists in the code but nothing implements it" is a hypothesis for the plan to confirm, or else to scope explicitly. If the mechanism needs new code, it is a plan task of its own with a test command.
- **R2 (Q2)**: proof by construction plus post-run evidence (plan shape, partial credit per tier per arm). No new gate. Separation is not claimed to measure decomposition.
- **R3 (Q3)**: the planner rubric judge is fixed in this round as a bounded code task, proven offline on a stored cat-cafe plan artifact.
- **R4 (Q4)**: raw opencode stream capture on the R0 smoke run only, scrubbed before commit. The parser is out of scope.
- **R5 (Q5)**: the domain is a theatre box office. The requirement list is approved at GATE 2.
- **R6 (Q6)**: the crew drafts the case. The user approves the requirement list before any test exists and reads every test for the review record.
- **R7 (Q7)**: R0 when the commit moves, then R1 with one run per arm. One repeat per lost arm, cleared on its own. A rejection is reported as it came out, with no repair-and-rerun.

## Amendments after GATE 1 (plan, 2026-10-17; listed for GATE 2)

Each was checked in the code or on the stored records before the spec
changed. Consults: advisor `.workspace/tmp/advisor-016-1.md`, skeptic
`.workspace/tmp/skeptic-016-1.md`. I verified the skeptic's answer claim
by claim, because several of its figures were wrong (see plan, Consults).

- **A1 (Context, R2, Terms): "exercises", not "forces".** In the stored strong-arm cat-cafe run (`bench-cat-cafe-monitoring-1792148180`), the retry of task T-01 wrote every application module (`app.py`, `detection.py`, `risk.py`, `state.py`, `zones.py`, ...). Its plan drift records them all as touched-unhinted. Every task branches from the integration branch, sees the whole tree, and may write anywhere (file hints are advisory). The oracle sees only the external interface. So **no case design can make the oracle penalise a bad cut**. That would take a pipeline property (fenced tasks), which is out of scope. The construction (FR-002, FR-007) makes the case *exercise* decomposition: there is multi-component work for the planner to cut and sequence. The evidence (US5, plus plan drift per task) shows how it was cut. The sentence "a set of requirements can only pass when separately built components agree on those seams" is withdrawn as a claim about the plan. It stays true of the produced program. R2's "no new gate" and "separation does not measure decomposition" are unchanged. The skeptic's alternative is a two-layer contract that also freezes component entry points and tests each component in isolation. It is not taken: it would fix the seams in the case text, which is the opposite of FR-002, and a single task could still write all the frozen modules. It is item 1 for GATE 2.
- **A2 (Defaults): research disabled for this case.** The default "research enabled, as for cat-cafe" is reversed. Research sends the case text into queries to external search providers. It is about a third of a run's dollars (cat-cafe R2: $0.71 and $0.79 of about $1.0 to $1.2 of stage dollars). It is one cause of lost runs, and an invented kata has nothing public to research. Separation compares arms within a case, so cat-cafe comparability is not needed. The research rubric is not registered for this case.
- **A3 (FR-006, FR-007): the mapping gains `feature` beside `tier`.** "Every feature has at least one `rule` requirement" cannot be checked without it. Both fields are optional and default to none, so every existing mapping loads unchanged. A suite that sets `tier` on one requirement must set it on all. The FR-005 to FR-007 bounds are checked by a store-side script, not by the loader.
- **A4 (FR-017): some consumers stay on the in-repo root on purpose.** Prompt eval fixtures, calibration (keyed by rubric, not case) and the smoke case stay there. So do root-cause labels: their path is the sibling of the primary cases root, and nothing routes them per root. **Labelling the private case is unsupported this round.** Its failed requirements show as `unattributed` in the root-cause view. No label for it is written anywhere, and above all not under `benchmarks/labels/`, because labels name requirement ids.
- **A5 (FR-019): how a worker without the store stops.** The case registers rubrics (FR-008). The first activity of a benchmark run already refuses missing registered rubric files, non-retryably and at zero model spend. On a worker that cannot see the store, the case resolves to no directory and that check fires. The plan adds the cause to its message: the case is in no cases root, and whether a private root is configured. No new always-on check is added, because existing tests load assets for case ids that do not exist.
- **A6 (Run gates): one commit under test.** Every code change of this round is merged before R0: storage, the judge fix, stream capture, the leak guard, the report script, and the documents for running a private case. Any later commit would invalidate the smoke stamp the run gate demands. R0 and R1 run on that commit. Authoring and fixing the case happen in the private store and never move it. The captured stream fixture, the tally and the corpus row are committed after the last run (015 A5 precedent).
- **A7 (Run Gates and Estimate): restated from the stored records.** The two 015 R2 cat-cafe runs took 2.9 h and 3.2 h, with about $1.0 to $1.2 of stage dollars, of which research was $0.71 and $0.79. With research off and a larger case: R1 is about 6 to 9 h and $2 to $4 for two runs. With R0 the round is about 8 to 11 h and $4 to $6, plus up to two repeats at about 3 to 4.5 h and $1 to $2 each.
- **A8 (FR-025): runs start from a clean detached worktree** of the merged commit, with absolute records and ops roots in the primary checkout (015 GATE 2 item 10). The run gate refuses a tree with untracked files, and the primary checkout always holds the user's own files.

## Open Questions as put to GATE 1 (resolved above)

Each question had a recommendation, and the spec is written to it.

- **Q1 — Where does the case live?** The brief says `benchmarks/cases/<slug>/` in this repository. 015 Q7 published cat-cafe on the condition that this round builds private storage so the second private case is never published. The repository is public. Options: **(A) isolated**: the whole case directory in a private store outside the repository, under its own local git history, read alongside the in-repo cases. This costs a resolution change in the one cases-location function, a worker bind mount, and an absent-store path for CI. **(B) split**: manifest in the repository, held-out files outside. Rejected: the mapping and acceptance record name every test, so the split leaks the oracle anyway. **(C) in the repository**, exposure `repo_public`, as cat-cafe. No storage code, but it breaks 015's condition and a research-enabled run can find the oracle. **Recommendation: A.** Whether the private store also gets an off-machine backup (for example a private remote) is the user's call. It is outward-facing and is not assumed.
- **Q2 — What shows that the case forces decomposition?** Task count cannot: the planner already gives cat-cafe 10 tasks and a chain of 7 (put to GATE 1 as "8"; corrected at plan review). **Recommendation: by construction plus evidence, no new gate.** By construction: internal seams are left free (FR-002), and at least 20% of the requirements are cross-component (FR-007). Evidence after the runs: plan shape, and partial credit per tier per arm (US5). The acceptance separation compares harness models. The planner is the same model in both arms, so separation cannot measure decomposition quality. This spec does not claim that it does.
- **Q3 — Fix the planner rubric judge in this round?** On both 015 R2 cat-cafe runs the planner rubric produced no score (the judge hit its output limit). This case's planner rubric would be blind the same way. **Recommendation: yes, as a bounded code-half item.** Diagnose and fix it, and prove the fix offline on a stored cat-cafe plan artifact (a few judge calls, no pipeline run). The alternative is to accept a blind planner lens and rely on US5 alone.
- **Q4 — Capture raw opencode streams for FR-041 (plan task 2.8) during this round's runs?** A stream from the private case's runs would carry the private case text and code. Committed as a fixture, it would publish them. **Recommendation: capture only, and only on the R0 smoke run (todo-api, already public), scrubbed before commit. The parser itself stays out of this round.** The alternative is to defer capture to a later round.
- **Q5 — The domain.** It must fit FR-002 to FR-007: Python, gradable through a small HTTP interface like cat-cafe's, deterministic, at least four components with real seams. Candidates: **(A) theatre box office**: shows, a seat map, seat holds that expire at caller-supplied times, purchases with price tiers and discounts, exchanges and refunds that release seats, and a sales report that must reconcile with every sale. **(B) tool library**: catalogue, members, reservations, checkouts, maintenance holds after a number of uses, late fees, waitlist promotion on return, a usage report. **(C) courier dispatch**: couriers, orders, zones, assignment, a delivery status machine, time-limit breaches from timestamps, payouts, a daily ledger. **Recommendation: A.** It has the most cross-component flows (an exchange touches holds, pricing, sales and the report), and its rules can be stated completely. The requirement list is approved at GATE 2 either way.
- **Q6 — Who authors, and who verifies by hand?** **Recommendation: the crew drafts the case text, oracle and both reference variants. The user approves the requirement list before any test is written (FR-009) and reads every test for the review record (FR-014).** The mechanical checks are run by the crew and re-run at review. Authoring agents send the private material to their model providers. That is not publication, and this spec accepts it. The alternative is to keep authoring seats off the z.ai models under test.
- **Q7 — The run batch and a rejection.** **Recommendation: R0 when the commit moves, then R1 (one run per arm, about 10 to 14 h and $6 to $8 with R0), one repeat per lost arm cleared on its own. A rejection is reported as it came out, with no repair-and-rerun this round.** Editing an oracle after seeing which arm won fits the instrument to the arms. A defect shown against the case text is the only reason to change the oracle, and the re-run then needs its own clearance.

## Assumptions

**Verified in the tree (main `f61261ba`, 2026-10-17)**

- No `.specify/specs/016-*` existed; 016 is free.
- Cat-cafe case anatomy: `case.yaml` (role, visibility, strong_arm, weak_arm, two arms differing only in dev/test/devops models, research enabled, opencode, judge `anthropic:claude-sonnet-5`, scratch repo under `/srv/scratch-repos/`), `oracle/` (36 tests in three files plus `requirements.txt`), `reference/app.py` (186 lines), `tasks.yaml` (15 requirements, each with an error class), `acceptance.yaml` (`provisional`, margin 0.361), five rubrics and two veto files.
- The acceptance rule and verdicts are those of `BENCHMARK.md` 5.1 and `src/sdlc/benchmarks/acceptance.py` (margin 0.15, three runs per arm for `accepted`). `Exposure` already admits `isolated`, but nothing sets it.
- `cases_dir()` in `src/sdlc/benchmarks/paths.py` is the single resolution point. It returns one directory, so the override replaces the default. The worker image sets that override to the baked-in `/app/benchmarks/cases`.
- `runs/` is git-ignored. Plan artifacts are stored per run under `runs/pipeline/<bench run>/<cell>/artifacts/plan-v*.json` with `depends_on` per task, so plan shape is derivable offline.
- The stored cat-cafe plan (run `...1792148180`, `plan-v25.json`) has 10 tasks, 18 dependency edges and a longest chain of 7 nodes (T-01, T-02, T-05, T-07, T-08, T-09, T-10). The weak-arm plan (`...1792137753`, `plan-v24.json`) has 10 tasks, 16 edges and a chain of 6. The 015 DevEval runs that reached code had 7 to 12 tasks. (Corrected at plan review; the first draft said 8.)
- The planner rubric score is null with judge `error` on both 015 R2 cat-cafe runs, reason: model output limit exceeded before any response.
- The repository is public (`gh repo view`: PUBLIC).

**Not verified — the plan must establish**

- Whether the judge, the oracle runner and the acceptance command all reach case files only through `cases_dir()`, or whether a direct path survives somewhere.
- Whether the worker container can take a second read-only bind mount without a change to the compose project pattern of the runbook.
- Why the planner judge hits its output limit, and whether the fix is a setting or a prompt change (Q3).
- How long a run of a case this size takes, and whether the harness time limit per task fits it.
- Whether the shared runs root contamination of stored-score test pins (015) recurs with new records.

**Defaults taken**

- Language Python, graded through an ASGI application object (the cat-cafe contract form), because that grading path is proven end to end.
- ~~Research enabled, as for cat-cafe.~~ Reversed by amendment A2: research disabled.
- The empty-tree floor is expected to be 0 tests, as for cat-cafe.
- Authoring follows PRDBench's shape (agent drafts, human review loop). The hours actually spent are recorded rather than budgeted.

## Out of Scope

- Brownfield and multi-language cases (toolchain adapters).
- Public corpus expansion (round 017).
- Phase 4: calibration, the three-to-five-run baseline, paired comparison. `accepted` needs three runs per arm and is not a target here.
- Moving cat-cafe to the private store. Its tests are in the public history for good (015 Q7).
- The opencode session parser (FR-041 itself). Only stream capture is in question (Q4).
- An automatic root-cause labeller, a batch runner, web console changes.
- Editing, staging or committing anything under `docs/reports/`.

## Dependencies

- Round 015: case roles, visibility, exposure, the acceptance command and record, oracle identity, the smoke stamp and run gate, the `--arm` selector, the root-cause view, the reference-isolation proof.
- Rounds 012 to 014: per-grade oracle environment, cell status, provenance, run-based scoring output.
- `BENCHMARK.md` sections 1, 4.4, 5 and 5.1; root `AGENTS.md` (1000-line ceiling; behaviour and its documents change in one diff).
- Ops facts from 015: one run at a time, per-batch user clearance, compose worker on the live Temporal, rebuilt with its commit on every re-pin, per-case scratch repository before dispatch, host `.env` sourced for acceptance, lost runs exit 0 (read the report).
