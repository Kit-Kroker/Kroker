# Feature Specification: Benchmark Scoring Output Rework

**Feature Branch**: `013-benchmark-scoring-output`

**Created**: 2026-10-09

**Status**: Approved (GATE 1, 2026-10-09)

**Input**: User description: "Round 013, Phase 2 of `docs/reports/2026-10-06-benchmark-improvement-plan.md`: rework the benchmark scoring output so that the scores read correctly on the records round 012 made trustworthy: composite dropped until a case has at least two arms; heatmap rebuilt as layers on shared stage columns (attrition, first-attempt failure rate, wasted tokens, oracle per run) with fixed colour scales, denominators shown, cells greyed under five observations; run-by-run grid as the main view grouped by commit and arm with mean and spread on top; oracle column showing partial credit beside the all-pass rate; gate-versus-oracle agreement and escape rate per gate; first-attempt and after-repair scores as separate columns; success-criteria rollup scoped to the case being scored; opencode session parsing so the waste counters are populated; erosion and verbosity computed on the integration branch after each run."

## Context

Round 012 (Phase 1) made the records the harness writes trustworthy. The
output that reads those records still misleads: it sums one failure into
three counts, hides the runs that never reached code, colours every grid
against its own maximum, shows a composite that compares a cell with
itself, reports attempts where it should report tasks, and fills the
success-criteria section from pipeline runs that have nothing to do with
the case being scored.

This round delivers Phase 2 of the report's plan, tasks 2.1 to 2.8. Task
2.9 is its own round by ruling R1 (see Rulings and Follow-ups). It changes what the
score command and the end-of-run report show. It adds no benchmark runs
and rewrites no stored record. The reader of a score — the person deciding
whether a change to Kroker helped — is the user of this feature.

The round is validated on the records already on disk: 1,249 pre-012
records in 41 run directories, plus the three todo-api runs round 012
wrote.

## Terms

- **Run**: one execution of one cell (a case under one harness and one arm).
- **Lost run**: a run that ended before its code stage finished. It has no grade. Whether the case has an oracle does not matter: a run of a case without an oracle that ended before code is lost, not "without oracle".
- **Graded run**: a run whose code stage finished and whose oracle returned a result.
- **Observation**: the unit a cell counts. Each layer names its own.
- **Record generation**: pre-012 (no provenance) or 012 (provenance recorded). Never mixed in one aggregate (round 012 ruling R3).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every run is counted once and lost runs are visible (Priority: P1)

Someone scores a case. The output states how many runs were started, how
many were lost and at which stage, and how many were graded. Quality
figures are computed over graded runs only. All records of one run land in
one row under one arm, whichever generation wrote them.

**Why this priority**: this is the round's exit criterion. Today the
cat-cafe score shows 0.421 because eight lost runs count as zero, shows
research as its coolest cell although four runs ended there, and splits
one cell across up to four rows.

**Independent Test**: score `cat-cafe-monitoring` on the stored records
and read the totals line and the arm rows.

**Acceptance Scenarios**:

1. **Given** the stored cat-cafe records, **When** the case is scored, **Then** the output states 18 runs started, 8 lost before code (4 with research as the last stage, 4 with clarify) and 10 graded.
2. **Given** a pre-012 run that has no recorded status, **When** it is scored, **Then** its status is derived from its own stage records by the same rule round 012 applies when writing, and the output marks the status as derived.
3. **Given** a lost run that carries a stored oracle record (a pre-012 artifact), **When** the case is scored, **Then** that oracle record enters no mean, rate or colour, and the output counts it as discarded.
4. **Given** a pre-012 run whose records were stored under several labels, **When** the case is scored, **Then** the run appears as one run of one arm.
5. **Given** any selection of runs, **When** it is scored, **Then** started = graded + lost + grading failed + no oracle, and every run appears in exactly one row.
6. **Given** pre-012 and 012 runs of the same case and arm, **When** the case is scored, **Then** they are shown in separate groups and no figure averages across them.

---

### User Story 2 - The run-by-run grid is the main view (Priority: P1)

The first thing a score shows is a grid with one row per run. Runs are
grouped by arm and by the Kroker commit that produced them. Each group is
headed by the mean and spread of its graded runs. Reading down a group
shows the variance; reading across a row shows where that run went.

**Why this priority**: with one arm and a few runs per commit, an average
hides the only thing the data can show. Round 012 put the commit on every
record so that runs can be grouped by it.

**Independent Test**: score a case that has runs from two commits and
confirm two groups, each with its own header, and one row per run.

**Acceptance Scenarios**:

