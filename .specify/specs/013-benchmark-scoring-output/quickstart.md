# Quickstart: validating the scoring output rework (013)

How to prove the round works once built. Names are in
[data-model.md](data-model.md); behaviour, the expected figures (§12) and
the requirement-to-proof table (§13) are in
[contracts/scoring-output.md](contracts/scoring-output.md).

## Prerequisites

- Python checks run in the `kroker-dev` container with the branch's tree
  bound at `/app` and the stored records visible at `runs/benchmarks`.
  Never the host Windows venv. Confirm the binding before the baseline.
- One suite per shell call. `addopts` already carries `-q`.
- Git on the branch's worktree runs on the host.
- No benchmark run happens in this round. Nothing here starts a workflow.
- Every score in §2 is written to a directory outside `runs/` with
  `--out`, so the stored tree gains no file.

## 1. Automated gates

| Where | Command | Expected |
|---|---|---|
| container | `uv run pytest tests/test_benchmark_runs.py tests/test_benchmark_grid.py tests/test_benchmark_gate_oracle.py tests/test_benchmark_stored_scores.py` | green; `test_benchmark_stored_scores.py` reports passed, not skipped (a skip means the records are not mounted and is not a pass) |
| container | `uv run pytest tests/test_benchmark_heatmap.py tests/test_benchmark_heatmap_render.py tests/test_benchmark_scoring.py tests/test_benchmark_report.py tests/test_benchmark_score.py tests/test_benchmark_evidence.py tests/test_benchmark_sc_rollup.py` | green |
| container | `uv run pytest tests/test_benchmark_waste_bag.py tests/test_benchmark_waste_matrix.py tests/test_benchmark_agreement_matrix.py tests/test_benchmark_experiments.py tests/test_benchmark_cell.py tests/test_benchmark_models.py tests/test_benchmark_legacy_records.py tests/test_aggregate_benchmarks.py` | green |
| container | `uv run pytest tests/test_opencode_normalise.py tests/test_session_capture.py tests/test_session_models.py tests/test_claude_stream_normalise.py` | green; the captured-stream test is present and passed |
| container | `uv run pytest tests/graph/test_graph_node_types.py tests/test_dashboard_graph_wire.py tests/test_run_state_query.py tests/test_calibration_render.py tests/test_e36_imports.py` | green, no file edited (they import `CANONICAL_STAGES`) |
| container | `uv run pytest` | fast tier green; the count differs from the baseline only by the tests this round adds and removes |
| container | `uv run pytest -m temporal tests/replay` | same result as the baseline |
| container | `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | green with a non-zero passed count |
| container | `uv run ruff check .` then `uv run ruff format --check .` then `uv run mypy` | clean; mypy no new errors against the baseline |
| host | `python scripts/check_file_size.py` | no file over 1000 lines |
| host | `python scripts/check_clauses.py` | always exits 0, so read it: no new `clause with no test` line |

## 2. The score on stored records (the round's exit)

In the container, with `<out>` a directory outside `runs/`:

```text
uv run python -m sdlc.cli benchmark score --case cat-cafe-monitoring --out <out>/cat-cafe
uv run python -m sdlc.cli benchmark score --case todo-api-greenfield --out <out>/todo-api
uv run python -m sdlc.cli benchmark score --all --out <out>/all
```

| Check on `<out>/cat-cafe` | Expect | Criterion |
|---|---|---|
| the totals line of `report.md` | 18 started, 10 graded, 8 lost (research 4, clarify 4), 8 discarded oracle records, 18 statuses derived | SC-001 |
| the first section of `report.md` | the run grid: one group, 18 rows, header mean 0.708, all-pass 1/10 | SC-002, FR-007 |
| the arm on the group | `zai-coding-plan-glm-5.2`, marked recovered and untrusted | SC-003 |
| the code row of the stage table | first attempt 84/113, after repair 111/113; its quality cell reads n/a (the attempt share 0.725 is gone) | SC-005 |
| any file | no `composite` column or key with a value; one line says why | SC-006 |
| `heatmap.html` attrition layer | research `4/18`, clarify `4/14`, no value in later columns; header `8 of 18 lost before code` | SC-001, FR-014 |
| `heatmap.html` | every non-blank cell shows `num/den`; no cell under five observations is coloured | SC-007 |
| `gate-oracle.html` | analyze: rejected 10, one of them an oracle pass, escape n/a; merge: rejected 7, passed 3, escape 3/3 in grey; qa: copy of code | SC-009 |
| success-criteria section | `0 of 18 runs left a run summary`; no `bf-e2e` id anywhere | SC-008 |
| wall time of the command | under one minute | SC-012 |

| Check on `<out>/todo-api` | Expect |
|---|---|
| groups | three: pre-012 (5 started, 4 graded, 1 lost), 012 `unknown` (1 graded), 012 `b3344416` (1 graded, 1 lost at clarify) |
| every group header | grey figures (fewer than five graded) |

| Check on `<out>/all` | Expect |
|---|---|
| the command | exits 0 |
| every case | started = graded + lost + grading failed + no oracle |

Then on the host:

| Step | Expect | Proves |
|---|---|---|
| the records fingerprint (tasks.md standing rules) | equals the baseline's | SC-010 |
| `git ls-files runs/` | prints nothing | FR-043 |
| `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out <temp file>` | output equal to the baseline's | FR-047 |

Record each row's result in `verification.md`.

## 3. What this does not prove

- That the opencode parser counts tools on a live benchmark run. It is
  proved on one captured stream; the next run made for another reason
  confirms it (spec Follow-ups).
- The composite with two arms on real data. No stored case has two arms;
  a fixture proves the rule.
- Anything about model or harness quality.
- Where the eight lost cat-cafe runs actually died. A record is written
  when a stage ends, so the layer shows the last stage that ended.
