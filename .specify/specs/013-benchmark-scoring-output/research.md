# Research: Benchmark Scoring Output Rework (013)

Decisions the plan rests on. Each says what was chosen, why, what else was
weighed, and what the executor must verify before code depends on it.
`B/` = `src/sdlc/benchmarks/`. `H/` = `src/sdlc/harness/`. Line numbers are
from main `35d1b056`.

## R-1. One run model, built once

**Decision**: a new pure module `B/runs.py` turns a list of records into
`Run` objects. Every view (grid, heatmap layers, gate-versus-oracle,
summaries, composite decision, success-criteria scoping) reads runs, never
raw records. `runs.py` imports `B/models.py` and the standard library only.

**Why**: four modules hold four private notions of "a run" today
(`heatmap.py:88-90`, `sc_rollup.py:107-110`, `waste_matrix.py:91-92`,
`report.py:105-128`). FR-001 and SC-004 need one.

**Alternatives**: extend each view in place (keeps the four notions);
put the model in `report.py` (imports `temporalio` at module scope, and
`sdlc benchmark score` must run with no worker).

**Constraint**: `B/cell.py` imports `temporalio` and `B/recorder.py` at
module scope. `runs.py` must not import it. See R-2.

## R-2. The 012 status rule is extracted, not copied

**Decision**: two pure functions move into `B/models.py`, beside
`CELL_STAGE_ORDER` and `POST_CODE_STAGES`:
`cell_progress(records) -> (last_stage, code_finished)` and
`grading_from_score(has_oracle, code_finished, score) -> str`.
`summarize_cell` and `grading_status` in `B/cell.py` call them and keep
their signatures. `runs.py` calls the same two.

**Why**: FR-002 says "the rule round 012 applies when writing". One body
is the only way that stays true.