1. **Given** a scored case, **When** the report is opened, **Then** the run-by-run grid is the first section, ahead of every aggregate table.
2. **Given** runs from two commits under one arm, **When** the case is scored, **Then** they form two groups; runs with no recorded commit form their own group labelled as not recorded, and runs recorded with an unknown commit form another.
3. **Given** a group with graded runs, **When** its header is rendered, **Then** it shows runs started, runs graded, the mean partial credit, the standard deviation, the lowest and highest value, and the all-pass rate.
4. **Given** a group with fewer than five graded runs, **When** its header is rendered, **Then** the figures are shown in grey with their count; with one graded run the standard deviation reads n/a.
5. **Given** a run row, **When** it is read, **Then** it shows the run's status, the last stage it reached, what happened at each stage it reached, its oracle result, its first-attempt and after-repair scores, its tokens and its wall-clock time.
6. **Given** a run started from a tree with uncommitted changes, **When** its row is rendered, **Then** the row says so.
7. **Given** the records of one benchmark run, **When** they are scored by the score command and by the end-of-run report, **Then** both show the same figures.

---

### User Story 3 - The heatmap is four layers on the same stage columns (Priority: P1)

The heatmap no longer adds different kinds of events into one number. It
is four grids stacked on identical stage columns: where runs were lost,
how often a first attempt failed, how many tokens went to work that was
thrown away, and what the oracle said about each run. Colours come from a
fixed scale, every cell prints its denominator, and a cell with fewer than
five observations is grey.

**Why this priority**: the summed heatmap counts one failed attempt three
times and makes two reports incomparable because each is coloured against
its own maximum.

**Independent Test**: build the heatmap from a fixture where one task
fails its first attempt and passes its second, and confirm the failure
appears once in each layer it belongs to and nowhere else.

**Acceptance Scenarios**:

1. **Given** a task that fails its first attempt and passes its second, **When** the heatmap is built, **Then** the first-attempt layer counts one failed first attempt for that task, the wasted-tokens layer counts the tokens of the first attempt, and no other cell changes.
2. **Given** four layers, **When** they are rendered, **Then** all four have the same stage columns in the same order, and the order is the pipeline's.
3. **Given** two reports built from different data, **When** a cell has the same value in both, **Then** it has the same colour in both.
4. **Given** a cell with a denominator of four, **When** it is rendered, **Then** it is grey and still prints its value and denominator.
5. **Given** a stage with no observation in a layer, **When** it is rendered, **Then** the cell is blank, distinct from grey and from a zero.
6. **Given** the stored cat-cafe records, **When** the attrition layer is rendered, **Then** the research and clarify columns carry the lost runs and no later column does.
7. **Given** a run lost inside the per-task loop, **When** the attrition layer is built, **Then** it is counted once, in the code column.

---

### User Story 4 - The oracle reads as partial credit beside the all-pass rate (Priority: P2)

Wherever the oracle result is shown, two figures stand side by side: the
share of held-out tests a run passed, and the share of runs that passed
all of them. A run that passes 11 of 12 no longer reads the same as one
that passes none.

**Why this priority**: the binary oracle column discards the progress of
nine of the ten graded cat-cafe runs.

**Independent Test**: score a case with one all-pass run and one 11-of-12
run and read both figures.

**Acceptance Scenarios**:

1. **Given** a graded run, **When** its oracle result is shown, **Then** it reads as tests passed over tests total.
2. **Given** a group of graded runs, **When** its oracle summary is shown, **Then** mean partial credit and the all-pass rate appear together, each with its count.
3. **Given** the stored cat-cafe records, **When** the case is scored, **Then** mean partial credit is 0.708 (85 of 120 tests over 10 runs) and the all-pass rate is 1 of 10.
4. **Given** a run whose grade could not be produced, **When** it is shown, **Then** it reads as grading failed and enters neither figure.

---

### User Story 5 - First-attempt and after-repair scores are separate columns (Priority: P2)

For the code stage the output shows two figures per run and per group:
the share of tasks that passed on their first attempt, and the share that
passed by the end of the fix loop. Neither is called quality, and neither
is a share of attempts.

**Why this priority**: the present code "quality" of 0.725 is the share of
attempts that passed. It answers no question anyone asks, and it hides
how much the fix loop contributes.

**Independent Test**: score a fixture with three tasks, one of which
passes on its second attempt and one of which never passes.

**Acceptance Scenarios**:

1. **Given** three tasks where one passes first time, one passes on the second attempt and one never passes, **When** the run is scored, **Then** the first-attempt score is 1 of 3 and the after-repair score is 2 of 3.
2. **Given** the stored cat-cafe records, **When** the case is scored, **Then** the first-attempt score is 84 of 113 tasks and the after-repair score is 111 of 113.
3. **Given** a stage whose record carries a pass/fail verdict and no rubric score, **When** it is shown in a summary table, **Then** it is shown as a pass rate with its denominator and never in the quality column.
4. **Given** a pre-012 qa verdict, which is a copy of the code verdict, **When** any view is rendered, **Then** it is marked as a copy and is not counted as an observation of its own.

---

