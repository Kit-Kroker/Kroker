# Implementation Plan: Benchmark Scoring Output Rework (round 013, Phase 2)

**Branch**: orchestrator's call (spec dir `013-benchmark-scoring-output`) | **Date**: 2026-10-09 | **Spec**: [spec.md](spec.md) | **Base**: main `35d1b056`

**Input**: [spec.md](spec.md), GATE 1 cleared 2026-10-09 with rulings R1 (2.8 stays, 2.9 is its own round), R2 (fixed colour scales as written), R3 (attrition over runs that reached the stage), R4 (round 012 rule applied to pre-012 runs), R5 (gate agreement at run level). Scope: user stories 1 to 9; FR-001 to FR-049; SC-001 to SC-012. Source of the findings: `docs/reports/2026-10-06-benchmark-improvement-plan.md` §1 and §4 Phase 2 (read-only; never edited, staged or committed).

**Consults**: advisor `.workspace/tmp/013-advisor-a1.md`, skeptic `.workspace/tmp/013-skeptic-a1.md`. Folded into [research.md](research.md) (consult log at its end). The skeptic broke five statements of the approved spec; the spec carries them as amendments A1 to A5 and they are items for GATE 2.

**Review**: reviewer `.workspace/tmp/reviewer-013-plan-1.md` — VERDICT: approve, five non-blocking findings, all folded in: the trailing column for a stage outside the pipeline order has a contract clause (§2.6, §3.1); `CANONICAL_STAGES` has four test importers, not five; the group key in research R-4 carries the harness, as the contract does; the documentation script matches the stage table by exact header cells and the grid's markdown header is pinned so it cannot match; `test_benchmark_models.py` is in the changed-on-purpose table. The reviewer recounted every row of contract §12 on the stored records. Tasks review `.workspace/tmp/reviewer-013-tasks-1.md` — VERDICT: fixes-needed, 1 blocking, 4 non-blocking; all folded in: the summary-row task names the four existing tests its re-keying breaks and how each changes (blocking 1); `render_markdown` emits every report section itself and one test pins the order of the file the score command writes; the reviewer-versus-adversary title assertion is added, not changed; the unedited list says what `test_benchmark_workflow.py` pins; two more test edits and the name-check fallback are named. Re-review `.workspace/tmp/reviewer-013-tasks-2.md` — VERDICT: approve; all five resolved; one stale clause in this plan's unedited list aligned with tasks.md.

`B/` = `src/sdlc/benchmarks/`. `H/` = `src/sdlc/harness/`.

## Summary

The records are trustworthy since round 012; the output that reads them is not. This round rebuilds the reading side around one object, the run.

- **Runs**: records are grouped into runs once. A run has one arm, one status (graded, lost, grading failed, no oracle), a last stage, an oracle result and task outcomes. A pre-012 run gets its status by the same function round 012 uses when writing.
- **Grid**: the first section of every score is one row per run, grouped by arm and commit, with mean and spread on each group.
- **Heatmap**: four layers on the same stage columns (attrition, first-attempt failure, wasted tokens, oracle per run), fixed colour steps, denominators printed, grey under five observations.
- **Scores**: partial credit beside the all-pass rate; first-attempt and after-repair scores per task; a pass/fail verdict is never shown as quality.
- **Gates**: each gate against the oracle: agreement, escape rate, false-reject rate.
- **Composite**: gone until a case has two arms with graded runs; then normalised across arms.
- **Success criteria**: computed from the scored runs' own summaries, found by run id.
- **Waste**: stored opencode counters read as not measured; the opencode parser is fixed against a real captured stream; new captures carry a mark.
- **Stored records**: read-only. No benchmark run.

Decisions R-1 to R-15 are in [research.md](research.md). Every name is in [data-model.md](data-model.md). Behaviour, the expected figures on the stored records and the requirement-to-proof table are in [contracts/scoring-output.md](contracts/scoring-output.md). Validation is in [quickstart.md](quickstart.md).

## The four rules every task is checked against

