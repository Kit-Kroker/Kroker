# Round 017 baseline — Baseline Unlock

Branch `017-baseline-unlock`, primary worktree `D:\own\Kroker` on main, base main
**`e435bd10e20f4d905b151933c5e3234f86da3c49`**.
`git diff --stat e435bd10 HEAD -- src/sdlc agents/analyst BENCHMARK.md tests` prints
nothing, so the plan's base facts hold.

Container: `kroker-dev` (`kroker-kroker-dev-1`), worktree at `/app`,
venv volume `kroker-verify-venv`, `runs/` bind from the primary tree
(`D:\own\Kroker\runs` → `/app/runs`; `runs/benchmarks` visible inside).
Python 3.13.15, uv 0.12.21.

## §1 Gates (container, one command per call, against `e435bd10`)

| Command | Result |
|---|---|
| `uv run pytest` | **21 failed, 6397 passed, 12 skipped, 274 deselected, 248 warnings in 627.42s** — see §2 |
| `uv run pytest -m temporal tests/replay` | **33 passed, 21 skipped, 183 deselected, 189 warnings in 71.48s** |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | **9 passed in 17.08s** |
| `uv run ruff check .` | **All checks passed! (0 issues)** |
| `uv run ruff format --check .` | **1731 files already formatted** |
| `uv run mypy` | **Success: no issues found in 405 source files (0 errors)** |

## §2 Fast-tier failures (all pre-existing at base; none caused by this round)

Exactly 21 pre-existing failures across three known groups:

| Group | Tests | Cause |
|---|---|---|
| Stale stored-score pins | 16 in `tests/test_benchmark_stored_scores.py` | Records grew past the pins after R1/R2/R4-r2; the known residual from 015/016 verification. |
| DevEval role drift | 3 in `tests/test_deveval_corpus.py` (`hone`, `particle-swarm-optimization`, `stocktrends`) | `fa1d58a1` parked those cases (`case.yaml` role `parked`); test asserts `CORPUS`. |
| Corpus / prompt pins | 2: `tests/test_benchmark_corpus.py::test_committed_records_match_their_cases`, `tests/test_prompt_migration.py::test_prompt_shas_did_not_move` | Existing pins pre-dating round 017 changes. |

## §3 Host checks

| Command | Result |
|---|---|
| `python scripts/check_file_size.py` | RC 0, no output (no file over the 1000-line ceiling) |
| `python scripts/check_clauses.py` | RC 0: `202 clauses declared, 10 untested, 0 dangling` |

## §4 Records manifest

`.specify/specs/017-baseline-unlock/baseline-records.sha256`: 972
lines, one per file under `runs/benchmarks`, `<sha256>  <forward-slash relpath>`, sorted by
path. `git ls-files runs/` prints nothing.

## §5 Line counts of files plan.md marks 'M' (physical lines)

| File | Lines |
|---|---|
| `src/sdlc/stages/analyze/models.py` | 51 |
| `src/sdlc/stages/analyze/activities.py` | 7 |
| `src/sdlc/stages/analyze/prompts.py` | 29 |
| `src/sdlc/stages/analyze/step.py` | 196 |
| `src/sdlc/stages/analyze/analyze.md` | 40 |
| `src/sdlc/stages/analyze/AGENTS.md` | 28 |
| `src/sdlc/stages/merge/step.py` | 680 |
| `src/sdlc/stages/merge/merge.md` | 56 |
| `src/sdlc/stages/plan/models.py` | 83 |
| `src/sdlc/stages/plan/step.py` | 201 |
| `src/sdlc/stages/code/step.py` | **998** (expected 998, ceiling 1000) |
| `src/sdlc/stages/qa/activities.py` | 695 |
| `src/sdlc/stages/research/budget_store.py` | 187 |
| `src/sdlc/stages/research/stage.py` | 473 |
| `src/sdlc/stages/research/step.py` | 406 |
| `src/sdlc/stages/research/activities.py` | 23 |
| `src/sdlc/stages/research/AGENTS.md` | 149 |
| `src/sdlc/workflows/models.py` | 100 |
| `src/sdlc/workflows/task_host.py` | 300 |
| `src/sdlc/workflows/feature.py` | 573 |
| `src/sdlc/workflows/graph_nodes/postplan.py` | 135 |
| `src/sdlc/benchmarks/models.py` | 545 |
| `src/sdlc/benchmarks/record_builder.py` | 102 |
| `src/sdlc/benchmarks/cell.py` | 144 |
| `src/sdlc/benchmarks/workflow.py` | 509 |
| `src/sdlc/benchmarks/oracle.py` | 395 |
| `src/sdlc/benchmarks/oracle_id.py` | 36 |
| `src/sdlc/benchmarks/runs.py` | 563 |
| `src/sdlc/benchmarks/acceptance.py` | 221 |
| `agents/analyst/instructions.md` | 1 |
| `BENCHMARK.md` | 891 |

Matches plan.md figures and `src/sdlc/stages/code/step.py` is at 998 lines.

## §6 Research D-n Citations Verification

Verified by reading source code at base commit `e435bd10`:
- **D-1**: `S/stages/analyze/step.py:151`, `S/workflows/graph_nodes/postplan.py:93`, `S/workflows/feature.py:542`, and `S/stages/merge/step.py:457-461` verified. `AnalyzeOutcome` design verified.
- **D-2**: `ANALYZE_EVIDENCE_PATCH = "017-analyze-evidence"` marker pattern verified.
- **D-3**: `S/stages/analyze/activities.py` stub verified (`ACTIVITIES = []`); `STAGE_MODULES` in `S/worker.py:140` verified; `TaskResult` in `S/workflows/models.py:56-68` verified; `TaskHost._dev_task` in `S/workflows/task_host.py:273-292` verified.
- **D-4**: `enforce_traces` and `untraced_criteria` in `S/stages/analyze/models.py` verified.
- **D-5**: `BenchmarkRecord` in `B/models.py` verified.
- **D-6**: `summarize_cell` in `B/cell.py:53-76`, `_oracle_record` and `cell_record` in `B/workflow.py:363+`, `tasks_total` in `S/stages/plan/step.py:148-163`, `blocking_checks` in `S/stages/merge/step.py` verified.
- **D-7**: `Run` in `B/runs.py`, `ArmEvidence` and `STALL_EPSILON` in `B/acceptance.py:15` verified.
- **D-8**: `_bounded_shell` at `B/oracle.py:327-329` and `grade_from_junit` at `B/oracle.py:31-58` verified.
- **D-9**: `budget_store.py`, `_research_subquestion_impl` at `S/stages/research/stage.py:270`, callers at `S/stages/research/step.py:203, 225, 280, 345`, fold sites at `294` and after `359` verified.
- **D-10**: `StageContext.emit` in `S/core/context.py:29`, `ReportHost._emit` in `S/workflows/report_host.py:38-44`, `_role_rollup` in `S/observability/summary.py:54-73` verified.
- **D-11**: `S/stages/code/step.py` at 998 lines verified; single call site at line 778 and import at line 54 verified; `S/stages/qa/activities.py:582-585` and `B/oracle_id.py:8` verified.
- **D-12**: `B/workflow.py:181-193`, `B/judge.py:294-298`, `B/workflow.py:249`, `B/acceptance.py:103-108` verified.
- **D-13**: Theatre scratch repo and R1 run IDs verified.