### User Story 6 - Each gate is compared with the oracle (Priority: P2)

For every gate the output shows how often its verdict agreed with the
oracle, how much of what it let through the oracle then failed (the escape
rate), and how much of what it rejected the oracle would have passed.

**Why this priority**: the analyze and merge gates rejected every graded
cat-cafe run. Round 012 ruled those rejections correct on their own terms.
Whether a gate's verdict predicts the oracle is the question that decides
if the gate earns its cost.

**Independent Test**: score a fixture of four runs covering the four
combinations of gate verdict and oracle verdict.

**Acceptance Scenarios**:

1. **Given** four runs covering pass/pass, pass/fail, reject/pass and reject/fail, **When** the agreement view is built, **Then** agreement is 2 of 4, the escape rate is 1 of 2 passed runs and the false-reject rate is 1 of 2 rejected runs.
2. **Given** a gate that passed no run, **When** its escape rate is shown, **Then** it reads n/a with a denominator of zero.
3. **Given** the stored cat-cafe records, **When** the case is scored, **Then** analyze shows 10 of 10 graded runs rejected, one of them a run that passed every oracle test; merge shows 7 rejected (one of them that same run) and 3 passed, all 3 of which the oracle failed.
6. **Given** a merge verdict recorded as passed with waived advisory checks, **When** the view is built, **Then** it counts as a pass of the merge gate.
4. **Given** a gate recorded as not evaluated for a run, **When** the view is built, **Then** that run enters none of the gate's counts.
5. **Given** a lost run, **When** the view is built, **Then** it enters no gate's counts.

---

### User Story 7 - No composite until a case has two arms (Priority: P2)

A case with a single arm shows no composite score anywhere. When a case
has at least two arms with graded runs, the composite returns and compares
the arms with each other.

**Why this priority**: on one cell the composite normalises a cell's cost
and speed against that cell's own slowest record. It gave the analyze
stage 0.196 with quality 0.0.

**Independent Test**: score a one-arm case and a two-arm fixture.

**Acceptance Scenarios**:

1. **Given** a case with one arm, **When** it is scored, **Then** no output shows a composite, and the report says in one line why.
2. **Given** a case with two arms that each have a graded run, **When** it is scored, **Then** a composite is shown per arm, with cost and speed normalised across the arms.
3. **Given** composite weights passed on the command line for a one-arm case, **When** it is scored, **Then** the command succeeds and says the weights were not used.

---

### User Story 8 - Success criteria are scoped to what is being scored (Priority: P2)

The success-criteria section of a case's score is computed from that
case's runs only. It says how many of them it could read.

**Why this priority**: today the section is filled from every pipeline
run on the machine. On the stored data that is 79 runs, none of them a
run of the case being scored.

**Independent Test**: score one case with run summaries present for some
of its runs and for unrelated pipeline runs.

**Acceptance Scenarios**:

1. **Given** run summaries for the scored case and for unrelated pipeline runs, **When** the case is scored, **Then** only the scored case's runs enter any criterion.
2. **Given** a scored case where some runs left no summary, **When** the section is rendered, **Then** it states how many of the case's runs had one.
3. **Given** the stored cat-cafe records, **When** the case is scored, **Then** the summary-based criteria read n/a with zero runs, and no bf-e2e run contributes.
4. **Given** a criterion with fewer than five observations, **When** it is rendered, **Then** it reads n/a with its count.

---

### User Story 9 - Waste counters are measured, or say they are not (Priority: P3)

A coding attempt whose session was captured without any tool activity is
shown as not measured. From the next run on, opencode sessions are parsed
so that tool calls, file reads, rewrites and failed commands are counted.

**Why this priority**: all 278 audited code records carry zeros that read
as clean runs. The exit criterion does not depend on this story, and it
cannot be proven on stored records.

**Independent Test**: parse a session stream captured from a real opencode
run and confirm non-zero counters; render a stored all-zero waste record
and confirm it reads as not measured.

**Acceptance Scenarios**:

1. **Given** a stored opencode coding attempt, captured before the parser could see tool activity, whose waste counters show zero tool calls, **When** the waste view is rendered, **Then** the attempt reads as not measured, and the view says how many attempts that is.
2. **Given** a session stream captured from a real opencode run that used tools, **When** it is parsed, **Then** tool calls, file reads, file writes and commands are each counted.
3. **Given** a command that failed in that stream, **When** it is parsed, **Then** it is counted as a failed command.
4. **Given** a stored record, **When** it is scored after this round, **Then** its waste counters are unchanged on disk.
5. **Given** an attempt captured after the parser fix in which the model called no tool, **When** the waste view is rendered, **Then** it reads as a measured zero.

---

### Edge Cases

