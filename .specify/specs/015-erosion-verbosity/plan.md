# Implementation Plan: Erosion and Verbosity as a Second Quality Axis (round 015)

**Branch**: orchestrator's call (spec dir `015-erosion-verbosity`) | **Date**: 2026-10-11 | **Spec**: [spec.md](spec.md) | **Base**: main `c3f6319c`

**Input**: [spec.md](spec.md), GATE 1 cleared 2026-10-11 with rulings R1 (own rule set, cloned lines out of v1), R2 (both tools added, one todo-api smoke run included), R3 (Python-only v1). Scope: user stories 1 to 4; FR-001 to FR-017; SC-001 to SC-006. Source of the item: `docs/reports/2026-10-06-benchmark-improvement-plan.md` §2.6 and §4 task 2.9 (read-only; never edited, staged or committed).

**Review**: this plan's reviewer gate is per task and blocking, as at base. No advisor or skeptic seats were run (solo session; the consult log and the GATE 2 disclosures that replace them are in [research.md](research.md)). Decisions R-1 to R-10 are in [research.md](research.md); every name is in [data-model.md](data-model.md); behaviour and the clause-to-proof table are in [contracts/axis.md](contracts/axis.md); validation is in [quickstart.md](quickstart.md).

`B/` = `src/sdlc/benchmarks/`.

## Summary

The oracle says whether the code works; nothing says what the run did to the code. This round adds the second objective axis: erosion (complexity mass above CC 10) and verbosity (rule-flagged lines), measured once at run end on the produced diff at the integration head, stored as one record per run, read like any other record.

