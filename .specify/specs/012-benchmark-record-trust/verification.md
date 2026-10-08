# Verification: round 012 (T023 §1–§2; §3 pending the smoke run)

Tree: commit `9761c729` (T023 working tree, identical content). Date:
2026-10-08. All Python rows in `kroker-dev` with this worktree bound at
`/app`; binding confirmed first (md5 of `src/sdlc/benchmarks/models.py`
host = container = `b747689d295e7cc813afc66f551d3566`). One suite per
shell call. Baseline numbers from `baseline.md` (T001, at `7f5191d0`
plus the authorized pins-fix `378a2345`).

## §1 Automated gates

| Where | Command | Result | vs baseline |
|---|---|---|---|
| container | `uv run pytest tests/test_benchmark_paths.py tests/test_benchmark_provenance.py tests/test_benchmark_cell.py tests/test_benchmark_legacy_records.py tests/test_benchmark_record_builder.py tests/test_aggregate_benchmarks.py` | **76 passed** in 63.25 s | all green, none deselected |
| container | `uv run pytest tests/test_benchmark_judge.py tests/test_benchmark_cli.py tests/test_benchmark_recorder.py tests/test_benchmark_scoring.py tests/test_benchmark_report.py tests/test_benchmark_workflow.py tests/test_grade_oracle.py tests/test_calibration_render.py` | **128 passed, 4 deselected** in 94.53 s | green; the 4 deselected are the slow-marked subset, run in the slow row below |
| container | `uv run pytest tests/code tests/review tests/qa tests/analyze tests/merge` | **242 passed, 1 skipped, 4 deselected** in 72.76 s | green; the skip is the documented §5.8 qa-lens-unreachable case, the 4 deselected are crew-marked |
| container | `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | **5 passed** in 28.30 s | non-zero passed, not deselected (T013's suite) |
| container | `uv run pytest -m slow tests/test_grade_oracle.py` | **4 passed, 13 deselected** in 153.78 s | baseline 1 passed; now 4 slow tests (T016) — non-zero, not deselected |
| container | `uv run pytest` | **3 failed, 5849 passed, 12 skipped, 263 deselected** in 624.74 s | baseline 13 failed / 5674 / 11 / 255. The 3 failures are the same three git-reading tests as the baseline (in-container git cannot read the bind-mounted worktree; recorded there). The baseline's ten registry-mirror failures were fixed by the authorized pins-fix `378a2345`. Passes +175 (this round's new tests, and only those), skips +1 (documented), deselected +8 (new opt-in tests) |
| container | `uv run pytest -m temporal tests/replay` | **32 passed, 21 skipped, 171 deselected** in 106.76 s | identical to baseline (32/21/171 in 148.91 s) |
| container | `uv run ruff check .` | **All checks passed** | clean |
| container | `uv run ruff format --check .` | **1701 files already formatted** | clean (baseline 1684 files; count grew with the round's new files) |
| container | `uv run mypy` | **Success: no issues found in 390 source files** | no new errors (baseline 387 files, 0 errors; +3 modules this round) |
| host | `python scripts/check_file_size.py` | **exit 0, no output**; `src/sdlc/stages/code/step.py` at 997 lines (ceiling 1000, SG-3 margin 3) | clean |
| host | `python scripts/check_clauses.py` | **exit 0; 202 clauses declared, 10 untested, 0 dangling** — the 10 are the identical pre-existing baseline list (ARCH-1.4, CODE-1.6/1.7, MERGE-1.6–1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6) | no new untested clause, none dangling |

## §2 Checks on stored data (no run)

| Step | Result |
|---|---|
| `uv run python -m sdlc.cli benchmark score --case cat-cafe-monitoring` (container) | **completes**. Environment note: invoked with the same four dummy API keys `tests/conftest.py` sets, because the registry loader fails closed without them; scoring is read-only over the stored records, no model is called. The regenerated report at `runs/benchmarks/_case/cat-cafe-monitoring/score/report.md` has a `## Pre-012 records (untrusted)` section (12 rows, all pre-012), the line `includes 653 pre-012 records (untrusted)`, **no `## Cells` section** (grep count 0) and an empty 012 header table — no 012 rows anywhere. Score outputs are derived artifacts; the fingerprint below covers only `*.jsonl` records and is unchanged. |
| records fingerprint + `git ls-files runs/` (host) | `108 7d335188d0a0a47e0234a9a3cea64f3e42d80e958996a4e3fb89e2bb76a4306c` — equals the T001 baseline; `git ls-files runs/` prints nothing (exit 0) |
| `f3-reproduction.md` | outcome recorded: **not reproduced** — the direct sequence plus every environment seam was tried; the residue hypothesis (pruned by a venv re-sync) explains but can no longer be demonstrated; no cause outside the oracle's environment, SG-4 not fired |
| `gate-diagnosis.md` | a cause per gate and a decision per gate: merge (five of six subjects) — absolute `lint_clean`/scoped-test checks failing on genuine produced-code defects, right-reasoned rejections; the sixth — the advisory path acting on analyze's traceability; analyze — exact-`(task_id, criterion)`-text tracing with the analyst report not stored. Decision (orchestrator, SG-5): both gates stay rejections, no not-evaluated gate, causes on the record from T020; T021 carried the contract lines |

## §3 The validation smoke run

Pending the orchestrator's go (SG-7). To be appended: run id, commit,
each quickstart §3 row's result, and the changed fingerprint line.