1. **Stored records are read-only.** Nothing under `runs/` is modified, moved, deleted or added. `runs/` is git-ignored, so the check is the records fingerprint taken at the baseline and compared before every commit; `git ls-files runs/` stays empty. Scores made during the round are written with `--out` to a directory outside `runs/`.
2. **The run is the unit.** A view reads `Run` objects from `B/runs.py`. A view that groups raw records by its own key is a defect, with two named exceptions that stay record-based: the task and error matrices (oracle-task records per bench run) and the reviewer-versus-adversary matrix.
3. **No reader guesses.** Absent reads as "not recorded" or "not measured", never as zero, pass or fail. A figure is printed with its denominator. Under five observations it is grey or `n/a`.
4. **Names come from data-model.md.** Its §8 check is in the first task. A name not in it stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2, argparse; Temporal Python SDK only at the one activity).

**Primary Dependencies**: existing only. No change to `pyproject.toml` or `uv.lock`.

**Storage**: JSON-lines record files under `runs/benchmarks/<bench_run_id>/`, read only. Run summaries under `runs/pipeline/<run_id>/summary.json`, read only. One additive optional field on two models that are written by future runs (`SessionDigest.capture_rev`, `WasteBag.capture_rev`).

**Testing**: in the `kroker-dev` container: `uv run pytest` (fast tier), named files per task; `-m temporal tests/replay` and `-m temporal tests/test_benchmark_workflow_sequence.py` at baseline and at the end. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`. Host: `python scripts/check_file_size.py`, `python scripts/check_clauses.py` (always exits 0; read it). One test file reads the stored records in place and asserts contract §12.

**Target Platform**: CLI on the developer host through the container; the same writer runs inside the worker's `finalize_benchmark_report` activity.

**Project Type**: single Python project; the benchmark package, three lines of the harness package, one script.

**Performance Goals**: scoring one case on the stored records completes in under a minute (SC-012). The records are read once per score and runs are built once.

**Constraints**: stored records read-only; no benchmark run; `sdlc benchmark score` needs no worker, server or network, so `B/runs.py`, `B/grid.py`, `B/gate_oracle.py`, `B/heatmap.py`, `B/heatmap_render.py` import no `temporalio`; `B/heatmap.py` stays importable with `B/models.py` and pydantic only (the worker and the dashboard import `CANONICAL_STAGES` from it); `CANONICAL_STAGES` is not edited; the activity `finalize_benchmark_report` keeps its name, argument and return; `report.md` stays ASCII; 1000-line ceiling; cross-stage call ban; producer owns its artifacts; behaviour and its clauses change in the same diff; no file under `tests/replay/` is edited.

**Scale/Scope**: 4 new source modules, about 14 modified source files and one script, 4 new test files and one fixture, about 16 modified test files (three heatmap test files are rewritten or removed), 4 documents, 2 files written into the spec directory during execution. No new file is expected to pass 450 lines.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md`. Neither `B/` nor `H/` has an `AGENTS.md` of its own. Checked after design:

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. No stage is edited. `B/` and `H/` are horizontal packages. |
| Producer owns its artifacts | Holds. Run, grid, layer and gate models live in the benchmark package that produces them. `SessionDigest` gains its field in `H/models.py`, which owns it; `WasteBag` in `B/models.py`. `core/` is not touched. |
| Whoever changes behaviour updates its clauses in the same diff | Planned per task: `BENCHMARK.md` §4.1, §4.3, §4.4; `README.md`; `ARCHITECTURE.md`; `ROADMAP.md` (document table below). No stage contract (`<stage>.md`) changes. |
| 1000-line ceiling | Holds. Largest files after: `B/models.py` 379 + about 70; `B/runs.py` about 400; `B/heatmap.py` about 350; `B/grid.py` about 350; `B/report.py` 234 + about 60; `scripts/aggregate_benchmarks.py` 657 + about 10. Stop-guard SG-3 at 800 for any of them. |
| Workflow determinism | No workflow code is edited. `B/report.py` is imported at worker boot through `imports_passed_through`; the new modules are imported lazily inside `finalize_benchmark_report` and `write_score`, as `calibration` already is. |
| Replay safety | No command sequence changes. The activity's result is still a path string. `SessionDigest` gains an optional field with a default, carried inside an activity result; a stored history without it still validates. The replay suite is run at baseline and at the end. |
| `AGENTS.md` files | Not edited. |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/013-benchmark-scoring-output/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   scoring-output.md
├── checklists/  requirements.md (+ plan.md, tasks.md from the reviewer)
├── tasks.md     (/speckit-tasks)
└── written during execution:
    baseline.md, verification.md
