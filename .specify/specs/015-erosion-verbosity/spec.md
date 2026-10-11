# Feature Specification: Erosion and Verbosity as a Second Quality Axis

**Feature Branch**: `015-erosion-verbosity`

**Created**: 2026-10-11

**Status**: Approved (GATE 1, 2026-10-11)

**Input**: User description: "Round 015, report item 2.9 of `docs/reports/2026-10-06-benchmark-improvement-plan.md` (Phase 2's last open item, made its own round by round 013 ruling R1): erosion and verbosity computed on the integration branch after each benchmark run. Deterministic metrics, no judge: structural erosion = share of complexity mass in functions with cyclomatic complexity above 10, mass(f) = CC(f) * sqrt(SLOC(f)); verbosity = lines flagged by AST-grep rules united with cloned lines, divided by lines of code. Both are a second objective quality axis next to the oracle (source: SlopCodeBench, report §2.6)."

## Context

Round 013 rebuilt the scoring output around the run and closed FR-001 to
FR-049 of its own spec. What no score can show today is *how* the produced
code is written: a run can pass every held-out test and still double the
complexity mass of what it touched, and the oracle is blind to that. The
source benchmark (report §2.6) measures two deterministic properties of the
produced tree — structural erosion and verbosity — and uses them as a
second objective axis: no judge, no network, computable from the code
alone. On their human baseline, agents are 2.3x more verbose and 2.0x more
eroded, and erosion rises over 77% of trajectories.

This round adds that axis to Kroker's benchmark. The measurement happens
once, at the end of a run, on the final state of the run's integration
branch (`sdlc/<run_id>/integration`), and is stored with the run's records.
Every reading side (score command, end-of-run report) then treats it like
any stored record: read-only, never recomputed.

Two facts bound the round, both established in round 013's follow-up:

- **No integration branch of any stored run survives.** Every stored run
  will read "not measured" on this axis, forever. The axis exists for new
  runs only, and live proof needs at least one new benchmark run.
- **The project has neither tool today.** A complexity analyser and a
  verbosity rule set have to be added (licence checks included). The
  source benchmark's 137 AST-grep rules are not in this repository and
  their licence is unchecked.

The reader of a score — the person deciding whether a change to Kroker
helped — is the user of this feature. The second axis answers a question
the oracle cannot: did the run get the answer at the cost of wrecking the
code.

## Terms

- **Integration branch**: the run's `sdlc/<run_id>/integration` branch; the
  accumulated result of the run's completed tasks.
- **Erosion**: the share of complexity mass sitting in functions whose
  cyclomatic complexity is above 10, where the mass of a function is its
  complexity times the square root of its lines of code.
- **Verbosity**: lines the pinned rule set flags, united with cloned lines,
  over lines of code.
- **Measured run**: a run whose axis record was written at run end.
- **Not measured**: the honest absence state — no measurement exists or it
  could not apply. Never rendered as a zero.
- **Rule-set version**: the identity of the verbosity rule set a
  measurement was made under. Measurements under different versions are
  never averaged together.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every new run carries the two figures (Priority: P1)

A benchmark run finishes. Its records include one axis record: erosion and
verbosity of the integration branch's final state, with the branch head it
measured and the tool identifications. The run grid shows the figures on
the run's row; the group header shows their mean over the group's runs.

**Why this priority**: without the measurement at run time nothing else in
the round exists; the branch is gone after the run.

**Independent Test**: run a fixture-backed measurement against a prepared
tree with a known complexity distribution and read the two figures off the
stored record.

**Acceptance Scenarios**:

1. **Given** a run whose integration branch ends at a tree with known
   complexity mass, **When** the run finishes, **Then** the run's records
   contain one axis record whose erosion equals the known figure exactly.
2. **Given** an axis record, **When** any view shows it, **Then** it also
   shows the integration branch head it was measured at and the tool
   identifications.
3. **Given** a scored case with measured runs in one group, **When** the
   group header is rendered, **Then** it shows the mean erosion and mean
   verbosity over the group's measured runs, each with its count.