- A run with no stage record at all: counted as lost, reported in the attrition layer's header line as "no stage recorded", in no column.
- A run whose code stage finished but whose pipeline did not (for example it died in merge): graded, and its row says it did not finish.
- A pre-012 run with code records, no post-code stage record and a stored full-pass oracle record (one todo-api run): lost by the round 012 rule; its oracle record is discarded like any other lost run's.
- A graded run with an empty diff: zero tests passed, shown as such, counted in the means.
- A case with no oracle (the probe cases): rows and stage layers are shown; the oracle column and layer are blank.
- A selection that mixes several cases: the grid is grouped by case first; no figure averages across cases.
- A matrix run with two arms under one benchmark run: each cell is its own run row under its own arm.
- A stage with token data on some records and none on others: the wasted-tokens cell uses the records that have it and states how many do not.
- Drift records: never shown as runs of a case.
- A selection with no records: the command succeeds and says so.
- A record whose stage name is not in the pipeline order: shown in a trailing column, the same one in every layer.
- A task with several attempts where the attempt number is absent: attempts are ordered by time.
- Output printed to a console that cannot show non-ASCII characters: the text report stays ASCII.

## Requirements *(mandatory)*

### Functional Requirements

**Runs, status and identity (report 2.2, 2.3 — F14, F10; exit criterion)**

- **FR-001**: The unit of every view MUST be the run. All records of one run MUST be attributed to one cell and one arm, including pre-012 records stored under several labels.
- **FR-002**: For a run with a recorded cell status the scorer MUST use it. For a run without one it MUST derive the status from the run's stage records by the rule round 012 applies when writing (code finished when a post-code stage wrote a record; last stage is the latest in pipeline order), and MUST mark the status as derived. A run is lost when its code stage did not finish, whether or not its case has an oracle; "without oracle" applies only to runs whose code stage finished.
- **FR-003**: An oracle record belonging to a lost run MUST enter no mean, rate, count of failures or colour. The output MUST state how many such records were discarded.
- **FR-004**: Every score MUST state runs started, graded, lost (with the count per last stage), grading failed and without oracle, and these MUST sum to runs started.
- **FR-005**: No aggregate may combine pre-012 and 012 runs. A group of pre-012 runs MUST be labelled untrusted.
- **FR-006**: For a pre-012 run the arm label MUST be recovered from the run's own records and marked as recovered. The scorer MUST NOT present a recovered label as recorded.

**Run-by-run grid (report 2.3)**

- **FR-007**: The first section of a score MUST be a grid with one row per run, grouped by case, then arm, then Kroker commit, runs in start order.
- **FR-008**: Runs without a recorded commit and runs recorded with an unknown commit MUST each form their own group, named as such.
- **FR-009**: Each group header MUST show runs started, runs graded, and over the graded runs: mean partial credit, standard deviation, minimum, maximum and all-pass rate.
- **FR-010**: Each run row MUST show status, last stage, a per-stage mark, tests passed over total, first-attempt score, after-repair score, tokens, wall-clock time, and whether the tree had uncommitted changes.
- **FR-011**: The per-stage mark MUST distinguish: passed first time, passed after repair, did not pass, not reached, not evaluated. For a per-task stage it MUST carry the count of tasks behind it.

**Layered heatmap (report 2.2 — F14)**

- **FR-012**: The heatmap MUST be four layers with identical columns: the stages in pipeline order followed by the oracle. The stage order MUST be the one cell status uses, defined once. A column is rendered when any layer has an observation in it.
- **FR-013**: Heatmap rows MUST be cells split by record generation (case, arm, generation).
- **FR-014**: The **attrition layer** MUST show, per stage, runs whose last stage is that stage and that were lost, over runs that reached that stage. A run reached a stage when its last stage is that stage or a later one in pipeline order. A stage at which no run of the row wrote a record (a disabled stage) has no column value. A run lost inside the per-task loop MUST be counted once, under code, while its row in the grid keeps the last stage as recorded. The layer's header MUST state runs lost before code over runs started, and the tokens those runs spent.
- **FR-015**: The **first-attempt failure layer** MUST show, per stage, first attempts that did not pass over first attempts. The unit is the task for per-task stages and the run for the others. Later attempts MUST NOT enter this layer.
- **FR-016**: The **wasted-tokens layer** MUST show, per stage, wasted tokens over all tokens spent at that stage. Tokens are wasted when a lost run spent them (at any stage), or when they belong to an attempt that was superseded by a later attempt of the same task or whose task never passed. Each token is counted once. Dollar cost MUST NOT be used. Records without token data MUST be left out and counted as not measured.
- **FR-017**: The **oracle layer** MUST show one mark per graded run, in start order, carrying tests passed over total. It MUST NOT be reduced to a count of failures.
- **FR-018**: Colour MUST come from a fixed five-step scale per layer (table below), the same on every report. Colour MUST NOT depend on the other values in the grid. Darker MUST always mean worse, and the scale MUST NOT rely on telling red from green.
- **FR-019**: Every coloured or grey cell MUST print its value and its denominator.
- **FR-020**: A cell with fewer than five observations MUST be grey and MUST still print value and denominator. Grey, blank (no observation) and step 0 MUST be three different appearances. In the oracle layer each mark is one run, so the rule applies to the group's summary figures.
- **FR-021**: Each observation MUST enter at most one cell of each layer. No layer may add counts of different kinds.