```

### Source Code (after the feature)

```text
src/sdlc/
├── benchmarks/
│   ├── runs.py                 N  Run, TaskOutcome, Group, Totals, build_runs, group_runs, gate_passed, composite_shown
│   ├── grid.py                 N  run-by-run grid: build, markdown, html, json
│   ├── gate_oracle.py          N  gate versus oracle: build, markdown, html, json
│   ├── heatmap_render.py       N  SCALES, step_for, html
│   ├── heatmap.py              M  CANONICAL_STAGES kept; layered model and build_layers replace the summed heatmap
│   ├── models.py               M  cell_progress, grading_from_score, TASK_LOOP_STAGES, RUBRIC_JUDGES, WasteBag.capture_rev, waste_measured, summary fields
│   ├── cell.py                 M  summarize_cell and grading_status call the moved bodies
│   ├── scoring.py              M  rows from runs; pass rate, first attempt, after repair, all-pass; composite across arms
│   ├── report.py               M  render_markdown sections; finalize calls the shared writer; write_heatmap takes runs
│   ├── score.py                M  write_score writes grid and gate-oracle; weights note
│   ├── evidence.py             M  summaries by run id; counts
│   ├── sc_rollup.py            M  "N of M runs left a summary"; shared threshold and sort key
│   ├── waste_matrix.py         M  unmeasured left out and counted; runs by run_id
│   ├── experiments.py          M  unmeasured left out; composite column behind the decision
│   ├── agreement_matrix.py     M  title and heading only
│   └── cli.py                  M  only if the weights note needs the dispatch to pass a flag through
├── harness/
│   ├── models.py               M  SessionDigest.capture_rev
│   ├── session.py              M  CAPTURE_REV; digest_of writes it
│   └── opencode.py             M  normalise_session tool events, failed commands, de-duplication
└── eval/verdict.py             M  one stale comment

scripts/aggregate_benchmarks.py M  parse_report picks the stage table

tests/
├── test_benchmark_runs.py             N
├── test_benchmark_grid.py             N
├── test_benchmark_gate_oracle.py      N
├── test_benchmark_stored_scores.py    N  contract §12 on the stored records, in place, read-only
├── fixtures/opencode/session_tools.jsonl   N  a real captured stream
├── test_benchmark_heatmap.py, test_benchmark_heatmap_render.py      rewritten
├── test_benchmark_heatmap_fix_inflation.py                          removed (its rule is superseded, research R-6)
├── test_benchmark_scoring.py, test_benchmark_report.py, test_benchmark_score.py,
│   test_benchmark_evidence.py, test_benchmark_sc_rollup.py, test_benchmark_models.py,
│   test_benchmark_cell.py, test_benchmark_waste_bag.py, test_benchmark_waste_matrix.py,
│   test_benchmark_agreement_matrix.py, test_benchmark_experiments.py, test_benchmark_cli.py,
│   test_aggregate_benchmarks.py, test_opencode_normalise.py, test_session_capture.py,
│   test_session_models.py                                           M
└── test_e36_imports.py                                              M  only if it names a removed heatmap symbol

