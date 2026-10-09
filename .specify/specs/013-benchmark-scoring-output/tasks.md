# Tasks: Benchmark Scoring Output Rework (round 013, Phase 2)

**Input**: `.specify/specs/013-benchmark-scoring-output/` (spec.md, plan.md, research.md, data-model.md, contracts/scoring-output.md, quickstart.md)

**Tests**: required (plan "Work order"; contract §13). In every task the failing test is written first and seen red for the stated reason, then the code; both land in that task's one commit, so no commit on the branch is red. A test marked PIN pins behaviour that already exists and must pass on first run; a red PIN is a stop-guard.

**Scope**: user stories 1 to 9, FR-001 to FR-049, SC-001 to SC-012. Report item 2.9 (erosion and verbosity) has no task here (ruling R1).

`B/` = `src/sdlc/benchmarks/`. `H/` = `src/sdlc/harness/`. "Contract" = `contracts/scoring-output.md`. "Names" = `data-model.md`. "R-n" = `research.md`. "Stored test" = `tests/test_benchmark_stored_scores.py`.

## Standing rules for every task

- **Names.** `data-model.md` is the only source of names, field names and fixed strings. Copy; do not retype from memory. A name that is needed and not there is a stop (SG-1).
- **Stored records are read-only.** Nothing under `runs/` is modified, moved, deleted or added. `runs/` is git-ignored, so the check is the **records fingerprint**: on the host, `python -c "import hashlib,pathlib;fs=sorted(pathlib.Path('runs/benchmarks').rglob('*.jsonl'));h=hashlib.sha256();[h.update(str(f.relative_to('runs/benchmarks')).replace(chr(92),'/').encode()+hashlib.sha256(f.read_bytes()).digest()) for f in fs];print(len(fs),h.hexdigest())"`. T001 records its output; it is re-run before every commit and must print the same line. `git ls-files runs/` stays empty. Any score command run during the round carries `--out <a directory outside runs/>`. Tests read stored records in place or build records in memory; a test that writes uses `tmp_path`.
- **The run is the unit.** A view reads `Run` objects from `B/runs.py`. Only `B/task_matrix.py`, `B/error_matrix.py` and `B/agreement_matrix.py` keep reading raw records.
- **No reader guesses.** Absent reads as "not recorded" or "not measured". Every figure prints its denominator. Under `MIN_OBSERVATIONS` it is grey or `n/a`.
- **Import discipline.** `B/runs.py`, `B/grid.py`, `B/gate_oracle.py`, `B/heatmap.py`, `B/heatmap_render.py` import no `temporalio`, and none of `B/report.py`, `B/cell.py`, `B/recorder.py`. `B/heatmap.py` imports only `B/models.py`, `B/runs.py`, pydantic and the standard library at module scope. `B/report.py` and `B/score.py` import the new modules inside functions.
- **Run environment.** Python: the `kroker-dev` container only (`uv run …`), never the host venv. Git on the branch's worktree: the host only. One test run per shell call, never two chained. `addopts` already has `-q`.
- **Convergence.** A task is not done while its named test files, `uv run ruff check .`, `uv run ruff format --check .` or `uv run mypy` (no new errors against the T001 baseline) are red, or `python scripts/check_file_size.py` reports a file over 1000 lines.
- **Commit**: one per task; subject and body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add` argument; no heredocs; every file written with the Write tool.
- **Reviewer gate** is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N's diff.
- **Read first**: root `AGENTS.md`. Neither `B/` nor `H/` has its own.
- **Forbidden paths**: everything under `runs/` and `docs/reports/`; every file under `tests/replay/`; everything under `src/sdlc/stages/`, `src/sdlc/workflows/`, `src/sdlc/graph/`, `src/sdlc/dashboard/`; `B/workflow.py`, `B/oracle.py`, `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/drift.py`, `B/task_matrix.py`, `B/error_matrix.py`, `B/calibration.py`; `H/claude_code.py`, `H/cursor.py`, `H/base.py`; `agents/`; `interfaces/`; every `AGENTS.md`; `CLAUDE.md`; `pyproject.toml` and `uv.lock`; every script except `scripts/aggregate_benchmarks.py`; earlier `.specify/specs/*` and `.specify/bugs/*`; the user's uncommitted and untracked files in the primary checkout. The tuple `CANONICAL_STAGES` in `B/heatmap.py` is not edited.
- **Tests that must pass unedited**: existing assertions on `summarize_cell` and `grading_status` in `tests/test_benchmark_cell.py`; all of `tests/test_benchmark_workflow.py` (the workflow's config and record builders are not touched by this round); `tests/test_benchmark_legacy_records.py`; `tests/graph/test_graph_node_types.py`; `tests/test_dashboard_graph_wire.py`; `tests/test_run_state_query.py`; `tests/test_calibration_render.py`; `tests/test_claude_stream_normalise.py`; `tests/test_cursor_harness.py`; the existing hand-written case in `tests/test_opencode_normalise.py`.
- Line numbers are as of main `35d1b056`; find passages by their text.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** A name or rule is needed that the spec set does not define; the T001 name check finds a hit; an edit to a forbidden path or to a "must pass unedited" test appears necessary; any test under `tests/replay/` changes result against the T001 baseline. Do not edit a test to pass.
- **SG-2** A T001 "Verify" item fails; T001's grep finds a reader of a changed output the plan does not name; or code does not reproduce a figure of contract §12. A §12 figure is never edited to match the code.
- **SG-3** Any file would pass 800 lines.
- **SG-4** T015: no parser code before the orchestrator has answered on the captured stream. A hand-written fixture does not close FR-041.
- **SG-5** The records fingerprint differs from the T001 value, `git ls-files runs/` prints anything, or a score was written under `runs/`.
- **SG-6** A `temporal` test named in a gate reports "deselected"; the stored test reports "skipped" in T017; a test marked RED passes before its code; a PIN is red.
- **SG-7** An import the "Import discipline" rule forbids appears necessary.

## Phase order

| Phase | Purpose | Story | Plan steps | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | known start, every design assumption checked | — | 0 | 1 |
| 2 Foundation | status functions shared; the run model | all (US1 delivered) | 1, 2 | 2 |
| 3 Summary rows | credit, pass rate, two code scores, composite | US4, US5, US7 | 3 | 2 |
| 4 Grid | the main view | US2 (P1) | 4 | 1 |
| 5 Heatmap | four layers, fixed scales | US3 (P1) | 5 | 2 |
| 6 Gate versus oracle | agreement, escape, false reject | US6 | 6 | 1 |
| 7 Success criteria | scoped by run id | US8 | 7 | 1 |
| 8 Assembly | report order, one writer, the script | US1, US2, all | 8 | 3 |
| 9 Waste | capture mark, not measured, opencode parser | US9 (P3) | 9a, 9b | 2 |
| 10 Close-out | documents, gates, stored validation | — | 10, 11 | 2 |

Phase 3 comes before the two remaining P1 stories on purpose: the grid and the heatmap print figures that the summary rows and the run model define, and US1's numbers (the exit criterion) are already true after phase 2. Phases 3 to 7 each depend only on phase 2 and may be reordered by the orchestrator. Phase 9 depends only on phase 1.

---

## Phase 1: Setup and baseline (no source edits)

- [ ] T001 Create branch `013-benchmark-scoring-output` from current main in the worktree the orchestrator names; confirm `kroker-dev` is bound to that tree and that `runs/benchmarks` is visible inside it (`ls runs/benchmarks | head`). If main has moved past `35d1b056`, on the host run `git diff --stat 35d1b056 HEAD -- src/sdlc/benchmarks src/sdlc/harness scripts/aggregate_benchmarks.py BENCHMARK.md` and report anything it prints (SG-1). Run, one per call, in the container: `uv run pytest`; `uv run pytest -m temporal tests/replay`; `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run mypy`. On the host: `python scripts/check_file_size.py`; `python scripts/check_clauses.py`; `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out <a temp file outside the repo>` and keep that output for T013 and T017. Compute the records fingerprint and record its line. Do the name check of Names §8 (on the host with the Grep tool or `git grep -nE "<the same alternation>" -- src tests interfaces scripts` when `rg` is not installed). Then the Verify items, each by reading code or stored records, each recorded with file:line evidence:
  (a) R-2: for each of the three stored 012 todo-api runs, the status derived from its stage records (code finished = a record at `analyze`, `merge` or `deploy`; last stage by `CELL_STAGE_ORDER`) equals the one on its cell record;
  (b) R-3: every stored non-drift record's `run_id` has the shape `<bench_run_id>/<case>#<harness>[:lead]#<arm>`; list any that does not;
  (c) R-3: `B/workflow.py` near line 308 builds the child id as `f"{bench_run_id}/{cell.cell_id}"`;
  (d) R-9: `src/sdlc/stages/merge/step.py` near line 654 writes `REVISED if overrides else PASS` on the approval path, and architecture, plan and deploy write `REVISED` when the gate did not approve;
  (e) R-12: for the two stored benchmark run summaries, the file's own `run_id` equals the record `run_id`, and `src/sdlc/observability/activities.py` writes to `root / run_id`;
  (f) R-15: which `HarnessKind` (and `lead_harness`) is on the code records of a crew cell whose lead is opencode, read from `src/sdlc/crew/activities.py` near line 349 and from one stored crew-probe record; state whether "harness or lead harness is opencode" covers it;
  (g) R-15: no model with `extra="forbid"` nests `SessionDigest`, and no file under `tests/replay/` embeds one;
  (h) grep `src`, `scripts`, `tests`, `interfaces` for readers of `heatmap.json` content, of `HeatmapCell`, `build_heatmap`, `max_density`, of the `## Cells` heading, of `sc-rollup` and of `agreement-matrix`; list every hit. A hit outside `B/`, `tests/` and the places plan.md names is SG-2;
  (i) list every test that asserts on `composite`, `_TABLE_HEADER`, `MIN_RUNS` or `load_run_summaries`.
  Write `.specify/specs/013-benchmark-scoring-output/baseline.md`: base sha, every command's result and counts, mypy error count, the replay result, the fingerprint line, name-check outcome, items (a) to (i), and line counts of `B/models.py`, `B/report.py`, `B/heatmap.py`, `B/scoring.py`, `B/score.py`, `B/sc_rollup.py`, `scripts/aggregate_benchmarks.py`. Any item that contradicts research.md is SG-2: stop and report before committing anything else. Commit (spec set + baseline).

**Checkpoint**: baseline.md exists with every gate's result and items (a) to (i); no source file differs from the base.

---

## Phase 2: Foundation — one status rule, one run model (blocks every story; delivers US1)

**Goal**: records become runs once; each run has one arm and one status; lost runs are counted and their oracle records discarded.

**Independent test**: `build_runs` on the stored cat-cafe records gives 18 runs, 10 graded, 8 lost (research 4, clarify 4), one group, 85 of 120 tests.

- [ ] T002 Status functions shared with the writer. RED first in `tests/test_benchmark_models.py`: `cell_progress(records)` returns `(None, False)` for no records; `("clarify", False)` for research and clarify; `("handoff", False)` for code, qa, review, handoff with no post-code record; `("merge", True)` through merge; a `cell`-stage and an `oracle`-stage record never become the last stage; `grading_from_score` for every row of the 012 contract §3 table (`no_oracle` whatever `code_finished`; `not_graded`; `graded` for score 0.0 and for 1.0; `grading_failed` for score `None`); `TASK_LOOP_STAGES` equals the seven names of Names §2 and is a subset of `CELL_STAGE_ORDER`; `RUBRIC_JUDGES == {"llm_judge", "staged_rubric"}`. Then add the four names to `B/models.py`, make `summarize_cell` and `grading_status` in `B/cell.py` call the two functions (signatures and return types unchanged), and make `score._SCORING_JUDGES` an alias of `RUBRIC_JUDGES`. PIN: `tests/test_benchmark_cell.py` (the only file that asserts on the two functions) and `tests/test_score_judge_mix.py` pass unedited; `tests/test_benchmark_workflow.py` passes unedited too (it pins the workflow's config and record builders, which this task does not touch). Commit.
- [ ] T003 [US1] The run model. RED first in new `tests/test_benchmark_runs.py`, on records built in memory (contract §1): one `Run` per `run_id`, drift records give none (§1.1); a run with a cell record takes `code_finished` and `grading` from it and `status_derived` is false; a run without one derives them and `status_derived` is true (§1.2); status table of R-2, including a run of a case with no oracle that stopped at `plan` → `lost`, and a code-finished run with no oracle record → `no_oracle` (§1.3); a lost run with an oracle record and two oracle-task records has `oracle_passed is None`, `discarded_oracle_records == 1`, and a graded run takes `passed` and `total` from the oracle record's components (§1.4); arm order of R-3 with `arm_recovered` (a 012 record with `arm`; a pre-012 run whose records carry three different `model` strings and whose `run_id` ends `#opencode#a-1` → arm `a-1`, recovered; a `run_id` of unexpected shape → the oracle record's model; no oracle → `arm_label` of the first record) (§1.5); `parse_run_id` on an id formed from a real `BenchmarkCell` exactly as `B/workflow.py` forms it, including a crew cell with a lead and an arm containing `#`; generation and the mixed-run note (§1.6); `totals` sums and `lost_by_stage` with key `none` (§1.7); `group_runs` key, `mean`, `sd` (`None` for one graded run; sample deviation for three), `lo`, `hi`, `all_pass`, `low_n` at four and at five graded runs, and that runs of two generations never share a group (§1.8); task outcomes per R-5 (first passes; passes on second attempt; never passes; attempt numbers absent → ordered by start time); `qa_is_copy` true for a pre-012 run whose qa outcomes equal code's on every attempt, false when one differs, false for any 012 run; `gate_passed` per R-9 (`pass` → True; `revise` on `merge` → True; `revise` on `plan` → False; `fail`, `escalated` → False; `not_evaluated` → None); `composite_shown` per contract §7.1 (one arm; two arms one graded; two arms both graded; two arms in different generations → not shown); `Run.tokens` is `None` when no record carries tokens. Create new Stored test `tests/test_benchmark_stored_scores.py` (skips when the records root has no run directory; reads in place; resolves the root as `tests/test_benchmark_legacy_records.py` does) asserting the run-level rows of contract §12: cat-cafe started/graded/lost, lost by last stage, statuses derived, discarded oracle records, one group with its arm and flags, 85/120, 1/10, 84/113, 111/113; todo-api's three groups; §1.7 for every case in the corpus. Then create `B/runs.py` per Names §1. Commit.

**Checkpoint**: US1's figures are computed and pinned on the stored records. Nothing renders them yet.

---

## Phase 3: User Stories 4, 5 and 7 — the figures in summary rows (P2)

**Goal**: a summary row shows partial credit beside the all-pass rate, a pass rate for a verdict stage, first-attempt and after-repair scores for code, and a composite only when the case has two arms.

**Independent test**: `compute_summaries` on three tasks (one first-time pass, one repaired, one never) gives a code row with first attempt 1/3, after repair 2/3 and no quality.

- [ ] T004 [US4] [US5] Summary rows from runs. RED first in `tests/test_benchmark_scoring.py` (contract §5): rows are keyed `(case, stage, harness, arm, generation)` and a pre-012 run stored under three model labels gives one row per stage (§5.1); `mean_quality` comes only from records whose judge is in `RUBRIC_JUDGES`; the oracle row's `mean_quality` is the mean partial credit of graded runs and its `all_pass` is `(k, n)` (§5.2, §5.3); a verdict stage has `pass_n / pass_d` by `gate_passed`, with `not_evaluated` in neither, and merge `revise` counted as a pass (§5.3); the code row has `first_attempt` and `after_repair` summed over its runs and `mean_quality is None` (§5.4); a qa row built only from `qa_is_copy` runs has `qa_is_copy` true and `pass_n`, `pass_d` both `None`, and a qa row that mixes copy and non-copy runs counts only the non-copy runs (§5.5); a lost run's stage records are in their stage rows and its oracle record is in no row (§5.6); `tokens` is the mean per run. Add the optional fields of Names §2 to `BenchmarkSummary` in `B/models.py` (cases in `tests/test_benchmark_models.py`: defaults; existing constructions still valid). Rewrite `compute_summaries` in `B/scoring.py` to build runs once and key rows per R-11; `aggregate()` keeps its signature. Update the existing tests this changes on purpose, in this commit: in `tests/test_benchmark_scoring.py` the row-key assertions and the code row's quality; in `tests/test_benchmark_report.py`, `test_aggregate_reads_store_and_returns_summaries` and `test_aggregate_sort_is_deterministic_on_model_tie` (their two records share one `run_id` and now form one row: give the two records distinct run ids of the stored shape with distinct arms, keeping what each test is about); in `tests/test_benchmark_experiments.py`, `test_compute_deltas_reports_quality_cost_and_wall` and `test_save_and_load_round_trip` (their fixture's judge is `contract`, so quality is now `None`: set the fixture's judge to `llm_judge`). Run `tests/test_benchmark_report.py`, `tests/test_benchmark_experiments.py`, `tests/test_benchmark_score.py`, `tests/test_benchmark_cli.py` green before committing; any other test that fails in them is reported, not edited (SG-1). Commit.
- [ ] T005 [US7] Composite across arms, or none. RED first in `tests/test_benchmark_scoring.py` (contract §7): one arm → every row's `composite is None`; two arms with a graded run each → a composite per arm where cost and speed are normalised against the larger arm mean of the `(case, stage)`, and an axis with data on only one arm is left out of the weights; two arms of different generations → `None`; a two-arm case whose rows have no quality still reports `shown` with `composite None` rows (the decision comes from `composite_shown`, not from row values). Replace the body of `_composite` and the normalisation block in `B/scoring.py` per R-10. Update the composite assertions of `tests/test_benchmark_scoring.py` and `tests/test_benchmark_report.py` that the plan table names. Commit.

**Checkpoint**: every figure the report will print exists on a summary row or a run.

---

## Phase 4: User Story 2 — the run-by-run grid (P1)

**Goal**: one row per run, grouped by arm and commit, with mean and spread on each group.

**Independent test**: runs from two commits under one arm give two groups, each with its own header and one row per run.

- [ ] T006 [US2] Grid. RED first in new `tests/test_benchmark_grid.py` (contract §2): group order and row order (§2.1); header text for a 012 group, for a commit of `None` (`not recorded`), for `unknown`, for a pre-012 group (`untrusted (pre-012)`), with `arm recovered`, and the `(low n)` suffix and grey class under five graded runs, `sd` reading `n/a` for one (§2.2); a row's status with `derived`, last stage as recorded (a run lost in the task loop shows `handoff`, not `code`), oracle `passed/total`, the two scores, tokens, wall-clock, `dirty`, `unfinished` (§2.3); every mark of the §2.4 table, with merge `revise` giving `first`, a task stage carrying `tasks`, qa under `qa_is_copy` giving `copy`; the markdown header cells exactly as §2.5 lists them, ASCII only, no cell containing `---`, no header cell equal to `case` or `stage`; a record whose stage is outside `CELL_STAGE_ORDER` gets a trailing column (§2.6); the JSON carries the same figures and no raw records. Create `B/grid.py` per Names §5. Commit.

**Checkpoint**: US2 renders on its own from `build_runs` output.

---

## Phase 5: User Story 3 — the layered heatmap (P1)

**Goal**: four layers on identical stage columns, fixed colour steps, a denominator in every cell, grey under five observations.

**Independent test**: one task that fails its first attempt and passes its second appears as one failed first attempt, as the first attempt's tokens in the wasted layer, and nowhere else.

- [ ] T007 [US3] Layers, added beside the old heatmap. The old model (`Heatmap`, `HeatmapCell`, `build_heatmap`, the old `render_heatmap_html`) and its three test files stay untouched in this task, so `B/report.py` keeps working; T008 removes them. RED first in new `tests/test_benchmark_heatmap_layers.py` (contract §3): rows and identical columns across layers, trailing unknown-stage column, `oracle` last (§3.1); attrition positions, `reached`, the task-loop fold to `code`, blank for a stage no run of the row wrote (a case with research disabled), `code` non-blank when a run was lost in the loop, and the row header's `lost_before_code`, `lost_tokens`, `no_stage_recorded` (§3.2); first-attempt units for a task stage and a run stage, `not_evaluated` left out, merge `revise` not a failure, qa `copy` state, and that a second attempt changes nothing in this layer (§3.3); wasted tokens for a lost run's research record, a superseded attempt's code, qa and review records, a never-passed task's last attempt, a handoff record with no attempt number (wasted only when its run is lost or its task never passed), a record with no token data counted in `not_measured`, and that cell, oracle and oracle-task records are in no cell (§3.4); one oracle mark per graded run in start order and none for a lost run (§3.5); the spec's US3 scenario 1 as a single test (§3.6); `CANONICAL_STAGES` is byte-for-byte the base tuple (PIN: copy its 18 names into the test). Add to `B/heatmap.py`, below the old code, the layered names of Names §3 except the JSON renderer (`LAYERS`, `ORACLE_COLUMN`, `LayerCell`, `OracleMark`, `HeatmapRow`, `LayeredHeatmap`, `build_layers`), and the comment Names §3 asks for above `CANONICAL_STAGES`. Extend the Stored test with the attrition rows of contract §12 (research 4/18, clarify 4/14, 8/18 before code; todo-api's pre-012 lost run positioned at `code`). PIN: the five files that import `CANONICAL_STAGES` or the module (`tests/graph/test_graph_node_types.py`, `tests/test_dashboard_graph_wire.py`, `tests/test_run_state_query.py`, `tests/test_calibration_render.py`, `tests/test_e36_imports.py`) pass unedited. Commit.
- [ ] T008 [US3] Scales, rendering, and the old heatmap removed. Rewrite `tests/test_benchmark_heatmap_render.py` RED first (contract §4): `step_for` on every edge of the §4.1 table for all four layers (for `attrition`: 0 → 0, 0.05 → 1, 0.0501 → 2, 0.10 → 2, 0.25 → 3, 0.2501 → 4; the same pattern for the others; `oracle`: 1.0 → 0, 0.9 → 1, 0.75 → 2, 0.5 → 3, 0.49 → 4); cell state for `den == 0`, four observations, five observations, copy (§4.2); HTML: a `value` cell has its step's class and the text `value (num/den)`; a `low_n` cell has the grey class and still the text; a blank cell has neither; a copy cell reads `copy of code`; an oracle mark prints `passed/total` (§4.3); two heatmaps built from different data give the same class for the same value (SC-007); the stylesheet defines five step classes of one hue and a grey class, and the strings `green` and `hsl(120` do not occur (§4.4); the note of §3.7 is present; the calibration block is appended; the `includes N pre-012 records (untrusted)` line is kept. Create `B/heatmap_render.py` per Names §3 and make `render_heatmap_json` in `B/heatmap.py` serialise the layered model. Point `B/report.py::write_heatmap` at the new builder and renderers (it now takes runs; its callers in `B/report.py` and `B/score.py` pass `build_runs(records)`, imported inside the functions). Then remove from `B/heatmap.py` the names Names §3 lists as removed, leaving `CANONICAL_STAGES` byte for byte. Replace the content of `tests/test_benchmark_heatmap.py` with that of `tests/test_benchmark_heatmap_layers.py` and delete the latter (`git mv` over it), so the layer tests live under the name contract §13 uses. Remove `tests/test_benchmark_heatmap_fix_inflation.py` (R-6: its rule has no input in the layered model; say so in the commit body). Edit `tests/test_e36_imports.py` only if it names a removed symbol. Update the one stale comment in `src/sdlc/eval/verdict.py` near line 226. In `tests/test_benchmark_report.py` update `test_write_heatmap_emits_both_files` (it passes records; `write_heatmap` now takes runs). Run `tests/test_benchmark_report.py`, `tests/test_benchmark_score.py`, `tests/test_benchmark_cli.py` green. Commit.

**Checkpoint**: `heatmap.html` and `heatmap.json` carry the four layers. US3 is complete.

---

## Phase 6: User Story 6 — each gate against the oracle (P2)

**Goal**: per gate: the four counts, agreement, escape rate, false-reject rate, and mean partial credit on each side.

**Independent test**: four runs covering pass/pass, pass/fail, reject/pass, reject/fail give agreement 2 of 4, escape 1 of 2, false reject 1 of 2.

- [ ] T009 [US6] Gate versus oracle. RED first in new `tests/test_benchmark_gate_oracle.py` (contract §6): the four-run case above; only graded runs enter (§6.1); a run-level gate takes its last record, a task gate passes only when its last record passed for every task that has one (§6.2, R-9); merge `revise` is a pass; a gate with only `not_evaluated` in a run is not in `n`; oracle verdict needs `passed == total > 0` (§6.3); rates with a zero denominator are `None` and render `n/a (0)`, `low_n` per rate (§6.4); `mean_credit_passed` / `mean_credit_rejected`, `None` for an empty side (§6.5); qa over copy runs → `is_copy`, zero counts, text `copy of code (pre-012)` (§6.6); one row set per heatmap row, so pre-012 and 012 runs never share counts; markdown is ASCII; JSON has the keys of Names §4. In `tests/test_benchmark_agreement_matrix.py` add a RED assertion (none exists today): the HTML `<title>` and `<h1>` read `Reviewer vs adversary split - <case>`. Create `B/gate_oracle.py`; edit the title, heading and docstring of `B/agreement_matrix.py` only. Extend the Stored test with the analyze, merge and qa rows of contract §12. Commit.

**Checkpoint**: US6 is complete on its own.

---

## Phase 7: User Story 8 — success criteria scoped to the selection (P2)

**Goal**: the criteria are computed from the scored runs' own summaries and say how many there were.

**Independent test**: with summaries on disk for one selected run and for an unrelated pipeline run, only the first is loaded.

- [ ] T010 [US8] Summaries by run id. RED first in `tests/test_benchmark_evidence.py` (contract §9), on a `tmp_path` export root and records root: `load_evidence(case=...)` loads the summary at `export_root / run_id / "summary.json"` for each run of the selection and nothing else, with a `bf-e2e-x/summary.json` beside them left unread (§9.1); a summary whose own `run_id` differs is ignored with a note; a missing file, a malformed file and a path that cannot be opened are "no summary" with a note and no exception (§9.2); `selection_runs` and `summary_runs` are set; `--all` reads no summary outside the selection's run ids. RED in `tests/test_benchmark_sc_rollup.py`: the rollup carries the two counts and renders `N of M runs left a run summary` first in markdown and HTML (§9.3); with zero summaries SC-1, SC-4 and SC-6 read `n/a` with n=0 while SC-3 is still computed from records (§9.4); `MIN_RUNS is MIN_OBSERVATIONS`; SC-3 orders attempts with `attempt_sort_key`. Edit `B/evidence.py` (`load_run_summaries` stays, PIN its existing tests) and `B/sc_rollup.py`. Extend the Stored test: cat-cafe reads `0 of 18`. Commit.

**Checkpoint**: US8 is complete on its own.

---

## Phase 8: Assembly — the report, one writer, the script

**Goal**: `report.md` opens with the runs; the score command and the end-of-run report write the same files from the same aggregation; the documentation build still reads the stage table.

**Independent test**: the same records scored by `write_score` and by `finalize_benchmark_report` give byte-identical `report.md` bodies.

- [ ] T011 [US2] [US7] The text report. RED first in `tests/test_benchmark_report.py` (contract §8): section order; `## Runs` is first, opens with the totals line carrying all seven figures, then the grid markdown; the stage table has the columns of §8 item 3 in order, with `composite` present only when a selected case's decision is shown; the line `composite not shown for <case>: 1 arm(s) with a graded run; it needs two` in `## Notes` (§7.2); pre-012 rows under their own heading with the same header; a qa row of copy runs prints `copy of code`; `## Gate versus oracle` present when there are graded runs; no `## Cells` heading; ASCII only; a records list with no records still returns the "No records found" report. Also RED: with `sc_rollup=` and `notes=` given, `## Success criteria` and `## Notes` each appear once, in the §8 position, before the calibration block; the stage table's fourth header cell is `arm`. Replace `_TABLE_HEADER` with `_table_header(show_composite)`, rewrite `_summary_row` and `render_markdown` in `B/report.py` per Names §6, importing `grid`, `gate_oracle` and `runs` inside the functions. In `B/score.py::write_score` change only the composition: build the grid, the gate view and the decisions, pass them with the rollup and the notes into `render_markdown`, and stop appending `render_sc_rollup_markdown` and `_render_notes` after it (the new output files arrive in T012). Update the assertions the plan table names, and `test_render_markdown_012_rows_show_arm_in_cell_column` (the header cell is `arm`, no longer `cell`). Run `tests/test_benchmark_score.py` and `tests/test_benchmark_cli.py` green. Commit.
- [ ] T012 [US2] One writer for both paths. RED first in `tests/test_benchmark_score.py`: `write_score` returns and writes exactly the files of contract §11.1 for a one-case selection; the `report.md` it writes has the sections of contract §8 in order, each heading exactly once; `--weights` with no composite shown adds the line `weights not used: no composite shown` and exits 0 (§7.4), and with a two-arm fixture the line is absent; importing `sdlc.benchmarks.runs`, `.grid`, `.gate_oracle`, `.heatmap`, `.heatmap_render` in a fresh interpreter leaves `temporalio` out of `sys.modules` (§11.4; run it in a subprocess). RED in `tests/test_benchmark_report.py`: with `SDLC_BENCHMARKS_ROOT` and `SDLC_EXPORT_ROOT` at `tmp_path`, `finalize_benchmark_report(bench_run_id)` (activity function called directly) returns the path of `<root>/<bench_run_id>/report.md`, writes the §11.1 files beside it, and that `report.md` equals the one `write_score` writes for `load_evidence(bench=...)` to another directory (§11.2); no `.jsonl` file's bytes or mtime change (§11.3). In `tests/test_benchmark_cli.py` extend the file-list assertion. Edit `B/score.py` (`write_score` writes `grid.*` and `gate-oracle.*`, takes the composite decisions for the notes) and `B/report.py` (`finalize_benchmark_report` builds the evidence and calls `write_score` with the bench directory, imports inside the function; name, argument and return unchanged). In `B/experiments.py` give `render_deltas_markdown` the `show_composite` keyword and have `cli.dispatch_experiment_compare` pass the decision (true only when either side's case shows a composite); case in `tests/test_benchmark_experiments.py`. Edit `B/cli.py` only for that pass-through. Then `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` (it stubs the activity by name; must be green, not deselected). Commit.
- [ ] T013 The documentation script. RED first in `tests/test_aggregate_benchmarks.py` (contract §11.5): `parse_report` on a `report.md` whose first table is a grid table (header per contract §2.5) and whose second is the stage table returns the stage table's rows; on a base-shaped report with one table it returns what it returned at base (PIN); on a stage table with no `composite` column `rr.get("composite")` is `None` and the run's `overall` for a directory that has records is unchanged. Edit `parse_report` in `scripts/aggregate_benchmarks.py` per Names §6. On the host re-run the T001 command on `runs/benchmarks` and diff against the T001 output: equal (the stored `report.md` files are untouched). Commit.

**Checkpoint**: `sdlc benchmark score --case cat-cafe-monitoring --out <outside runs/>` writes the full directory; the records fingerprint equals the T001 value.

---

## Phase 9: User Story 9 — waste counters are measured, or say they are not (P3)

**Goal**: a stored opencode attempt with zero tool calls reads as not measured; new captures carry a mark; the opencode parser counts tool activity on a real stream.

**Independent test**: a stored-shape opencode bag (`capture_rev` absent, zero tool calls) is left out of the waste mean and counted; the same bag with `capture_rev=1` is a measured zero.

- [ ] T014 [P] [US9] The capture mark and the not-measured rule. RED first: in `tests/test_session_models.py`, `SessionDigest()` has `capture_rev is None` and a payload without the field validates; in `tests/test_session_capture.py`, the digest `capture_session` returns has `capture_rev == 1` for the opencode and the claude harness; in `tests/test_benchmark_waste_bag.py`, `WasteBag.from_digest` copies it and a stored-shape bag without it reads `None`; `waste_measured` per R-15 (bag `None` → False; opencode, mark `None`, zero tool calls → False; opencode, mark `None`, three tool calls → True; opencode, mark 1, zero tool calls → True; claude, mark `None`, zero tool calls → True; a crew record per T001(f)'s finding); in `tests/test_benchmark_waste_matrix.py`, unmeasured records are in no sum, `not_measured` counts them, the HTML prints the line of contract §10.2 when N > 0 and not when N = 0, and a two-cell bench run counts as two runs; in `tests/test_benchmark_experiments.py`, `_cells` leaves unmeasured records out. Update the fixtures the plan table names (all-zero opencode bags used as "clean" get `capture_rev=1`). Edit `H/models.py`, `H/session.py`, `B/models.py`, `B/waste_matrix.py`, `B/experiments.py`. Then `uv run pytest -m temporal tests/replay`: same result as T001 (SG-1 otherwise). Commit.
- [ ] T015 [US9] The opencode parser on a real stream. **Stop first (SG-4)**: report to the orchestrator that the fixture is needed and wait for one of: a stream file from the user; or clearance for one call, in a throwaway directory outside the repository, of `opencode run --format json "Create hello.txt containing hi, read it back, then run a command that exits with status 1"` on the cheapest configured model, stdout saved raw. Save the stream as `tests/fixtures/opencode/session_tools.jsonl`: every event line verbatim and in order; replace the absolute directory, the user name and the session id by fixed placeholders with a text substitution only; state in the commit body what was substituted and the opencode version. Read the stream and write down, in the task report, the actual top-level event type and the part and state field names for a tool call and for the failed command; where they differ from R-15 the code follows the stream and the difference is reported. RED first in `tests/test_opencode_normalise.py` (contract §10.4), on the fixture: `tool_calls > 0`; a `file_write` event with the written path; a `file_read` event with the read path; a `command` event; the failed command has a non-zero `exit_code` and `digest_of` counts one failed command; a tool call id that appears twice in the stream is counted once (if the fixture has none, build the duplicate in the test from a fixture line); `model_turns` and the token sums equal what the base parser gives on the same stream (PIN that half before editing). PIN: the existing hand-written case passes unedited. Edit `normalise_session` and `_TOOL_MAP` in `H/opencode.py` only. PIN: `tests/test_claude_stream_normalise.py`, `tests/test_cursor_harness.py`, `tests/test_harness_parse.py` pass unedited. If no stream can be had, do not write parser code: leave this task open, record FR-041 as open in `verification.md`, and tell the orchestrator. Commit.

**Checkpoint**: US9 is complete. Live confirmation on a benchmark run is a follow-up, not part of this round.

---

## Phase 10: Close-out

- [ ] T016 Documents. Edit by finding each passage by its text (plan "Document changes"): `BENCHMARK.md` §4.1 (replace the round 012 sentence on the share of attempts with the two task scores; partial credit beside the all-pass rate; verdicts are pass rates; the composite needs two arms), §4.3 (stored opencode counters not measured; the capture mark; tool events parsed from this round on, or "pending a captured stream" if T015 is open), §4.4 (four layers with unit and denominator each; the fixed scales table; grey under five; the run grid as the main view; gate versus oracle; the files a score writes; the `fail_reentry` axis and the per-task maximum of `fix_attempts` superseded; the known limit of contract §3.7), and the success-criteria passage (scoped to the scored runs' own summaries); `README.md` near lines 64 to 77 and 312 to 314; `ARCHITECTURE.md` near lines 473 and 830; `ROADMAP.md` (Phase 2 landed except 2.9; "Last verified"). On the host: `python scripts/check_clauses.py` and read it; `python scripts/check_file_size.py`. Commit.
- [ ] T017 Full gates and the stored-record validation. Run quickstart §1 row by row, one command per call. Run quickstart §2: the three score commands with `--out` outside `runs/`, time the cat-cafe one, and check every row of the three tables; then the records fingerprint (equal to T001), `git ls-files runs/` (empty) and the documentation script's output (equal to T001). Write `.specify/specs/013-benchmark-scoring-output/verification.md`: each row's command and result against the T001 baseline; each SC-001 to SC-012 with its evidence; FR-041's state; the open follow-ups of plan.md. Any red row is fixed in the task that owns it, with the reviewer gate, not here. File the plan's follow-ups under `.workspace/tasks/` only if the orchestrator asks. Commit.

---

## Dependencies

```text
T001 → T002 → T003 → { T004 → T005, T006, T007 → T008, T009, T010 } → T011 → T012 → T013 → T016 → T017
T001 → T014 → T015 (any time after T001; T015 waits on the stream)
```

- T011 needs T004, T005, T006 and T009 (it prints their output). T012 needs T008, T010 and T011.
- T014 touches `B/models.py`, `B/waste_matrix.py` and `B/experiments.py`; it is parallel to T006 to T010 (different files) but not to T004 (`B/models.py`) or T012 (`B/experiments.py`). Run it before T004 or between T010 and T011.
- With one executor, the order is the numeric order with T014 placed after T010.

## Parallel opportunities

One executor seat implements, so parallelism is the orchestrator's choice, not a default. Where two executors exist: T006, T007+T008, T009 and T010 touch disjoint files after T003 (the Stored test is the one shared file: each task appends its own test function). T014 is marked [P] for the same reason.

## Implementation strategy

- **MVP**: phases 1 and 2. After T003 the exit criterion's numbers are computed and pinned on the stored records.
- **First visible increment**: add T004 to T006 and T011: `report.md` opens with the run grid and the corrected stage table.
- **Then**: heatmap (T007, T008), gate view (T009), success criteria (T010), the shared writer (T012), the script (T013).
- **Independent tail**: T014 and T015. The round can close with T015 open and FR-041 reported open.

## Requirement coverage

| Task | Requirements |
|---|---|
| T002 | FR-002 (one rule) |
| T003 | FR-001 to FR-006, FR-022, FR-024, FR-025, FR-028; SC-001 to SC-005 (figures) |
| T004 | FR-023, FR-025 to FR-028 |
| T005 | FR-034, FR-035 |
| T006 | FR-007 to FR-011 |
| T007 | FR-012 to FR-017, FR-021 |
| T008 | FR-018 to FR-020; SC-007 |
| T009 | FR-029 to FR-033; SC-009 |
| T010 | FR-037 to FR-039; SC-008 |
| T011 | FR-007 (first section), FR-023, FR-027, FR-034 |
| T012 | FR-036, FR-044, FR-045, FR-046; SC-006 |
| T013 | FR-047 |
| T014 | FR-040, FR-042 |
| T015 | FR-041, FR-042; SC-011 |
| T016 | FR-049 |
| T017 | FR-043, FR-048; SC-001 to SC-012 on the stored records |