Fixed scales (FR-018). The observation that the grey rule counts is named per layer.

| Layer | Cell value | Step 0 | Step 1 | Step 2 | Step 3 | Step 4 | Observation |
|---|---|---|---|---|---|---|---|
| Attrition | lost at stage / reached stage | 0% | up to 5% | up to 10% | up to 25% | above 25% | a run that reached the stage |
| First-attempt failure | failed first attempts / first attempts | 0% | up to 10% | up to 25% | up to 50% | above 50% | a first attempt |
| Wasted tokens | wasted tokens / tokens at stage | 0% | up to 10% | up to 25% | up to 50% | above 50% | an attempt with token data |
| Oracle | tests passed / tests total | 100% | 90% and above | 75% and above | 50% and above | below 50% | a graded run |

**Oracle figures (report 2.4 — F14)**

- **FR-022**: Partial credit of a run MUST be tests passed over tests total of its oracle grade. The all-pass rate of a group MUST be graded runs that passed every test over graded runs.
- **FR-023**: Wherever an oracle aggregate is shown, mean partial credit and the all-pass rate MUST be shown together, each with its count.
- **FR-024**: A grading failure MUST be shown as such and MUST enter neither figure.

**First attempt and after repair (report 2.6 — F7)**

- **FR-025**: The first-attempt score of a run MUST be tasks whose first code attempt passed over tasks attempted. The after-repair score MUST be tasks whose last code attempt passed over tasks attempted. They MUST be separate columns in the grid and in the summary tables.
- **FR-026**: A share of attempts MUST NOT be shown as a quality score.
- **FR-027**: A stage whose records carry a pass/fail verdict and no rubric score MUST be shown as a pass rate with its denominator. The quality column MUST hold rubric scores only.
- **FR-028**: A verdict known to be a copy of another stage's verdict (pre-012 qa, which copies code) MUST be marked as a copy in every view and MUST NOT be counted as an observation.

**Gate versus oracle (report 2.5 — F8)**

- **FR-029**: For each gate (qa, review, analyze, merge, and each review lens that wrote records) the score MUST show, over graded runs that have a verdict of that gate: the four counts of gate verdict against oracle verdict, the agreement rate, the escape rate (runs the gate passed and the oracle failed, over runs the gate passed) and the false-reject rate (runs the gate rejected and the oracle passed in full, over runs the gate rejected).
- **FR-030**: A run-level gate's verdict for a run MUST be its last verdict in that run. A per-task gate's verdict for a run MUST be pass only when its last verdict passed for every task of the run. A verdict counts as a pass when the gate let the work through: a recorded pass, and for merge also a pass with waived advisory checks (which merge records as "revise"). Every other verdict (fail, escalated, and "revise" on any gate other than merge) MUST count as a rejection. The oracle's verdict for a run MUST be pass only when every test passed.
- **FR-031**: Beside the rates, the view MUST show the mean partial credit of the runs the gate passed and of the runs it rejected.
- **FR-032**: Not-evaluated verdicts and lost runs MUST enter no gate's counts. Rates MUST follow the denominator and under-five rules of FR-019 and FR-020.
- **FR-033**: The existing reviewer-against-adversary agreement view MUST remain and MUST be named so that it cannot be mistaken for this one.

**Composite (report 2.1 — F9)**

- **FR-034**: No output of the benchmark package (score, end-of-run report, experiment comparison) may show a composite for a case that has fewer than two arms with at least one graded run each. The report MUST say in one line that it was left out and why.
- **FR-035**: With two or more such arms the composite MUST be shown per arm, with cost and speed normalised across the arms' figures and never across the records of one arm.
- **FR-036**: Passing composite weights when no composite is shown MUST NOT fail the command; the output MUST say the weights were not used.

**Success criteria rollup (report 2.7 — F12)**

- **FR-037**: Every criterion in a score MUST be computed only from runs in the selection being scored: record-based criteria from the selection's records, summary-based criteria from the run summaries of the selection's runs, matched by run identity.
- **FR-038**: Run summaries of pipeline runs that are not benchmark runs MUST enter no benchmark score, under any selector.
- **FR-039**: The section MUST state how many of the selection's runs had a readable run summary. A criterion with fewer than five observations MUST read n/a with its count.

**Waste counters (report 2.8 — F6)**