BENCHMARK.md, README.md, ARCHITECTURE.md, ROADMAP.md   M
```

**Not touched**: anything under `runs/`; `docs/reports/`; `tests/replay/`; every stage slice under `src/sdlc/stages/`; `src/sdlc/workflows/`; `B/workflow.py`, `B/oracle.py`, `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/drift.py`, `B/task_matrix.py`, `B/error_matrix.py`, `B/calibration.py`; `H/claude_code.py`, `H/cursor.py`, `H/base.py`; `src/sdlc/graph/`, `src/sdlc/dashboard/`; `agents/`; `interfaces/`; every `AGENTS.md`; `pyproject.toml`, `uv.lock`; earlier `.specify/specs/*` and `.specify/bugs/*`; every script except `scripts/aggregate_benchmarks.py`.

## Design in brief

1. **Status functions move** (R-2). Two pure functions into `B/models.py`; `B/cell.py` delegates. Existing cell tests pass unedited: that is the proof nothing changed for the writer.
2. **Run model** (R-1, R-3, R-4, R-5; contract §1). Everything else reads it.
3. **Summary rows** (R-10, R-11; contract §5, §7). Keyed by run arm; pass rate, two code scores, all-pass; composite decided per case.
4. **Grid** (contract §2).
5. **Heatmap layers and scales** (R-6, R-7, R-8; contract §3, §4).
6. **Gate versus oracle** (R-9; contract §6).
7. **Success criteria by run id** (R-12; contract §9).
8. **One writer, report order, the script** (R-13, R-14; contract §8, §11).
9. **Waste mark, not-measured rule, opencode parser** (R-15; contract §10).
10. **Documents**, then the stored-record validation.

## Work order

Tasks come from `/speckit-tasks`; this is the order and why. Each test lands with the code that satisfies it, test written first, no red commits. Each step ends with its named checks green.

| Step | What | Why here |
|---|---|---|
| 0 | Baseline in the container (fast tier counts, `-m temporal tests/replay`, the workflow sequence test, ruff, mypy count) and on the host (file size, clauses, the documentation script's output, the records fingerprint). Container binding check, and that `runs/benchmarks` is visible inside it. Data-model §8 name check. Research "Verify" items: R-2 (derived status equals recorded on the three 012 runs), R-3 (every stored `run_id` has the expected shape), R-15 (the harness kind a crew arm's session is captured under; `SessionDigest` field and replay). A grep for any reader of the heatmap model or of `heatmap.json` content, `agreement-matrix`, `sc-rollup` outside `B/` and tests. Record all of it in `baseline.md`. | A known start; every assumption the design rests on is checked before code depends on it. |
| 1 | `cell_progress`, `grading_from_score`, `TASK_LOOP_STAGES`, `RUBRIC_JUDGES` in `B/models.py`; `B/cell.py` delegates. | Smallest change; the 012 tests pin it. |
| 2 | `B/runs.py` + `test_benchmark_runs.py`; `test_benchmark_stored_scores.py` with the run-level rows of contract §12 (totals, groups, credit, task scores). | US1. The exit criterion's numbers are true from here on. |
| 3 | `B/scoring.py` and the `BenchmarkSummary` fields; composite decision and arm normalisation; tests. | US4, US5, US7 in the summary rows. Needs runs. |
| 4 | `B/grid.py` + tests. | US2. |
| 5 | `B/heatmap.py` layers, `B/heatmap_render.py`; the three heatmap test files; `eval/verdict.py` comment. Stored test gains the attrition rows. | US3. Largest single piece; isolated. |
| 6 | `B/gate_oracle.py` + tests; `agreement_matrix.py` title. Stored test gains the gate rows. | US6. |
| 7 | `B/evidence.py`, `B/sc_rollup.py` + tests. Stored test gains the summary count. | US8. |
| 8 | `B/report.py` section order and the shared writer; `B/score.py`; `B/experiments.py` composite column; `scripts/aggregate_benchmarks.py`; tests, including finalize against score on one record set. | Assembles steps 2 to 7 into the output; FR-044, FR-045, FR-047. |
| 9a | `capture_rev` on `SessionDigest` and `WasteBag`, `waste_measured`, waste matrix and experiments; tests. | US9, reader half. No dependency on the captured stream. |
| 9b | The captured stream fixture: **report to the orchestrator and wait** (who captures it, or whether the user supplies it). Then `H/opencode.py` + `test_opencode_normalise.py`. | US9, parser half. The fixture decides the field names; the wait is the one live call of the round. |
| 10 | Documents (table below). | Describe what is on the branch. |
| 11 | Full gates (quickstart §1) and the stored-record validation (§2); `verification.md`. | The exit criterion. |

US1 is deliverable after step 2. Steps 3 to 7 each depend only on step 2 and may be reordered. Step 9a and 9b depend on nothing but step 0 and may run at any point; 9b can be last if the stream arrives late.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `tests/test_benchmark_heatmap.py`, `test_benchmark_heatmap_render.py` | rewritten against the layered model | R-6 |
| `tests/test_benchmark_heatmap_fix_inflation.py` | removed | the rule it pins (per-task maximum of `fix_attempts`, `fail_reentry` count) has no input in the layered model; R-6 |
| `tests/test_benchmark_scoring.py` | row keys carry the arm and generation; composite tests assert `None` for one arm and the arm normalisation for two; code row has no quality | R-10, R-11 |
| `tests/test_benchmark_report.py` | section order; `## Cells` replaced by the totals line; composite column assertions; the stage table's `cell` header becomes `arm`; two `aggregate` tests whose records share one `run_id` get distinct runs; the `write_heatmap` test passes runs | contract §8, R-11, R-6 |
| `tests/test_benchmark_experiments.py` (quality fixtures) | the fixture's judge becomes `llm_judge`: a `contract` verdict is no longer a quality score | R-11 |
| `tests/test_benchmark_score.py`, `test_benchmark_cli.py` | file list gains `grid.*` and `gate-oracle.*` | contract §11.1 |
| `tests/test_benchmark_evidence.py` | summaries are found by run id; a summary outside the selection is not loaded | R-12 |
| `tests/test_benchmark_sc_rollup.py` | gains the count line; scoping cases | contract §9 |
| `tests/test_benchmark_waste_matrix.py`, `test_benchmark_experiments.py` | fixtures that used all-zero opencode bags as "clean" set `capture_rev=1` or expect not measured | R-15 |
| `tests/test_benchmark_agreement_matrix.py` | the title assertion | FR-033 |
| `tests/test_benchmark_models.py` | gains cases for the new `BenchmarkSummary` fields and the moved status functions; its `composite` constructions keep working (`float \| None`, still required) | R-2, R-11 |
| `tests/test_e36_imports.py` | only if it imports a removed heatmap name | R-6 |

Tests that must pass **unedited**: the assertions on `summarize_cell` and `grading_status` in `test_benchmark_cell.py`; all of `test_benchmark_workflow.py` (the workflow's config and record builders are not touched); `test_benchmark_legacy_records.py`; `tests/graph/test_graph_node_types.py`, `test_dashboard_graph_wire.py`, `test_run_state_query.py`, `test_calibration_render.py`; `test_claude_stream_normalise.py` and the cursor normaliser's tests; the existing hand-written case in `test_opencode_normalise.py`; everything under `tests/replay/`. A needed edit to one of these is a stop-guard (SG-1), not a fix.

## Document changes

| File | Now | Change to |
|---|---|---|
| `BENCHMARK.md` §4.1 | code-stage quality is the share of attempts that passed (round 012 sentence) | first-attempt and after-repair scores per task; partial credit beside the all-pass rate; a verdict is a pass rate, not a quality score; the composite needs two arms |
| `BENCHMARK.md` §4.3 | waste counters landed | stored opencode counters are not measured; the capture mark; tool events are parsed from here on |
| `BENCHMARK.md` §4.4 | one case by stage grid of rework density; "five grids" status line | four layers, their units and denominators, the fixed scales, grey under five; the run grid as the main view; gate versus oracle; the list of files a score writes; the `fail_reentry` and per-task-maximum rules are superseded |
| `BENCHMARK.md` success-criteria passage (find by "SC-1") | cross-run rates | computed from the scored runs' own summaries |
| `README.md` lines near 64 to 77 and 312 to 314 | how to score; list of outputs | the grid and gate-oracle files; the reviewer-versus-adversary name; weights are unused without two arms |
| `ARCHITECTURE.md` near 473 and 830 | package listing | `runs`, `grid`, `gate_oracle`, `heatmap_render` |
| `ROADMAP.md` | Phase 1 landed, Phases 2 to 4 open | Phase 2 landed except 2.9; "Last verified" line |

Find each passage by its text; line numbers are from the base. Documents describe main, so these ride the branch.

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: a test listed as "must pass unedited" needs an edit, any test under `tests/replay/` changes result against the baseline, or an edit to a "not touched" path appears necessary. Stop, diagnose, report.
- **SG-2**: a step-0 "Verify" item fails; step 0's grep finds a reader of a changed output this plan does not name; or the implementation does not reproduce a figure of contract §12. Stop and report. A §12 figure is never edited to match the code.
- **SG-3**: any file would pass 800 lines.
- **SG-4**: step 9b. No parser code before the orchestrator has answered on the captured stream. If the stream contradicts research R-15's field names, the fix follows the stream and the difference is reported. If no stream can be had, step 9b is not done and FR-041 is reported open; a hand-written fixture does not close it.
- **SG-5**: the records fingerprint changes, `git ls-files runs/` prints anything, or a score is written under `runs/` during the round.
- **SG-6**: a `temporal` test named in a gate reports "deselected", or `test_benchmark_stored_scores.py` reports "skipped" in the final gates. Neither is a pass.
- **SG-7**: a task needs a module in the list of `temporalio`-free modules to import `temporalio`, `B/report.py`, `B/cell.py` or `B/recorder.py`.

## Risks

| Risk | Mitigation |
|---|---|
| A stored run does not fit the run model (odd `run_id`, records of two generations, lines that fail validation) | Step-0 verify on the whole corpus; `build_runs` notes and never raises; 51 herdr-probe lines already fail validation at base and stay skipped. |
| Changing summary row keys breaks a consumer | Step-0 grep; the documentation script reads `report.md` by header name and is covered by its own test. |
| The opencode stream differs from the advisor's memory | The fixture decides; SG-4. |
| No captured stream by the end of the round | Step 9a still lands and is honest on its own; FR-041 is reported open. |
| The bench directory gains files at the end of a run (shared writer) | Stated at GATE 2; the documentation script ignores unknown files. |
| A hidden dependency on `## Cells` in `report.md` | Step-0 grep for the heading in `src`, `scripts`, `tests`, `interfaces`. |
| The layered heatmap HTML grows hard to read | One row per arm and generation; layers stacked under one column header; reviewed on the cat-cafe output in step 11. |

## Follow-ups to file (`.workspace/tasks/`)

- Round for report 2.9, erosion and verbosity (spec Follow-ups).
- A stage that dies before it writes a record is invisible to attrition; a "stage started" record would place the eight lost runs exactly. Size S to M.
- Three vocabularies for one stage (`CANONICAL_STAGES`, `CELL_STAGE_ORDER`, rubric keys); carried over from 012. Size M.
- The export of a crew cell's run summary uses an unsanitised id with `:` in the path. Size S.
- `B/task_matrix.py` and `B/error_matrix.py` still key by `cell_key`, so a pre-012 cell is several columns there. Size S; out of this round because they read oracle-task records per bench run and no requirement names them.
- Live confirmation of the opencode parser on the next benchmark run.

## Items for GATE 2

1. **Five spec amendments after GATE 1** (A1 to A5 in the spec). The one that changes an approved number: merge "revise" is a pass with waived checks, so cat-cafe merge is 7 rejected and 3 passed, not 10 rejected (SC-009).
2. **Two heatmap rules are superseded**: the E-77 `fail_reentry` axis and the per-task maximum of `fix_attempts`. One test file is removed with them.
3. **The `heatmap.json` schema changes**; the file name stays. `report.md` loses `## Cells` and the `composite` column, and gains `## Runs` first.
4. **A bench directory gains files** at the end of a run: the end-of-run report now writes everything the score command writes.
5. **One additive field written by future runs**: `capture_rev` on the session digest and the waste counters.
6. **One live opencode call** for the stream fixture, or a stream from the user (step 9b, SG-4).
7. **Task and error matrices are not moved onto the run model** (follow-up).
8. **Summary rows change key**: one row per stage for a pre-012 cell, where there were two to four.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind (no `Co-Authored-By:`, no `Claude-Session:`), even where a template prints one.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only. Git on a worktree runs on the host.
- Never chain two test runs in one shell call. `addopts` already carries `-q`.
- The reviewer gate is per task and blocking.
- The benchmark improvement plan under `docs/reports/` and the other untracked or modified files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