4. **Given** a matrix run with two arms, **When** both finish, **Then**
   each arm's integration branch is measured separately and each run row
   carries its own figures.

---

### User Story 2 - Absence reads as not measured, never as zero (Priority: P1)

Every run measured before this round, every run lost before its
integration branch held code, and every case whose produced code the
metric cannot read all appear with an explicit "not measured" state. The
output says how many runs that is. No mean, rate or colour ever treats
absence as zero.

**Why this priority**: the round's own validation corpus is 100% "not
measured"; if absence read as zero, the first score after this round would
be a lie on every historical row.

**Independent Test**: score the stored records after the round and confirm
every run reads not measured on this axis, zero means, and an explicit
count.

**Acceptance Scenarios**:

1. **Given** the stored records, **When** any case is scored, **Then**
   every run row reads "not measured" on the axis and no group shows a
   mean for it.
2. **Given** a run lost before code, **When** its row is rendered, **Then**
   it reads not measured with the reason, and the output's count of
   not-measured runs includes it.
3. **Given** a measurement whose rule-set version differs from another's,
   **When** both fall in one group, **Then** they are not averaged together;
   the figures are shown per version or the mean is withheld with the
   versions named.

---

### User Story 3 - The axis stands beside the oracle and never blends with it (Priority: P2)

The two figures are a second axis: they appear beside the oracle column,
never inside the quality column, never in partial credit, never in the
composite, never in gate-versus-oracle agreement, and never averaged with
each other or with any rubric score.

**Why this priority**: the source benchmark's central finding is that a
"cleaner code" prompt trades about a third of erosion and verbosity
against 2.3 points of correctness. That trade is only visible if the two
axes stay separate.

**Independent Test**: score a fixture with measured runs and confirm by
absence: the figures appear nowhere in quality, composite, oracle or gate
figures, in text, HTML or JSON.

**Acceptance Scenarios**:

1. **Given** a case with measured runs and a composite (two arms), **When**
   the composite is rendered, **Then** erosion and verbosity enter no
   composite weight, normalisation or figure.
2. **Given** any view, **When** its quality column is rendered, **Then** it
   holds rubric scores only; erosion and verbosity have their own columns.
3. **Given** the gate-versus-oracle view, **When** it is built, **Then** no
   gate's counts or rates change because a measurement exists.
4. **Given** a machine-readable output, **When** it is read, **Then** the
   axis figures sit under their own key, not inside oracle or quality
   figures.

---

### User Story 4 - The measurement is deterministic, cheap and self-describing (Priority: P2)

Measuring the same tree twice gives the same two figures. The measurement
adds a bounded, small time to a run, needs no network, and the record
carries everything needed to interpret it later: tool names and versions,
the rule-set version, the head it measured.

**Why this priority**: the axis is only comparable across runs and arms if
the same tree always measures the same and the record says what measured
it.

**Independent Test**: measure one fixture tree twice and diff the records;
time the measurement.

**Acceptance Scenarios**:

1. **Given** one fixture tree, **When** it is measured twice, **Then** both
   records carry identical figures.
2. **Given** the measurement step, **When** it runs on a case-sized tree,
   **Then** it completes in seconds, not minutes, and needs no network.
3. **Given** an axis record, **When** it is read months later, **Then** the
   rule-set version and tool identifications on the record say what the
   figures mean without reading the code of that time.

---

### Edge Cases

- A run whose integration branch holds no code at measurement time (lost
  before code, empty tree): not measured, reason recorded.
- A run that finished but whose integration branch is gone at measurement
  time (infrastructural failure): not measured, reason recorded; the run's
  other records and its grade are unaffected.
- A case whose produced code is not Python: not measured with that reason
  (ruling R3), until a round extends the metric.
- A tree with no functions at all (a docs-only result): erosion reads n/a
  with the reason, not 0%.
- A tree where every function is above the complexity threshold: erosion
  reads 1.0 (100%), a real value, not a saturation error.
- A rule-set version change between two runs of one group: no mean across
  the versions (US2, scenario 3).