- **FR-040**: Waste counters captured by a session parser that could not see tool activity MUST be shown as not measured in every view and MUST enter no waste mean. That is every opencode attempt captured before the FR-041 fix that shows zero tool calls. Counters captured after the fix MUST carry a mark that says so, so that a real zero (a model that called no tool) stays a measured zero. The view MUST state how many attempts are not measured.
- **FR-041**: The opencode session parser MUST count the tool calls, file reads, file writes and commands that a real opencode session stream contains, and MUST count a failed command as failed. This MUST be proven against a stream captured from a real opencode run, kept as a test fixture.
- **FR-042**: The parser change MUST NOT alter how sessions of other harnesses are parsed.

**Compatibility, outputs and validation**

- **FR-043**: The scorer MUST NOT write to, rename or delete any stored record file. Every stored record file MUST still load.
- **FR-044**: The score command and the end-of-run report MUST produce their views from the same aggregation, so the same records give the same figures on both paths.
- **FR-045**: Every view MUST exist as a human-readable output and as a machine-readable output carrying the same figures and denominators.
- **FR-046**: The score command MUST keep running with no worker, no server and no network.
- **FR-047**: The documentation build that reads the text report MUST keep working when the composite column is absent.
- **FR-048**: No benchmark run lands in this round. Validation is the score command on the stored records.
- **FR-049**: Documentation that describes the scoring output (the composite, the heatmap, the success-criteria rollup, the waste counters) MUST be updated in the same change as the behaviour.

### Key Entities

- **Run**: one execution of one cell. Has an arm, a commit (recorded, unknown or not recorded), a record generation, a status (recorded or derived), a last stage, and at most one oracle grade.
- **Group**: the runs of one case, arm and commit. Carries the mean, spread and all-pass rate of its graded runs.
- **Task outcome**: for one task in one run, whether its first attempt passed and whether its last attempt passed.
- **Layer**: one grid of the heatmap. Has one cell value, one observation unit and one fixed colour scale.
- **Layer cell**: a numerator, a denominator, an observation count and a colour step (or grey, or blank).
- **Gate agreement**: for one gate, the four counts of gate verdict against oracle verdict over graded runs, and the rates derived from them.
- **Selection**: the set of runs a score covers (one benchmark run, one case, or everything). Every figure, including the success criteria, is computed inside it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Scoring cat-cafe-monitoring on the stored records shows 18 runs started, 8 lost before code (4 last seen at research, 4 at clarify) and 10 graded (baseline: lost runs invisible, research the coolest cell).
- **SC-002**: The same score shows mean partial credit 0.708 over 10 graded runs beside an all-pass rate of 1 of 10, and counts 8 discarded oracle records (baseline: 0.421 over 18).
- **SC-003**: The same score shows the case as one arm (baseline: two to four stored labels per cell).
- **SC-004**: For every selector on all stored records, runs started equals graded plus lost plus grading failed plus no oracle, every run is in exactly one grid row, and lost runs equal the attrition layer's cells plus "no stage recorded". Zero discrepancies.
- **SC-005**: The same score shows a first-attempt score of 84 of 113 tasks and an after-repair score of 111 of 113, and shows the attempt share of 0.725 nowhere.
- **SC-006**: No composite appears in the score of any stored case (each has one arm); a two-arm fixture shows one per arm.
- **SC-007**: In every heatmap layer, 100% of non-blank cells print a denominator, 100% of cells under five observations are grey, and one value maps to one colour step across two reports built from different data.
- **SC-008**: The success-criteria section of the cat-cafe score uses zero summaries of non-benchmark runs (baseline: 79) and states that 0 of the case's 18 runs left a summary.
- **SC-009**: The gate agreement view of the cat-cafe score shows analyze rejecting 10 of 10 graded runs, one of them a full oracle pass, with its escape rate reading n/a; and merge rejecting 7 (one a full oracle pass) and passing 3, with an escape rate of 3 of 3 shown in grey.
- **SC-010**: After every selector has been scored, every stored record file is byte-identical to what it was before, and every one loads.
- **SC-011**: Zero stored coding attempts are shown as a measured zero of waste (baseline: all of them), and a real captured opencode stream yields non-zero tool, read, write and command counts.
- **SC-012**: Scoring one case on the stored records completes in under one minute on the development machine with no service running.

## Rulings (GATE 1, user, 2026-10-09)

All five open questions were answered as recommended.

- **R1 (Q1)**: 2.8 stays in this round (User Story 9, FR-040 to FR-042). 2.9, erosion and verbosity, is removed from this round and becomes its own round (see Follow-ups).
- **R2 (Q2)**: the fixed colour scales are the table under FR-018, as written.
- **R3 (Q3)**: the attrition denominator is runs that reached the stage, with "N of M lost before code" in the layer header (FR-014).
- **R4 (Q4)**: the round 012 rule is applied uniformly to pre-012 runs (FR-002, FR-003), with both stated consequences accepted.
- **R5 (Q5)**: gate-versus-oracle agreement is at run level only (FR-029 to FR-032).

