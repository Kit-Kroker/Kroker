# Contract: what a benchmark score shows (013)

What the score command and the end-of-run report do after this round,
stated so each line can be tested. Names are in
[../data-model.md](../data-model.md). `B/` = `src/sdlc/benchmarks/`.

## 1. Runs

1.1 `build_runs` returns one `Run` per distinct `run_id`. Drift records
(`case_id == "_production"`) produce no run.

1.2 Status. With a cell record: `code_finished` and `grading` are the
recorded ones. Without: `cell_progress` over the run's records, and
`grading_from_score(has_oracle, code_finished, score)` where `has_oracle`
is "an oracle-scope record exists". `status_derived` is true exactly in
the second case.

1.3 `status` is `lost` when code did not finish, whatever the grading
label; otherwise it is the grading label (`graded`, `grading_failed`,
`no_oracle`).

1.4 `oracle_passed` and `oracle_total` are set only on a graded run, from
the oracle record's `passed` and `total` components. On a lost run every
oracle-scope and oracle-task record is ignored by every view and counted
in `discarded_oracle_records` (oracle-scope records only).

1.5 Arm: research R-3 order. `arm_recovered` is false only when a record
carried `arm`.

1.6 `generation` is `pre012` when the run's records have no
`kroker_commit`, else `012`. A run never has records of both kinds; if one
does, it is `012` and a note names the run.

1.7 `totals(runs)`: `started == graded + lost + grading_failed +
no_oracle`. `sum(lost_by_stage.values()) == lost`.

1.8 `group_runs` keys on `(case, harness, arm, generation, commit)`. A
group's `mean`, `sd`, `lo`, `hi`, `all_pass` are over its graded runs.
`sd` is `None` under two graded runs. `low_n` is true under five.

## 2. Run-by-run grid

2.1 One row per run, inside its group; groups ordered by case, arm,
generation (012 first), then the start of the group's first run; rows by
start.

2.2 Group header text: arm, commit (`not recorded` for `None`, `unknown`
as is), `untrusted (pre-012)` for a pre-012 group, `arm recovered` when
any run's arm was recovered, started, graded, lost, mean, sd, lo to hi,
all-pass `k/n`. Under `low_n` the figures carry the suffix `(low n)` in
text and a grey class in HTML.

2.3 Row: status (`derived` appended when derived), last stage as
recorded, one cell per rendered stage, oracle `passed/total`, first
attempt `k/n`, after repair `k/n`, tokens, wall-clock seconds, `dirty`
when `tree_dirty` is true, `unfinished` when `pipeline_finished` is false
and the run is not lost.

2.4 Stage cell mark:

| Mark | When |
|---|---|
| `first` | run stage: its first record passed. Task stage: every task's first record at the stage passed. |
| `repaired` | not `first`, and the last record (per task for a task stage) passed |
| `failed` | the last record (any task's, for a task stage) did not pass |
| `not_evaluated` | the stage's only verdicts are `not_evaluated` |
| `copy` | qa under `qa_is_copy` |
| `not_reached` | the run has no record at the stage |

"Passed" is `gate_passed(stage, outcome)`. A task stage's cell also
carries `tasks = (passed first time, total)`.

2.5 Markdown: one pipe table per group, ASCII only, no cell containing
`---`. Header cells, in order: `run`, `status`, `last`, one cell per
rendered stage prefixed `s:` (for example `s:code`), `oracle`,
`first attempt`, `after repair`, `tokens`, `wall (s)`, `flags`. No header
cell is exactly `case` or exactly `stage`. HTML and JSON carry the same
figures.

2.6 A record whose stage is not in `CELL_STAGE_ORDER` (and is not `oracle`
or `cell`) gets a column after the ordered stages, sorted by name. The
same trailing columns appear in the grid and in every heatmap layer.

## 3. Heatmap layers

3.1 Rows: one per `(case, harness, arm, generation)`. Columns: the stages
of `CELL_STAGE_ORDER` in order, then any stage outside it by name (§2.6),
then `oracle`; a column is present when
any layer of any row has a non-blank cell in it; all four layers have the
same columns.

3.2 Attrition. Position of a lost run: `code` when its last stage is in
`TASK_LOOP_STAGES`, else its last stage; none when it has no stage record.
A non-lost run's position is its last stage. `reached(S)` = runs whose
position is at or after S. Cell at S: `num` = lost runs positioned at S,
`den` = `reached(S)`, `observations = den`. Blank when no run of the row
wrote a record at S, except `code`, which is also non-blank when a lost
run is positioned there. Row header: `lost_before_code` (lost runs
positioned before `code`, plus those with no stage record), `started`,
`lost_tokens`, `no_stage_recorded`.

3.3 First-attempt failure. Task stages: for each `(run, task)` with a
record at the stage, the first by `attempt_sort_key`. Other stages: for
each run with a record at the stage, the first by start time. A unit whose
first verdict is `not_evaluated` is left out. `num` = units where
`gate_passed` is false; `den = observations` = units. The qa cell of a row
whose runs are all `qa_is_copy` has state `copy`; in a row that mixes, the
copy runs are left out.

3.4 Wasted tokens. For each record with token data at stage S:
wasted when the run is lost; or it has a task and an attempt and a later
code attempt of that task exists; or it has a task and the task's last
code attempt did not pass. `num` = wasted tokens, `den` = all tokens at S,
`observations` = records with token data, `not_measured` = records at S
without. Cell-scope, oracle and oracle-task records are in no cell.

3.5 Oracle. One `OracleMark` per graded run in start order. The `oracle`
column of the three other layers is blank.

3.6 Each record contributes to at most one cell of a layer. The layers do
not share a number.

3.7 A note under the heatmap: "A stage record is written when the stage
ends. A run that stopped inside a stage shows the stage before it as its
last."

## 4. Scales and cell states

4.1 `step_for(layer, value)`:

| Layer | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| `attrition` | `== 0` | `<= 0.05` | `<= 0.10` | `<= 0.25` | above |
| `first_attempt` | `== 0` | `<= 0.10` | `<= 0.25` | `<= 0.50` | above |
| `wasted_tokens` | `== 0` | `<= 0.10` | `<= 0.25` | `<= 0.50` | above |
| `oracle` | `== 1` | `>= 0.90` | `>= 0.75` | `>= 0.50` | below |

4.2 Cell state: `blank` when `den == 0` or §3.2's rule says so; `copy`
per §3.3; `low_n` when `observations < 5`; else `value`.

4.3 Rendering: `value` cells take the class of their step; `low_n` cells
take the grey class, whatever their value; `blank` cells have no text and
no fill; `copy` cells read `copy of code`. Every `value` and `low_n` cell
prints the value and `num/den`. Oracle marks print `passed/total` and take
their step's class; the grey rule applies to the group figures (§1.8), not
to marks.

4.4 The five step classes are one hue at five lightness levels. The
stylesheet uses no red and green pair. The same value gives the same
class in any report.

## 5. Scores in summary rows

5.1 Rows are keyed `(case, stage, harness, arm, generation)`. No row
holds records of two runs' generations.

5.2 `mean_quality`: mean of `quality.score` over counted records whose
judge is in `RUBRIC_JUDGES`; on the oracle row, the mean partial credit
of the row's graded runs. `None` otherwise.

5.3 `pass_n / pass_d`: on a stage with no rubric-judged record, records
where `gate_passed` is true over records where it is not `None`. On the
oracle row `all_pass` is set and `pass_n / pass_d` are `None`.

5.4 On the code row: `first_attempt` and `after_repair` are the sums of
the row's runs' `(k, n)`. The code row's `mean_quality` is `None`: no
share of attempts is shown.

5.5 A qa row built only from `qa_is_copy` runs shows `copy of code` in
place of its pass rate.

5.6 Records of lost runs stay in stage rows (the stage ran). Oracle
records of lost runs are in no row.

## 6. Gate versus oracle

6.1 Input: graded runs. One `GateRow` per heatmap row and gate in
`GATE_STAGES` that has a verdict in at least one of those runs.

6.2 Run verdict of a gate: research R-9. A run with no verdict, or only
`not_evaluated`, is not in the gate's `n`.

6.3 Oracle verdict: `passed == total` and `total > 0`.

6.4 `agree_rate = (pass_pass + reject_fail) / n`.
`escape_rate = pass_fail / (pass_pass + pass_fail)`.
`false_reject_rate = reject_pass / (reject_pass + reject_fail)`.
A rate with a zero denominator is `None` and reads `n/a (0)`.
`low_n[rate]` is true when that rate's denominator is under five.

6.5 `mean_credit_passed` and `mean_credit_rejected`: mean partial credit
of the runs on each side; `None` for an empty side.

6.6 qa over runs that are all `qa_is_copy`: `is_copy` true, counts zero,
the row reads `copy of code (pre-012)`.

## 7. Composite

7.1 `composite_shown(runs)[case].shown` is true exactly when the case has
two or more `(harness, arm)` pairs within one generation that each have a
graded run.

7.2 Not shown: every summary's `composite` is `None`; `report.md` has no
`composite` column; one line reads `composite not shown for <case>: <n>
arm(s) with a graded run; it needs two`. The experiment comparison prints
no composite column.

7.3 Shown: per `(case, stage)`, each arm's mean cost and mean wall-clock;
an axis counts when two or more arms have it; it is normalised against the
largest arm mean. Quality and weights as today.

7.4 `--weights` given while no selected case shows a composite: exit 0 and
one line `weights not used: no composite shown`.

## 8. `report.md`

Section order, each present only when it has content:

1. `# Benchmark report`
2. `## Runs`: totals line (`runs started`, `graded`, `lost` with the count
   per last stage, `grading failed`, `no oracle`, `discarded oracle
   records`, `statuses derived`), then the grid (§2).
3. `## Stages`: the summary table for 012 rows. Columns: case, stage,
   harness, arm, model, n, quality, pass rate, first attempt, after
   repair, tokens, cost ($), wall (s), [composite], trust.
4. `## Pre-012 records (untrusted)`: the same table for pre-012 rows.
5. `## Gate versus oracle`.
6. `## Stage failures`.
7. `## Success criteria`.
8. `## Notes` (composite line, weights line, judge-mix notes, evidence
   notes).
9. Calibration.

ASCII only. The 012 `## Cells` section is replaced by the totals line of
`## Runs`. `render_markdown` emits all nine items, each heading exactly
once: the success-criteria markdown and the notes are passed to it
(`sc_rollup=`, `notes=`), and `write_score` appends nothing after its
output. The stage table's fourth column is headed `arm`.

## 9. Success criteria

9.1 Summaries are read at `export_root / run_id / "summary.json"` for each
run of the selection and nowhere else. A summary whose own `run_id` is not
the run's is ignored with a note.

9.2 A missing or unreadable summary is "no summary"; nothing raises.

9.3 The section opens with `N of M runs left a run summary`.

9.4 SC-1, SC-4, SC-6 take only those summaries; SC-3 takes the selection's
records. A rate under five observations reads `n/a` with its count.

## 10. Waste

10.1 `waste_measured(r)` per research R-15.

10.2 The waste matrix and the experiment comparison leave unmeasured
records out of every sum and mean. `WasteMatrix.not_measured` counts them;
the HTML prints `N attempts not measured (captured before tool events
were parsed)` when N > 0. Runs are counted by `run_id`.

10.3 `digest_of` writes `capture_rev = 1` for every harness.
`WasteBag.from_digest` copies it.

10.4 `OpenCodeHarness.normalise_session` on the captured stream fixture:
`tool_calls > 0`; at least one `file_read`, one `file_write` and one
`command` event when the fixture contains them; a command the fixture
shows as failed has a non-zero `exit_code`; a tool call the stream reports
twice is counted once. The hand-written stream in
`tests/test_opencode_normalise.py` still normalises as it does today.

10.5 The claude and cursor normalisers are not edited; their tests pass
unedited.

## 11. Outputs and compatibility

11.1 Files written into the output directory: `report.md`, `grid.html`,
`grid.json`, `heatmap.html`, `heatmap.json`, `gate-oracle.html`,
`gate-oracle.json`, `sc-rollup.html`, `sc-rollup.json`, and per case the
existing waste, agreement, task and error matrix files. Nothing else is
written anywhere.

11.2 `finalize_benchmark_report(bench_run_id)` writes the same files into
the bench directory by calling the same writer, and returns the path of
`report.md`. For one set of records the figures in the two `report.md`
files are identical.

11.3 No file ending `.jsonl` under the records root is opened for writing.

11.4 `sdlc benchmark score` imports no Temporal client and opens no
connection.

11.5 `scripts/aggregate_benchmarks.py` on a `report.md` whose first table
is the grid reads the stage table (the first table with header cells
exactly `case` and `stage`); on one with no `composite` column its
output is unchanged for directories that have records.

11.6 `CANONICAL_STAGES` is unchanged; the graph and dashboard tests that
import it pass unedited.

## 12. Expected figures on the stored records

Counted on 2026-10-09 by a read-only script and recounted by the skeptic.

| Selector | Figure | Value |
|---|---|---|
| case cat-cafe-monitoring | runs started / graded / lost | 18 / 10 / 8 |
| | lost by last stage | research 4, clarify 4 |
| | statuses derived | 18 |
| | discarded oracle records | 8 |
| | groups | 1 (pre-012, commit not recorded, arm `zai-coding-plan-glm-5.2`, recovered) |
| | mean partial credit | 85/120 = 0.708 |
| | all-pass | 1/10 |
| | first attempt / after repair | 84/113, 111/113 |
| | attrition | research 4/18 (step 3), clarify 4/14 (step 4), lost before code 8/18 |
| | analyze vs oracle | rejected 10, of which oracle pass 1; passed 0; escape n/a |
| | merge vs oracle | rejected 7, of which oracle pass 1; passed 3, of which oracle fail 3; escape 3/3 low n |
| | qa | copy of code |
| | composite | not shown |
| | success criteria | 0 of 18 runs left a run summary |
| case todo-api-greenfield | pre-012 group | 5 started, 4 graded, 1 lost (attrition position `code`) |
| | 012 groups | commit `unknown`: 1 graded; commit `b3344416`: 1 graded, 1 lost at clarify |
| all | invariant §1.7 | holds for every case |

A figure in this table that the implementation does not reproduce is a
stop (plan SG-2), not a number to edit.

## 13. Requirement to proof

All proofs are fast-tier tests unless marked. "Stored" = the test reads
`runs/benchmarks` in place, read-only, and is skipped when the directory
is absent.

| Requirement | Proof |
|---|---|
| FR-001, FR-006 | `tests/test_benchmark_runs.py` (§1.1, §1.5); `test_benchmark_stored_scores.py` stored (§12 groups) |
| FR-002 | `test_benchmark_runs.py` (§1.2, §1.3); `test_benchmark_cell.py` (moved bodies, unedited assertions) |
| FR-003 | `test_benchmark_runs.py` (§1.4); stored (§12 discarded) |
| FR-004, SC-004 | `test_benchmark_runs.py` (§1.7); stored (all cases) |
| FR-005 | `test_benchmark_runs.py` (§1.6, §1.8); `test_benchmark_scoring.py` (§5.1) |
| FR-007 to FR-011 | `tests/test_benchmark_grid.py` (§2); `test_benchmark_report.py` (§8 order) |
| FR-012 to FR-017, FR-021 | `tests/test_benchmark_heatmap.py` rewritten (§3) |
| FR-018 to FR-020, SC-007 | `tests/test_benchmark_heatmap_render.py` rewritten (§4) |
| FR-022 to FR-024 | `test_benchmark_runs.py`; `test_benchmark_scoring.py` (§5.2, §5.3) |
| FR-025 to FR-028, SC-005 | `test_benchmark_runs.py` (tasks, qa copy); `test_benchmark_scoring.py` (§5.4, §5.5); stored |
| FR-029 to FR-032, SC-009 | `tests/test_benchmark_gate_oracle.py` (§6); stored |
| FR-033 | `test_benchmark_agreement_matrix.py` (title) |
| FR-034 to FR-036, SC-006 | `test_benchmark_scoring.py`, `test_benchmark_report.py`, `test_benchmark_experiments.py`, `test_benchmark_score.py` (§7) |
| FR-037 to FR-039, SC-008 | `test_benchmark_evidence.py`, `test_benchmark_sc_rollup.py` (§9); stored |
| FR-040 | `test_benchmark_waste_bag.py`, `test_benchmark_waste_matrix.py`, `test_benchmark_experiments.py` (§10.1 to §10.3); `test_session_capture.py` (mark written) |
| FR-041, SC-011 | `test_opencode_normalise.py` on the captured fixture (§10.4) |
| FR-042 | claude and cursor normaliser tests unedited (§10.5) |
| FR-043, SC-010 | fingerprint of stored record files before and after quickstart §2; `test_benchmark_legacy_records.py` unedited |
| FR-044 | `test_benchmark_report.py`: finalize and score on one record set (§11.2) |
| FR-045 | `test_benchmark_score.py`: file list (§11.1) |
| FR-046 | `test_benchmark_score.py` or `test_e36_imports.py`: import check (§11.4) |
| FR-047 | `test_aggregate_benchmarks.py` (§11.5) |
| FR-048 | quickstart §2; no run command in tasks |
| FR-049 | document table in the plan; `scripts/check_clauses.py` read |
| SC-001 to SC-003 | stored (§12) and quickstart §2 |
| SC-012 | quickstart §2, timed |
