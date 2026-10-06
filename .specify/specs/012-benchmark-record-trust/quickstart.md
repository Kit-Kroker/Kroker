# Quickstart: validating benchmark record trustworthiness (012)

How to prove the round works once built. Names are in
[data-model.md](data-model.md); behaviour and the requirement-to-proof
table are in [contracts/records-and-harness.md](contracts/records-and-harness.md).

## Prerequisites

- Python checks run in the `kroker-dev` container with the branch's tree
  bound at `/app`. Never the host Windows venv. Confirm the binding before
  the baseline; it has been left bound to an old worktree before.
- One suite per shell call. `addopts` already carries `-q`.
- Git inside the container cannot read a bind-mounted worktree. Anything
  that needs git on the branch runs on the host.
- No benchmark run other than §3 happens in this round.

## 1. Automated gates

| Where | Command | Expected |
|---|---|---|
| container | `uv run pytest tests/test_benchmark_paths.py tests/test_benchmark_provenance.py tests/test_benchmark_cell.py tests/test_benchmark_legacy_records.py tests/test_benchmark_record_builder.py tests/test_aggregate_benchmarks.py` | green; every file is fast tier, none deselected |
| container | `uv run pytest tests/test_benchmark_judge.py tests/test_benchmark_cli.py tests/test_benchmark_recorder.py tests/test_benchmark_scoring.py tests/test_benchmark_report.py tests/test_benchmark_workflow.py tests/test_grade_oracle.py tests/test_calibration_render.py` | green |
| container | `uv run pytest tests/code tests/review tests/qa tests/analyze tests/merge` | green |
| container | `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | green with a non-zero passed count. A deselect is not a pass |
| container | `uv run pytest -m slow tests/test_grade_oracle.py` | green with a non-zero passed count. A deselect is not a pass |
| container | `uv run pytest` | fast tier green; the count rises only by the new tests |
| container | `uv run pytest -m temporal tests/replay` | same result as the baseline taken in the first task |
| container | `uv run ruff check .` then `uv run ruff format --check .` then `uv run mypy` | clean; mypy no new errors against the baseline |
| host | `python scripts/check_file_size.py` | no file over 1000 lines; `src/sdlc/stages/code/step.py` at or under 1000 |
| host | `python scripts/check_clauses.py` | always exits 0, so read it: no new `clause with no test` line |

## 2. Checks on stored data (no run)

| Step | Expect | Proves |
|---|---|---|
| `uv run python -m sdlc.cli benchmark score --case cat-cafe-monitoring` in the container | completes; the report has a `Pre-012 records (untrusted)` section and no 012 rows | FR-027, contract §7.4 |
| the records fingerprint (tasks.md standing rules) on the host, and `git ls-files runs/` | the fingerprint equals the baseline's; `git ls-files` prints nothing | ruling R3 |
| Read `f3-reproduction.md` | an outcome: reproduced with cause, or not reproduced with what was tried | FR-010 |
| Read `gate-diagnosis.md` | a cause per gate and a decision per gate | FR-023 |

## 3. The validation smoke run (the round's exit)

One todo-api cell, run alone. Follow the benchmark launch runbook:
dedicated Temporal, clean worktree of the branch, the scratch repository
for the case, no other pipeline run on the machine.

The worker must know the commit. If the worker's tree is not a git
checkout it can read, start it with `KROKER_COMMIT` set to the branch
head (and `KROKER_TREE_DIRTY=0` for a clean tree).

```text
sdlc benchmark run --case benchmarks/cases/todo-api-greenfield/case.yaml
```

Then, on the new run directory under `runs/benchmarks/`:

| Check | Expect | Criterion |
|---|---|---|
| number of `*.jsonl` files | exactly 1 | SC-003 |
| `kroker_commit` on every line | the branch head, identical on every line; not `unknown` | SC-002 |
| `prompt_sha` on every line | 64 hex characters for prompted roles, `none:...` otherwise; no empty value | SC-002 |
| `arm` and `cell_id` on every line | identical on every line | SC-003 |
| clarify and architecture stage records | `quality.score` is a number, judge `llm_judge` or `staged_rubric` | SC-001 |
| for each task attempt: code, qa, review `speed` | ordered as contract §5.4; qa and review shorter than the attempt | SC-006 |
| review records | `cost.input_tokens` present | FR-021 |
| the cell record | `grading: graded`, `last_stage` a post-code stage | FR-006 |
| analyze and merge records | per `gate-diagnosis.md`: no rejection caused by a benchmark-only condition; any rejection names its cause in `error` | SC-007 |
| `report.md` | one `Cells` section; no pre-012 section | contract §7 |

Record the run id, the commit and each row's result in `verification.md`.

If the run aborts before code: that is a valid outcome for the harness
(the cell must then read `not_graded`) but it does not meet the exit
criterion. Report it; a second run needs the orchestrator's clearance.

## 4. What this does not prove

- Anything about model or harness quality. One cell, one arm.
- That dollars on harness records are right. They are not measured
  (Phase 2).
- That a prompt-builder change is visible in `prompt_sha`. It is visible
  as a different commit or a dirty tree (research R-7).
- Aborted cells, missing rubrics, the empty tree, a grading failure, a
  reviewer rejection with qa passing: those are proved by the tests in §1,
  not by the smoke run.