## Amendments after GATE 1 (plan consults, 2026-10-09; listed for GATE 2)

The skeptic pass broke five statements of the approved text. Each was checked in code or on stored records before the spec changed.

- **A1 (FR-030, US6, SC-009)**: merge "revise" is a pass with waived advisory checks, not a rejection. Cat-cafe merge is 7 rejected and 3 passed, not 10 rejected. Analyze is unchanged.
- **A2 (Terms, FR-002)**: a run of a case without an oracle that ended before code is lost. Round 012 labels its grading "no oracle"; the lost/finished line comes from whether code finished.
- **A3 (FR-014)**: "reached" is by position in the pipeline order, a disabled stage has no column value, and the grid keeps the recorded last stage of a run the layer counts under code.
- **A4 (FR-016)**: tokens spent by lost runs are wasted tokens at the stage that spent them. The first text left research and clarify at zero waste on the eight lost cat-cafe runs.
- **A5 (FR-040, US9)**: "zero tool calls means not measured" holds only for captures made before the parser fix. New captures carry a mark, so a model that called no tool reads as a measured zero.

## Follow-ups

- **Erosion and verbosity (report 2.9)**: its own round. Structural erosion and verbosity computed on the integration result after each run, stored with the run, shown as a second objective axis beside the oracle and never blended with it. Known before that round starts: no integration branch of any stored run survives, so it applies to new runs only; it needs a complexity analyser and a verbosity rule set the project does not have, and the source benchmark's rule-set licence is unchecked.
- **Live confirmation of the opencode parser (FR-041)**: rides the next benchmark run that happens for another reason.
- **Per-task gate-versus-oracle agreement**: after Phase 3 (3.2) adds the test-to-requirement mapping.

## Open Questions as put to GATE 1 (resolved above)

Each had a recommendation, and the spec is written to it.

- **Q1 — Do 2.8 and 2.9 stay in this round?** Recommendation: **2.8 stays, 2.9 becomes its own round.**
  - 2.8 turned out small: an opencode session parser already exists and its tool-event branch does not fire on real streams (see Assumptions). The fix is a parser correction plus the "not measured" rule. It cannot be shown on stored records, so its proof is a test on a real captured stream. Getting that stream costs one small opencode call, which is not a benchmark run; the user may instead supply a captured stream.
  - 2.9 cannot be validated at all inside this round's rules: no integration branch of any stored run survives, so every stored run would read "not measured". It also needs a complexity analyser and a verbosity rule set the project does not have (the source benchmark's 137 rules, licence unchecked), and it is a new step at run time, not a change to scoring output. If ruled in, it adds a tenth story and a run-time contract to this round.
- **Q2 — Fixed colour scales.** Recommendation: accept the table under FR-018 (five steps, fixed edges per layer, darker is worse, grey under five observations with the value still printed). The edges are a judgement and are the user's to move.
- **Q3 — Attrition denominator.** Recommendation: runs that reached the stage (cat-cafe: research 4 of 18, clarify 4 of 14), with "8 of 18 lost before code" in the layer header. The alternative is runs started for every column (4 of 18 and 4 of 18).
- **Q4 — Re-scoring pre-012 runs by the round 012 rule.** Recommendation: apply it uniformly (FR-002, FR-003). Consequences the user should see before approving: the 8 cat-cafe oracle records of lost runs are discarded from every figure, including the 6-of-12 result on an empty tree; and one pre-012 todo-api run that stored a 6-of-6 oracle result becomes lost, because its code stage never finished.
- **Q5 — Gate agreement at run level only.** Recommendation: yes for this round, with "every test passed" as the oracle's verdict and mean partial credit shown beside it. Per-task agreement needs the test-to-requirement mapping that Phase 3 (3.2) adds for cat-cafe.

## Assumptions

**Audit claims verified in the current tree (2026-10-09, main `35d1b056`)**