- **Measure**: a fail-safe activity, its own detached worktree (the oracle's pattern), radon for mass, ast-grep-py over a pinned six-rule set authored here, versioned `"1"`.
- **Store**: one `scope=AXIS` record per started cell, figures in an `AxisBag` payload — never in `quality` — through the existing recorder. No new file or directory in the bench dir.
- **Read**: two grid columns, group means per rule-set version, one totals clause. Absence reads `n/m(<reason>)`, never zero. The heatmap, the composite, the gate view and every quality figure are untouched.
- **Prove**: fixture trees with hand-computed figures and a determinism pair; the stored corpus as the negative proof (every run `no axis record`, all 013 figures unchanged); one todo-api smoke run as the live proof, which also closes 013's opencode-parser follow-up.
- **Deps**: `radon==6.0.1`, `ast-grep-py==0.50.0` — both MIT — the first `pyproject.toml`/`uv.lock` change since round 013 froze them (GATE 2).

## The four rules every task is checked against

1. **The stored corpus is read-only.** Nothing under an existing `runs/benchmarks/<id>/` is modified, moved, deleted or added; the fingerprint taken at baseline is compared before every commit; `git ls-files runs/` stays empty. The smoke run writes only its own new bench directory. Scores made during the round are written with `--out` outside `runs/`.
2. **The run is the unit.** The axis rides `Run` objects from `B/runs.py`; no view groups axis records by its own key.
3. **No reader guesses.** Absence reads `n/m(<reason>)`, never zero; a figure prints with its count; under five observations is grey; a mean never crosses a rule-set version.
4. **Names come from data-model.md.** Its §8 check is in the first task. A name not in it stops the task.

## Technical Context

**Language/Version**: Python 3.13 (Pydantic v2; Temporal Python SDK at the one new activity).

**Primary Dependencies**: NEW — `radon==6.0.1`, `ast-grep-py==0.50.0` (both MIT, verified 2026-10-11; wheels cp310–cp314 Windows/Linux for the binding, pure Python for radon). Existing otherwise.

**Storage**: JSON-lines record files under `runs/benchmarks/<bench_run_id>/` — the axis record lands in the cell's existing `records.jsonl`; no layout change.

**Testing**: in the `kroker-dev` container: `uv run pytest` (fast tier), named files per task; `-m temporal tests/test_benchmark_workflow_sequence.py` at baseline and end; `-m temporal tests/replay` at baseline and end. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`. Host: `python scripts/check_file_size.py`, `python scripts/check_clauses.py` (always exits 0; read it).

**Target Platform**: the worker's run end (measurement activity) and the CLI score command (reader, no worker).

**Project Type**: single Python project; the benchmark package, one workflow file, the worker registration list, two dependencies.

**Performance Goals**: measuring a case-sized tree completes in under 30 s (SC-005); scoring stays under the one-minute bar (013 SC-012).

**Constraints**: the workflow edit is confined to a `workflow.patched("015-quality-axis")` branch (in-flight runs replay the old path); the activity never raises; `B/runs.py` and `B/grid.py` stay free of `temporalio`, radon and ast-grep-py; `CANONICAL_STAGES`, `CELL_STAGE_ORDER` and every other pinned vocabulary are not edited; the recorder's file layout is not changed; behaviour and its clauses change in the same diff; no file under `tests/replay/` is edited; `pyproject.toml`/`uv.lock` change exactly once (first source task) and never after; report text stays ASCII; 1000-line ceiling; cross-stage call ban (the measurement lives in `B/`, a horizontal package that owns its records).

**Scale/Scope**: 1 new source module, 1 new rules directory (6 YAML files), about 8 modified source files, 1 new test file, 2 new fixture trees, about 9 modified test files, 4 documents, and the 2 files written into the spec directory during execution (baseline.md, verification.md). No new file is expected to pass 300 lines.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so no constitution gate applies. The binding rules are the repository's: root `AGENTS.md`. Neither `B/` nor `H/` has an `AGENTS.md` of its own. Checked after design:

| Rule | Status |
|---|---|
| Cross-stage calls banned | Holds. No stage is edited. `B/` is a horizontal package; the workflow already imports from it. |
| Producer owns its artifacts | Holds. The bag, the rules and the activity live in the benchmark package that owns the records. `core/` is not touched. |
| Behaviour and clauses in the same diff | Planned per task: `contracts/axis.md` clauses land with the behaviour they describe; `BENCHMARK.md` and the other living docs in the documents task. |
| 1000-line ceiling | Largest files after: `B/models.py` 463 + about 35 (AxisBag); `B/runs.py` 496 + about 30; `B/grid.py` 400 + about 40; `B/workflow.py` 459 + about 25; `B/axis.py` new, about 220. Stop-guard SG-3 at 800 for any of them. |
| Workflow determinism | Holds. The new activity call sits inside `workflow.patched("015-quality-axis")`; no filesystem access in workflow code; the builder is pure. |
| Replay safety | No BenchmarkWorkflow history exists in the replay suite (verified); in-flight benchmark runs replay the unpatched branch. The replay suite is run at baseline and at the end regardless. |
| `AGENTS.md` files | Not edited. |

No violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/015-erosion-verbosity/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/   axis.md
├── checklists/  requirements.md
├── tasks.md     (/speckit-tasks)
└── written during execution:
    baseline.md, verification.md
```

### Source Code (after the feature)

```text
src/sdlc/benchmarks/
├── axis.py                    N  AxisInput, AXIS_EROSION_THRESHOLD, RULESET_VERSION,
│                                 measure_files, measure_code_axis (activity), axis_record
├── rules/verbosity/           N  except-pass.yml, bare-except.yml, print-call.yml,
│                                 debugger-call.yml, nested-ternary.yml, if-deep-4.yml
├── models.py                  M  BenchmarkScope.AXIS, JudgeKind "axis", AxisBag, BenchmarkRecord.axis
├── workflow.py                M  the patched 015-quality-axis block: measure, record
├── runs.py                    M  Run.axis; Group mean_erosion/mean_verbosity/axis_n/axis_versions; Totals.axis_*
├── grid.py                    M  two row columns; header figures; grid.json/grid.html fields
├── report.py                  M  _totals_line gains the axis clause
├── score.py                   M  only if the grid plumbing needs a flag passed through
└── worker.py (src/sdlc/)      M  import + register measure_code_axis

pyproject.toml, uv.lock       M  radon==6.0.1, ast-grep-py==0.50.0 (once, first source task)

tests/
├── test_benchmark_axis.py            N  fixtures' figures, determinism, reasons, activity paths
├── fixtures/axis/                    N  mass-split tree, slop tree (hand-computed expectations)
├── test_benchmark_workflow_sequence.py  M  axis stub; lost run, non-python, absent branch, record order
├── test_benchmark_runs.py            M  Run.axis, version mixing, absence
├── test_benchmark_grid.py            M  row columns, header means, grey rule
├── test_benchmark_report.py          M  totals clause; no axis in other sections
├── test_benchmark_score.py           M  grid.json carries the axis; no other output mentions it
├── test_benchmark_models.py          M  AxisBag validation (the XOR invariant), scope, judge literal
├── test_benchmark_stored_scores.py   M  the §4 rows: not measured everywhere, figures unchanged
└── test_judge_literal.py             M  "axis" added to the emitted set

BENCHMARK.md, README.md, ARCHITECTURE.md, ROADMAP.md   M
```

**Not touched**: anything under `runs/` (the smoke run's own new dir aside); `docs/reports/`; `tests/replay/`; every stage slice; `src/sdlc/workflows/`; `B/report.py` beyond the totals line; `B/oracle.py`, `B/judge.py`, `B/recorder.py`, `B/record_builder.py`, `B/provenance.py`, `B/paths.py`, `B/drift.py`, `B/task_matrix.py`, `B/error_matrix.py`, `B/calibration.py`, `B/heatmap.py`, `B/heatmap_render.py`, `B/gate_oracle.py`, `B/evidence.py`, `B/sc_rollup.py`, `B/waste_matrix.py`, `B/experiments.py`, `B/agreement_matrix.py`, `B/cell.py`, `B/cli.py`; `src/sdlc/harness/`; `src/sdlc/graph/`, `src/sdlc/dashboard/`; `agents/`; `interfaces/`; every `AGENTS.md`; earlier `.specify/specs/*` and `.specify/bugs/*`; every script.

## Design in brief

1. **Dependencies first** (R-8): pin, lock, sync, import-check on 3.13.
2. **The bag and the record shape** (R-5): model + scope + judge literal; old records still validate.
3. **The measurement core** (R-3, R-4, R-7): pure `measure_files` on fixture trees; the six rules; determinism.
4. **The activity and the wiring** (R-1): fail-safe `measure_code_axis`, the pure `axis_record`, the patched workflow block, worker registration, sequence tests.
5. **The reader** (R-6): `Run.axis`, group means per version, totals clause, grid columns and JSON.
6. **The stored corpus** (R-10): the negative rows in the stored-scores test.
7. **Documents**, then full gates and `verification.md`.
8. **The smoke run** (R-9): live proof under SG-4, addendum in `verification.md`.

## Work order

Tasks come from `/speckit-tasks`; this is the order and why. Each test lands with the code that satisfies it, test written first, no red commits. Each step ends with its named checks green.

| Step | What | Why here |
|---|---|---|
| 0 | Baseline in the container (fast tier counts, `-m temporal tests/replay`, the workflow sequence test, ruff, mypy count) and on the host (file size, clauses, the records fingerprint of the stored corpus). `uv run python -c "import radon, ast_grep_py"` after a first sync on the branch. Data-model §8 name check. A grep for readers of `grid.json` and of the totals line outside `B/` and tests. Record all of it in `baseline.md`. | A known start; the two new tools proven on the container's 3.13 before code depends on them. |
| 1 | `radon==6.0.1`, `ast-grep-py==0.50.0` in `pyproject.toml`, `uv lock`, container sync (the round's only lockfile touch); `AxisBag`, `BenchmarkScope.AXIS`, the `"axis"` judge literal, `BenchmarkRecord.axis`; tests in `test_benchmark_models.py` and `test_judge_literal.py`. | The record shape everything else writes and reads; the lockfile changes once, up front. |
| 2 | `B/axis.py`: `measure_files` + `AXIS_EROSION_THRESHOLD`; the two fixture trees; `test_benchmark_axis.py` on hand-computed figures and the determinism pair. | The metric core, pure and provable before any workflow wiring. |
| 3 | The six rules under `rules/verbosity/` + `RULESET_VERSION`; the loader; rule failures fail the measurement; slop-fixture verbosity. | The rule set is data; it lands after the engine that applies it. |
| 4 | `measure_code_axis` (fail-safe paths), `axis_record`, the `015-quality-axis` workflow block, worker registration; `test_benchmark_workflow_sequence.py` cases. | The writer, proven on the sequence test with stubs. |
| 5 | Reader: `Run.axis`, `Group`/`Totals` fields, `_totals_line`, grid row/header/JSON; tests in runs/grid/report/score files. Stored test gains the §4 rows. | Everything the score shows; the stored corpus is the negative proof from here on. |
| 6 | Documents (table below). | Describe what is on the branch. |
| 7 | Full gates (quickstart §1-§3) and the stored-corpus validation (§2); `verification.md`. | The exit criterion minus the live proof. |
| 8 | The smoke run (quickstart §4) under SG-4: orchestrator's go, runbook constraints, acceptance checks, the opencode-parser confirmation, the addendum. | SC-006; also closes 013's live-parser follow-up. |

US1/US4 are deliverable after step 4; US2 after step 5; US3 is proven at step 5 (checked by absence). Step 8 can run after step 7 or, if the machine is busy, later — the round's code is complete without it and SC-006 is the only clause that waits.

## Existing tests changed on purpose

| File | Change | Why |
|---|---|---|
| `tests/test_judge_literal.py` | `"axis"` added to `EMITTED_JUDGES` | R-5 |
| `tests/test_benchmark_models.py` | AxisBag construction/validation cases; scope member; `BenchmarkRecord.axis` default None | R-5 |
| `tests/test_benchmark_workflow_sequence.py` | an axis stub registration; four new cases (measured, lost run, non-python, absent branch); record-order assertion (axis after the cell record) | contract §2 |
| `tests/test_benchmark_runs.py` | `Run.axis` from the last AXIS record; version mixing withholds means; `no axis record` reason | R-6 |
| `tests/test_benchmark_grid.py` | two columns; header means with counts; grey under five; absence rendering | R-6 |
| `tests/test_benchmark_report.py` | the totals clause; no axis text in Stages/heatmap/gate sections | contract §3.4-3.5 |
| `tests/test_benchmark_score.py` | grid.json carries the axis; no other output file mentions it | FR-011 |
| `tests/test_benchmark_stored_scores.py` | the §4 rows: every run `no axis record`, counts equal started, 013 figures unchanged | R-10 |

Tests that must pass **unedited**: everything under `tests/replay/`; `test_benchmark_cell.py`; `test_benchmark_workflow.py`; `test_benchmark_legacy_records.py`; the heatmap, calibration, graph and dashboard tests; `test_opencode_normalise.py`, `test_session_capture.py`, `test_session_models.py`. A needed edit to one of these is a stop-guard (SG-1), not a fix.

## Document changes

| File | Now | Change to |
|---|---|---|
| `BENCHMARK.md` §4 (new §4.5) | no axis passage | the two definitions as contract §1 states them; measured = the produced diff; the rule set, its version and the six v1 rules; cloned lines out and why; not-measured reasons; the axis never enters quality/composite/gate figures |
| `BENCHMARK.md` outputs passage | the 013 file list | the grid's two columns and the totals clause |
| `README.md` scoring passages | the 013 description | the axis columns and what not-measured means |
| `ARCHITECTURE.md` benchmarks package listing | modules through 013 | `axis`, `rules/verbosity/` |
| `ROADMAP.md` | Phase 2 landed except 2.9 | 2.9 landed; "Last verified" line |

Find each passage by its text; line numbers are from the base. Documents describe main, so these ride the branch.

## Stop-guards (binding; clearance only from the orchestrator)

- **SG-1**: a test listed as "must pass unedited" needs an edit, any test under `tests/replay/` changes result against the baseline, or an edit to a "not touched" path appears necessary. Stop, diagnose, report.
- **SG-2**: a step-0 verify item fails; the step-0 grep finds a reader of the grid or the totals line this plan does not name; or the implementation does not reproduce a figure of contract §1 on the fixtures or of contract §4 on the stored corpus. Stop and report. A stored figure is never edited to match the code.
- **SG-3**: any file would pass 800 lines.
- **SG-4**: the smoke run. Not launched without the orchestrator's explicit go; never parallel with live pipeline runs; only per the launch runbook (dedicated server, clean worktree, dedicated scratch repo). If no run can be had, step 8 is not done and SC-006 is reported open.
- **SG-5**: the stored-corpus fingerprint changes, `git ls-files runs/` prints anything, or a score is written under `runs/` during the round (the smoke run's own new bench dir aside).
- **SG-6**: a `temporal` test named in a gate reports "deselected", or `test_benchmark_stored_scores.py` reports "skipped" in the final gates. Neither is a pass.
- **SG-7**: `B/runs.py`, `B/grid.py` or `B/report.py` would import `temporalio`, radon or ast-grep-py; or `B/axis.py`'s pure functions would import `temporalio`.

## Risks

| Risk | Mitigation |
|---|---|
| radon (last release 2023) misbehaves on 3.13 | Step 0 imports and runs it on the container before any code depends on it; pure Python, sole dep `mando`. |
| ast-grep-py is "Alpha" on PyPI | The round uses the binding's core surface only (compile, rules, spans); pinned exact version; disclosed at GATE 2. |
| A rule matches nothing on real runs (silent zero) | A rule that fails to compile fails the measurement; the smoke run is the live check that real code flags something. |
| The integration branch is gone at measure time (late cleanup) | Reason `integration branch absent`, recorded, run unaffected (contract §2.3); the smoke run proves the normal timing (measure runs before finalize). |
| The workflow edit breaks an in-flight run | The `workflow.patched` seam is the 012-proven pattern; the unpatched branch is byte-identical to base. |
| Scoring slows on large selections | The reader parses bags already in memory; no extra pass over records; quickstart §2.3 keeps the one-minute bar. |
| The totals clause breaks a consumer of the line | Step-0 grep for readers of the totals line and `grid.json`; the documentation script reads the stage table, not the totals (013 T013). |

## Follow-ups to file (`.workspace/tasks/`)

- Clone detection united into verbosity, under a new rule-set version (needs a licence-checked detector).
- Erosion threshold and the rule set as user-tunable case config.
- Per-stage erosion delta (before/after each task) — needs per-task snapshots the pipeline does not keep.
- The axis in the experiments comparison view (Phase 4 will want it beside quality and cost).
- Whole-tree reference figures recorded beside the diff figures, if a consumer ever needs them.

## Items for GATE 2

1. **`pyproject.toml` and `uv.lock` change** — the first since round 013 froze them: `radon==6.0.1`, `ast-grep-py==0.50.0` as runtime dependencies (ruling R2). ast-grep-py's PyPI status is "3 - Alpha"; both are MIT.
2. **One benchmark run is sanctioned** (ruling R2): the todo-api smoke run, under SG-4 and the launch runbook. It also closes 013's "live confirmation of the opencode parser" follow-up.
3. **A new record kind appears in bench dirs**: `scope=AXIS`, judge literal `"axis"` (the pinned judge set grows by one); the axis rides the cell's existing `records.jsonl`.
4. **The totals line gains one clause** (`axis: N measured, M not measured`); every 013 figure is unchanged, and the stored-scores test's expectations are this round's to extend.
5. **The grid gains two columns** and `grid.json` new row/header fields; the file set a score writes is unchanged.
6. **Every pre-015 run reads "not measured" on the axis forever** (no integration branch survives); the axis exists for new runs only.
7. **The workflow gains a patched branch** (`015-quality-axis`) — the 012-proven seam; no BenchmarkWorkflow replay history exists to migrate.

## Execution notes

- Commit messages: subject and body only. No attribution trailers of any kind (no `Co-Authored-By:`, no `Claude-Session:`), even where a template prints one.
- Commits via `git commit -F <msgfile>`; one path per `git add` argument; no heredocs. Every file is written with the Write tool.
- Python runs in `kroker-dev` only (host repo venv only where an exec brief sanctions it, disclosed as in 013's verification). Git on a worktree runs on the host.
- Never chain two test runs in one shell call. `addopts` already carries `-q`.
- The reviewer gate is per task and blocking.
- The benchmark improvement plan under `docs/reports/` and the other untracked or modified files in the primary tree are the user's; never edit, add or commit them.

## Complexity Tracking

No constitution or repository-rule violation to justify.