- A case with zero measured runs: the group's axis figures read n/a with
  their zero counts; no error.
- A measurement that crashes mid-run: the run's pipeline result is not
  failed by it; the axis reads not measured with the reason.
- The stored corpus: every record reads not measured (US2), and scoring
  stays as fast as round 013 left it.

## Requirements *(mandatory)*

### Functional Requirements

**Measurement at run end**

- **FR-001**: At the end of every benchmark run, the system MUST measure
  erosion and verbosity of the final state of the run's integration branch
  and store the result as one axis record of that run, alongside its other
  records.
- **FR-002**: An axis record MUST carry: the run id, the arm, the
  integration branch head it was measured at, erosion, verbosity, the
  underlying counts (flagged lines, lines of code, and the complexity-mass
  split the erosion figure came from), the rule-set version, the tool
  identifications, and the provenance fields every 012-generation record
  carries.
- **FR-003**: Erosion MUST be computed as the share of complexity mass in
  functions whose cyclomatic complexity is above 10, where a function's
  mass is its complexity times the square root of its lines of code. The
  record MUST carry the mass split so the figure can be audited.
- **FR-004**: Verbosity MUST be flagged lines over lines of code, where the
  flagged lines are the lines the project's own pinned rule set flags. The
  rule set lives in this repository and is versioned; the record carries
  its version. Cloned lines are not united in (ruling R1); the difference
  from the source benchmark's definition MUST be stated in `BENCHMARK.md`.
- **FR-005**: The measurement MUST be deterministic: the same tree under
  the same tool identifications MUST produce identical figures.
- **FR-006**: A run that cannot be measured MUST get its axis record
  stating not measured with the reason (no code on the branch, branch
  absent, unsupported language, measurement failure). The run's other
  records, its grade and its pipeline result MUST be unaffected by the
  measurement or its failure.
- **FR-007**: The measurement MUST NOT need network access; its tools MUST
  come from the project's own environment.

**Reading side**

- **FR-008**: The run grid row MUST show the two figures for a measured
  run, and the group header MUST show the mean of each over the group's
  measured runs, each with its count.
- **FR-009**: A run without a usable measurement MUST read not measured
  with its reason in every view, MUST enter no mean, rate or colour, and
  the output MUST state how many runs that is.
- **FR-010**: No aggregate may combine measurements made under different
  rule-set versions; where versions mix in one group, the figures are
  shown per version or withheld with the versions named.
- **FR-011**: The two figures MUST appear only as their own axis: in no
  quality column, in no partial-credit or all-pass figure, in no composite
  weight or normalisation, in no gate-versus-oracle count, and never
  averaged with each other. This holds in text, HTML and JSON outputs.
- **FR-012**: The score command and the end-of-run report MUST show the
  same figures for the same records (one aggregation, both paths).
- **FR-013**: The score MUST read stored axis records only; it MUST NOT
  recompute the metrics, need the integration branch, or need a worker,
  server or network.
- **FR-014**: Axis figures follow the house display rules: a figure prints
  with its count; a mean over fewer than five runs is grey with its count;
  the text report stays ASCII.

**Compatibility and validation**

- **FR-015**: Nothing under `runs/` is rewritten by this round; stored
  records keep loading; scoring the stored corpus produces the same
  figures round 013's verification recorded, plus the axis reading not
  measured everywhere.
- **FR-016**: Documentation that describes the benchmark output
  (`BENCHMARK.md` and the passages that list what a score shows) MUST be
  updated in the same change as the behaviour.
- **FR-017**: The round MUST add the complexity analyser and the rule
  engine to the project environment (ruling R2), and MUST include one
  todo-api smoke run as the live proof of the axis. That run also carries
  round 013's follow-up "live confirmation of the opencode parser".

### Key Entities *(include if feature involves data)*

- **Axis record**: one run's erosion-verbosity measurement. Carries the
  figures, the counts behind them, the branch head, the rule-set version,
  the tool identifications and the provenance. Immutable once written,
  like every record.
- **Not-measured state**: a reason on the axis record (or its absence for
  stored runs). Renders explicitly; never a zero.