- **F9 holds.** Cost and speed are normalised against the largest value among the records of the same case and stage, and the test for "enough data" counts records, not arms. On one cell that is the cell's own slowest record.
- **F14 holds.** The heatmap adds gate rejections, fix attempts and oracle failures into one density and colours it against the grid's own maximum. It has no attrition figure.
- **F14, further finding.** The heatmap's column order is keyed on `planning` and has no `merge`; records use `plan` and `merge`, so both fall into the trailing bucket of unknown stages. Round 012 fixed the same mismatch for the rubric mapping only. FR-012 closes it by using one stage order.
- **F7 holds, recounted.** On cat-cafe: 153 code attempts over 113 tasks; 111 attempts passed (0.725, the audited figure); 84 tasks passed first time; 111 tasks passed by the end.
- **F7, qa copy confirmed on stored data.** The pre-012 qa verdict equals the code verdict on 153 of 153 cat-cafe attempts and 47 of 47 todo-api attempts. The review verdict differs from code's on 15 of 153, so review is its own observation.
- **F8 holds for analyze, not for merge.** Analyze fails on 10 of 10 graded cat-cafe runs. Merge is fail on 7 and "revise" on 3, and the merge stage writes "revise" with a score of 1.0 when it passes with waived advisory checks. So merge let 3 of 10 through; the audit's "rejects every run" counted them as rejections. Round 012 ruled the rejections right-reasoned; this round only measures the gates against the oracle.
- **F10 as round 012 left it.** All pre-012 records have no commit. The three 012 todo-api runs carry `unknown` (one run) and `b3344416` (two runs).
- **F12 holds and is wider than audited.** The rollup reads every run summary directly under the pipeline export root: 79 files, none under a benchmark run id (mostly `bf-intake-*` and `bf-e2e-*`). Benchmark runs export one level deeper and are not read at all (two such files exist, both todo-api). No cat-cafe run left a summary on disk.
- **The "8 of 18" count was recounted and holds.** Four cat-cafe runs have research as their only stage record, four have research and clarify. All eight carry a stored oracle record; seven are 0 of 12, one is 6 of 12.
- **Oracle partial credit is already on the records.** Every oracle record carries tests passed and tests total.
- **Code records carry the attempt number**, on every stored code, qa and review record of both oracle cases.
- **Token coverage on pre-012 cat-cafe records**: present on research, clarify, architecture, plan, code, qa, handoff and analyze; absent on review, merge, deploy and oracle.

**Audit claims that no longer hold as written**

- **F6: the cause is not a missing parser.** An opencode session parser exists and is tested against a hand-written stream. A stored transcript of a real opencode session, whose own text says it is creating four files, contains six model turns and no tool event. So the parser's tool-event branch does not fire on what opencode emits. The raw stream is not stored, only the parsed transcript, so stored records cannot be back-filled.
- **F6: session data is not reachable from the record path for stored benchmark runs.** The sixteen session digests on disk belong to four non-benchmark runs. No stored benchmark run has a transcript. FR-040 therefore reads the record's own counters.
- **Report §1.1 "todo-api: 5 runs, 5 reached code" needs a footnote.** One of the five has code records and no post-code stage record. Under the round 012 rule its code stage did not finish, so it is lost, despite a stored 6-of-6 oracle record (Q4).
- **Report 2.5 is a new view.** The existing agreement matrix compares the reviewer with the adversary lens, not a gate with the oracle.
- **The brief's "nearest AGENTS.md in the benchmarks package" does not exist.** Only the root file applies.

**Not verified — the plan must establish**

- Which event shape real opencode streams use for tool activity. It needs a real captured stream (Q1).
- Whether proposer stages write one record per revise round or one per stage. On stored data each wrote one per run. If one per stage, the wasted-tokens layer shows no waste for them, which is the honest reading.

**Defaults taken**

- Spread is the sample standard deviation with the minimum and maximum beside it.
- "Five observations" is the one threshold for grey cells, grey group headers and n/a criteria, matching the floor the success-criteria rollup already uses.
- The attrition layer counts lost runs only. A run that finished code and then died is graded and is flagged on its row.
- Tasks attempted is the denominator of the two code scores. Planned tasks that were never attempted are not on the records.
- With two or more arms the composite keeps its current weights; only what it is normalised against changes.
- A stored opencode waste record with zero tool calls is a capture failure, because the parser of that time could not see tool events at all. After the fix a zero is a real zero and is kept.
- The text report stays ASCII.

## Out of Scope

- 2.9, erosion and verbosity on the integration branch (ruling R1: its own round).
- Any benchmark run, including a smoke run. Live confirmation of the opencode parser rides the next run that happens for another reason.
- Rewriting, re-grading, relabelling or deleting stored records.
- Per-task gate-versus-oracle agreement.
- The $0.00 code cost on subscription-billed harness runs (F5), and whether token counts can stand in for cost (report §5).
- Why eight cat-cafe runs ended in research and clarify (report §5).
- Phase 3 (corpus) and Phase 4 (calibration, baseline, paired comparison with significance tests).
- Changes to the web console.
- Editing, staging or committing the source report.

## Dependencies

- `docs/reports/2026-10-06-benchmark-improvement-plan.md` (read-only source: §1.2 findings, §4 Phase 2 table).
- Round 012's spec, data model and records contract, which define cell status, provenance fields and the pre-012 marker this round reads.
- `BENCHMARK.md` (§4.1, §4.3, §4.4) and the root `AGENTS.md`.
- Repo rules: 1000-line file ceiling, cross-stage call ban, producer owns its artifacts, behaviour and its clauses change in the same diff. The session parser lives in the harness package; the benchmark package does not own it.
- The stored records under `runs/benchmarks/` as the validation corpus.
- For FR-041: one captured real opencode session stream.