**Derived status for a run with no cell record**: `code_finished` and
`last_stage` from `cell_progress`. `has_oracle` = the run has an
oracle-scope record (the case's language is not on a record). A
code-finished pre-012 run with no oracle record reads "no oracle".

**Status of a run** (one of five, mutually exclusive, amendment A2):

| Code finished | Grading (recorded or derived) | Run status |
|---|---|---|
| no | any | `lost` |
| yes | `graded` | `graded` |
| yes | `grading_failed` | `grading_failed` |
| yes | `no_oracle` | `no_oracle` |

A recorded cell status of `not_graded` always has code not finished
(`workflow.py:359` grades only when code finished), so it maps to `lost`.

**Verify (step 0)**: on every stored run, the derived status of a 012 run
equals its recorded one (three todo-api runs).

## R-3. The run key is `run_id`; the arm comes from it

**Decision**: `Run.run_id` is the key. For the arm, in order: `arm` on any
record (012); else the part of `run_id` after the first `/`, split on `#`
at most twice (`case`, `harness[:lead]`, `arm`); else the oracle record's
`model`; else `arm_label` of the first record. Every result other than the
first is marked `arm_recovered`.

**Why**: `workflow.py:308` builds the child id as
`f"{bench_run_id}/{cell.cell_id}"` and every stored `run_id` has that
shape (advisor D2, grep over the corpus). The coding model on a pre-012
record is `zai-coding-plan/glm-5.2`, the arm is `zai-coding-plan-glm-5.2`;
falling back to the coding model would split lost and graded runs into two
arms and break SC-003.

**Alternatives**: `(bench_run_id, cell_key)`: `cell_key` embeds the
record's model, which is exactly what differs per record kind on pre-012.

**Verify (step 0)**: zero stored records have a `run_id` without `/` or
without `#` after it, drift records aside. One unit test builds a
`BenchmarkCell`, forms the id the way the workflow does and asserts the
parser returns its parts, so a change of the id format fails a test.

## R-4. Record generation and commit groups

**Decision**: `Run.generation` is `pre012` when `is_pre012` holds for the
run's records, else `012`. `Run.commit` is the records' `kroker_commit`:
a commit id, the literal `unknown`, or `None` (shown as "not recorded").
A group is `(case, harness, arm, generation, commit)`; the harness is in
the key so that two harnesses under one arm name never merge. No function takes runs of
two generations and returns one figure.

**Why**: FR-005, FR-008, round 012 ruling R3.

## R-5. Task outcomes and the qa copy

**Decision**: per run, per task: the code attempts sorted by
`(attempt or 0, speed.started_at)` (the key `sc_rollup.py:114` already
uses). `first_passed` = first attempt's outcome is pass; `last_passed` =
last attempt's outcome is pass. `Run.first_attempt = (k, n)` and
`Run.after_repair = (k, n)` over tasks with at least one code attempt.

`Run.qa_is_copy` is set by the run builder: the run is pre-012 and every
qa record's outcome equals the code record's for the same
`(task_id, attempt)`. Views read the flag; none re-derives it.

**Why**: FR-025, FR-028. Stored data: qa equals code on 153 of 153
cat-cafe attempts; review differs on 15 of 153.

## R-6. Heatmap: layers replace the summed density; the graph vocabulary stays

**Decision**: `B/heatmap.py` keeps its name and keeps `CANONICAL_STAGES`
untouched. `HeatmapCell`, `Heatmap`, `build_heatmap`, `max_density`,
`ORACLE_STAGE`, `REWORK_OUTCOMES` are replaced by the layered model in
data-model §3. Columns come from `CELL_STAGE_ORDER` plus `oracle`.
Rendering moves to a new `B/heatmap_render.py`. Output file names
`heatmap.html` and `heatmap.json` are kept; the JSON schema changes.

**Why**: `CANONICAL_STAGES` is imported by `graph/node_types.py:333`,
`dashboard/graph_wire.py:160` and four test files as the graph's stage
vocabulary. It is not the record vocabulary (`planning` against `plan`).
Nothing outside tests reads the heatmap JSON content (advisor D3).

**Superseded on purpose** (GATE 2 item): the E-77 once-per-activation
`fail_reentry` axis and the per-task maximum of `fix_attempts`
(`heatmap.py:95-149`). The layers count attempts, not `fix_attempts`, so
neither rule has anything to act on. The record fields stay.

**Kept**: the calibration block appended to the HTML. Language is shown as
a label on the row; the per-language duplicate grids go.

## R-7. Layer definitions

One row per `(case, arm, generation)`. A column is rendered when any layer
of any row has an observation in it.

- **Attrition**. `TASK_LOOP_STAGES` = code, tool_approval, qa, review,
  adversary, deep_review, handoff. The attrition position of a lost run is
  `code` when its last stage is in that set, else its last stage. A run
  reached stage S when the position of its last stage (attrition position
  for lost runs) is at or after S. A stage at which no run of the row
  wrote a record has no value (amendment A3). Cell = lost at S / reached
  S. Header: lost before code / started, and the tokens those runs spent.
  Runs with no stage record are in the header only.
- **First-attempt failure**. Per-task stages: unit `(run, task)`, the
  record of the first attempt at that stage. Other stages: unit run, the
  first record of that stage by time. Numerator: outcome is not a pass
  (R-9 decides pass per stage). `not_evaluated` is in neither count. A qa
  cell under `qa_is_copy` has no value and reads "copy of code".
- **Wasted tokens** (amendment A4). Tokens = input + output. A record's
  tokens are wasted when the run is lost; or the record has a task and
  attempt and that attempt is not the task's last; or the task's last
  attempt did not pass. A task record with no attempt number (handoff) is
  wasted only by the first and third rule. Cell = wasted / total at the
  stage. Observation = a record with token data. Records without it are
  counted as not measured.
- **Oracle**. One mark per graded run, start order, passed / total.

**Known limit, stated in the output**: a record is written when a stage
ends. A run that died inside stage X has X-1 as its last stage.

## R-8. Fixed scales

**Decision**: the table under spec FR-018 (ruling R2), as data in
`B/heatmap_render.py`: per layer, four upper bounds and a direction. The
step of a value is a pure function tested on every edge. Colours: one
single-hue ramp of five lightness steps, grey for under five observations,
no fill for blank. Text in every cell: `value (num/den)`.

`MIN_OBSERVATIONS = 5` lives in `B/runs.py`; `sc_rollup.MIN_RUNS` becomes
an alias of it.

## R-9. Gate verdicts

**Decision**: a pure `gate_passed(stage, outcome) -> bool | None` in
`B/runs.py`: `None` for `not_evaluated`; `True` for pass; `True` for
`revise` when the stage is `merge`; else `False`.

**Why** (amendment A1): `stages/merge/step.py:654` writes
`REVISED if overrides else PASS` with score 1.0 on the approval path;
merge rejections are written earlier with `FAIL`. On architecture, plan
and deploy `revise` means the gate did not approve. Stored cat-cafe: merge
7 fail, 3 revise with score 1.0.

**Run-level verdict**: for analyze, merge: the last record of the stage.
For qa, review and each lens: pass only when the last record of that stage
passed for every task that has one. qa under `qa_is_copy` is left out and
named as a copy.

## R-10. Composite

**Decision**: `composite_shown(runs) -> dict[case, CompositeDecision]` in
`B/runs.py`: shown when the case has two or more `(harness, arm)` pairs of
one generation with a graded run each. `compute_summaries` normalises cost
and speed against the largest arm mean of the `(case, stage)` and needs
two arms with data for the axis to count. `BenchmarkSummary.composite`
stays a required `float | None`. The report's column, the one-line reason
and the "weights not used" line all read the decision.

**Why**: FR-034 to FR-036. Inferring "no composite" from empty rows would
print the wrong reason for a two-arm case with no quality data (advisor
D8).

## R-11. Summary rows

**Decision**: rows are keyed `(case, stage, harness, arm, generation)`
from the run, not `cell_key`. New optional fields on `BenchmarkSummary`
(data-model §2). `mean_quality` is filled only from records whose judge is
a rubric judge (`llm_judge`, `staged_rubric`) and, on the oracle row, from
partial credit. Every other stage shows `pass_n / pass_d`. The code row
carries first-attempt and after-repair.

**Consequence**: a pre-012 cell that was two to four rows becomes one row
per stage. Existing tests that assert on `model` as the row key change
(plan, "tests changed on purpose").

## R-12. Success criteria by run identity

**Decision**: `load_evidence` loads records, builds the set of run ids,
then reads `export_root / run_id / "summary.json"` for each. Any read
error is "no summary" and a note. `Evidence` gains `summary_runs` and
`selection_runs` counts. `load_run_summaries` stays for its tests.

**Why**: `RunSummary.run_id` equals `BenchmarkRecord.run_id` byte for byte
on stored data (advisor D5); the export writes to `root / run_id`
(`observability/activities.py:29`), which is why benchmark summaries sit
one level deeper. Exact membership cannot admit a `bf-e2e-*` summary.

## R-13. One writer for both paths

**Decision**: `finalize_benchmark_report` keeps its name, its one `str`
argument and its `str` return, and calls `write_score` with the bench
directory as output. New modules are imported lazily inside it.

**Why**: FR-044. The workflow only stores the returned path
(`workflow.py:456-459`); an activity body is not replayed. `report.py` is
imported at worker boot through `imports_passed_through`, so its
module-scope imports stay as they are.

**Consequence**: a bench directory gains the grid, gate-oracle,
success-criteria and matrix files it did not have.

## R-14. The documentation script

**Decision**: `scripts/aggregate_benchmarks.py::parse_report` takes the
first pipe table whose header has both a cell exactly `case` and a cell
exactly `stage`. The grid's markdown header has neither (contract §2.5). A missing `composite`
column already reads as `None` through `.get`.

**Why**: it takes the first table today, and FR-007 puts the grid first
(advisor D8).

## R-15. Waste: a capture mark, and the opencode parser

**Decision** (amendment A5):

- `SessionDigest` and `WasteBag` gain `capture_rev: int | None = None`.
  `digest_of` writes `CAPTURE_REV = 1`. Old records read `None`.
- `waste_measured(record) -> bool` in `B/models.py`: false when the bag is
  `None`; false when `capture_rev is None`, `tool_calls == 0` and the
  record's harness or lead harness is opencode; else true. Used by the
  waste matrix and by `experiments._cells`.
- `OpenCodeHarness.normalise_session` recognises a tool event by
  `part.type == "tool"` or a top-level type of `tool` or `tool_use`,
  de-duplicates by call id, and counts a command as failed on
  `state.status == "error"` or a non-zero exit in the state metadata.

**Why**: the stored opencode parser output has model turns only. The
advisor's reading of opencode's emitter is `type: "tool_use"` with
`part.type: "tool"`; nothing in the repo pins it, and every opencode
sample in the repo is hand-written.

**Proof**: a real stream saved as
`tests/fixtures/opencode/session_tools.jsonl` (paths and session id
scrubbed, lines otherwise verbatim). It comes from one small
`opencode run --format json` call in a throwaway directory, or from the
user. The field names above are from memory until that file exists;
FR-041 is not done on a hand-written fixture.

**Verify (step 0)**: which harness kind the crew arm's coding session is
captured under, so the "opencode" test in `waste_measured` covers it; and
that an added optional field on `SessionDigest` changes no replay result.

## Consult log

- Advisor, `.workspace/tmp/013-advisor-a1.md`: D1 seam right, must not
  import `cell.py` (R-1, R-2). D2 arm from `run_id` (R-3). D3 keep
  `CANONICAL_STAGES` (R-6). D4 replay-safe, lazy imports (R-13). D5 exact
  id match (R-12). D6 distinct name `gate_oracle` (data-model §4). D7 no
  raw sample exists (R-15). D8 decision at case level, table-order trap
  (R-10, R-14). Extras: position-based "reached" (R-7), shared sort key
  (R-5).
- Skeptic, `.workspace/tmp/013-skeptic-a1.md`: L1 probes (A2, R-2). L2
  holds. L3 zero-tool attempts are real after the fix (A5, R-15). L4
  disabled stages and loop stages (A3, R-7); the in-flight limit is stated
  in the output. L5 lost-run tokens and handoff without attempt (A4, R-7).
  L6 holds: 84 and 111 of 113. L7 merge revise is a pass (A1, R-9),
  confirmed at `merge/step.py:654` and on stored scores. L8 holds: 18, 8,
  10, 85 of 120. L9 holds: no stored case has two arms.