- **Rule-set version**: the pinned identity of the verbosity rule set. The
  aggregation boundary for means.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fixture tree whose complexity mass is half in functions
  above the threshold measures erosion exactly 0.50; a tree with known
  flagged-line and total-line counts measures verbosity exactly
  flagged/total. Zero discrepancies on the fixtures.
- **SC-002**: Measuring the same fixture tree twice produces byte-identical
  figures.
- **SC-003**: After the round, scoring every stored case shows the axis as
  not measured on 100% of runs, zero axis means anywhere, an explicit
  not-measured count, and every round 013 verification figure unchanged.
- **SC-004**: In every output of a score with measured runs (text, HTML,
  JSON), the axis figures appear in exactly one place per view and in no
  quality, oracle, composite or gate figure (checked by absence).
- **SC-005**: The measurement step completes in under 30 seconds on a
  case-sized tree with no network.
- **SC-006**: The smoke run's run row and group header show both figures
  with tool identifications, and its score shows them beside the oracle.

## Rulings (GATE 1, user, 2026-10-11)

All three open questions were answered as recommended.

- **R1 (Q1)**: verbosity's rule set is authored in this repository, pinned
  and versioned; cloned lines are out of v1; the difference from the
  source definition is documented in `BENCHMARK.md` (FR-004).
- **R2 (Q2)**: the complexity analyser and the rule engine are added to
  the project environment, and one todo-api smoke run proves the axis
  live (FR-017, SC-006). The run also carries the round 013 follow-up
  "live confirmation of the opencode parser".
- **R3 (Q3)**: v1 measures Python produced code only; other trees read not
  measured with that reason (FR-006).

## Assumptions

**Verified in the current tree (2026-10-11, main `c3f6319c`)**

- The integration branch is `sdlc/<run_id>/integration`, built in a
  worktree during the run and not preserved afterwards (the oracle already
  handles "integration branch absent" as its own case) — hence
  measurement at run end, from stored records never.
- No complexity analyser or AST rule engine is a project dependency today.
- The benchmark case importers grade with pytest; the produced code of the
  current corpus is Python.
- Round 013's reader (`runs.py` and everything downstream) is the surface
  this round's reading side extends; the stored corpus reads as
  generation "pre-012/012" and would read not measured on this axis.

**Defaults taken**

- One axis record per run (both figures together), not one per figure.
- The threshold (complexity above 10) and the erosion mass formula are
  the source benchmark's, adopted as written; the threshold is a named
  constant, the user's to move later.
- The measurement runs in the same worker that finalises the run, so no
  new service is introduced.
- Grey/under-five and ASCII rules match round 013's display contract.
- The axis is opt-out by configuration (a case or arm can disable it) —
  default on.

## Out of Scope

- Extending the metric beyond Python produced code.
- Clone detection (ruled out of v1 by R1).
- Any change to what the oracle measures, to rubric scores, to the
  composite's weights, or to gate verdicts.
- Phases 3 and 4 of the improvement plan (corpus growth; calibration,
  baseline, paired comparison).
- Interpreting the figures — thresholds for "too eroded", alarms, or a
  quality gate on erosion/verbosity. This round only measures and shows.
- The web console.
- Editing, staging or committing the source report under `docs/reports/`.

## Dependencies

- `docs/reports/2026-10-06-benchmark-improvement-plan.md` (read-only
  source: §2.6, §4 task 2.9) and round 013's follow-up section.
- Round 013's reading side: the run model, the grid, the report writer.
- The worker's run-finalisation path, where the measurement attaches.
- Repo rules: 1000-line file ceiling, cross-stage call ban, producer owns
  its artifacts, behaviour and its clauses change in the same diff. The
  measurement writes benchmark records, so it lives in the benchmark
  package; the workflow calls it the way it calls the report writer.
- Whatever GATE 1 rules in for Q2: the two tools and possibly one smoke
  run (with the benchmark launch runbook's constraints: dedicated server
  port, clean worktree, never parallel with live pipeline runs).
