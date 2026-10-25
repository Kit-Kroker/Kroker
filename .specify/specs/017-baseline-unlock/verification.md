# Verification: Baseline Unlock (round 017)

**Branch** `017-baseline-unlock`, primary worktree `D:\own\Kroker`, code base main `e435bd10e20f4d905b151933c5e3234f86da3c49`.
**Phase 9 verification (T020).** STOP at the merge gate before main merge and paid pre-flight (T021).

---

## 1. Full gates at T020 (vs the baseline)

All commands executed in container `kroker-dev` (`kroker-kroker-dev-1`), worktree mounted at `/app`:

| Command | Baseline (`e435bd10`) | T020 Seen | Delta & Explanation |
|---|---|---|---|
| `uv run pytest` (fast tier) | 21 failed / 6397 passed / 12 skipped / 274 deselected | **21 failed / 6524 passed / 12 skipped / 275 deselected** | Exactly the SAME 21 pre-existing baseline failures (16 stale stored-score pins in `test_benchmark_stored_scores.py`, 3 DevEval parked-role drift in `test_deveval_corpus.py`, 1 corpus pin in `test_benchmark_corpus.py`, 1 prompt SHA pin in `test_prompt_migration.py` — per `baseline.md` §2); **+127 passed** = round 017 added test suites; **0 new failures**. |
| `uv run pytest -m temporal tests/replay` | 33 passed / 21 skipped | **34 passed / 21 skipped / 183 deselected / 207 warnings** | All golden replay scenarios reproduce their golden command projection and close cleanly. |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 9 passed | **9 passed** | Full sequence harness passes cleanly. |
| `uv run ruff check .` | 0 issues | **All checks passed! (0 issues)** | Clean across all 1747 files. |
| `uv run ruff format --check .` | 1731 files formatted | **1747 files already formatted** | Clean. |
| `uv run mypy` | 0 errors / 405 source files | **Success: no issues found in 406 source files (0 errors)** | Clean. |
| `python scripts/check_file_size.py` | RC 0, no output | **RC 0, no output** | All authored files <= 998 lines; `code/step.py` at exactly 998 physical lines. |
| `python scripts/check_clauses.py` | 202 declared / 10 untested / 0 dangling | **202 declared / 9 untested / 0 dangling** | Clause coverage improved (+1 tested). |
| Manifest check (`baseline-records.sha256`) | 972 lines | **972 / 972 files matched byte-for-byte** | Zero missing, zero extra, zero modified files under `runs/benchmarks/`. |

---

## 2. Success Criteria Evidence (SC-001 through SC-005)

- **SC-001 (Pre-flight todo-api run PASS or cleanly diagnosed)**:
  Deferred to Phase 10 (T021) per plan sequence. Clearance required before execution.
- **SC-002 (Spend split on live pre-flight)**:
  Deferred to Phase 10 (T021).
- **SC-003 (Recomputing stored acceptance verdicts)**:
  **PASSED**. Verified by `tests/test_benchmark_acceptance_stalled.py::test_sc003_recompute_stored_acceptance` (7 passed in 114s). Non-offline acceptance recomputation over stored `acceptance.yaml` copies yields byte-identical `verdict`, `reason`, `note`, and `separation` blocks (excluding only `kroker_commit` and `updated` timestamps).
  *Caveat (per T016 review)*: Cases where the oracle drifted from the base branch (e.g. `todo-api-greenfield`) are skipped per contract §11; `cat-cafe-monitoring` is effectively compared and matches byte-for-byte.
- **SC-004 (Stored record compatibility)**:
  **PASSED**. Verified by `tests/test_benchmark_record_compat.py` (7 passed in 40s). Every stored `.jsonl` record under `runs/benchmarks/` parses into `BenchmarkRecord` without validation errors, with `trace is None` preserved on all historical rows.
  *Caveat (per T007 review)*: 51 legacy lines carrying the removed `herdr` harness value are tolerated by `_is_removed_herdr_harness` per the baseline reader contract.
- **SC-005 (Research budget sum invariance)**:
  **PASSED**. Verified by `tests/research/test_research_dead_attempts.py` (16 passed in 23s). Invariance `_check_budget` sum holding across dead attempts and live rolls confirmed.

---

## 3. Requirement Mapping to Tests

| Requirement | Implementation / Tests | Status |
|---|---|---|
| **FR-001 to FR-003, FR-005 to FR-008, FR-011** | Evidence trace models (`TraceInventory`, `CriterionTrace`, `TraceBag`), normalization, containment, `task_unchanged` in `src/sdlc/stages/analyze/models.py`; tests in `tests/analyze/test_trace_enforcement.py` and `tests/test_benchmark_record_compat.py`. | **PASS** |
| **FR-004** | `build_trace_inventory` activity in `src/sdlc/stages/analyze/activities.py`; tests in `tests/analyze/test_trace_inventory.py`. | **PASS** |
| **FR-009, FR-010** | Wire `017-analyze-evidence` in `analyze.step`, analyst prompt v2 in `prompts.py`; tests in `tests/analyze/test_analyze_patched.py` and `tests/replay/test_graph_golden.py`. | **PASS** |
| **FR-020 to FR-023** | `StageReach` model, `cell_progress`, and propagation to oracle and cell records in `src/sdlc/benchmarks/cell.py`, `models.py`, `workflow.py`; tests in `tests/test_benchmark_stage_reach.py`. | **PASS** |
| **FR-024** | Stalled verdict rule in `acceptance.decide` ($\varepsilon=0.05$, 4 preconditions, `final_stage` resolution); tests in `tests/test_benchmark_acceptance_stalled.py`. | **PASS** |
| **FR-025, FR-026** | Oracle test exit code and JUnit error signal in `src/sdlc/benchmarks/oracle.py` and `workflow.py`; tests in `tests/test_benchmark_oracle_signal.py` and `tests/test_oracle.py`. | **PASS** |
| **FR-027** | Investigation of `theatre-box-office` 1 of 56 pass in `.specify/specs/017-baseline-unlock/finding-1of56.md`; accepted by orchestrator. | **PASS** |
| **FR-030 to FR-032** | Research dead attempt spend recording and aggregation via `read_dead_attempt_usage`; tests in `tests/research/test_research_dead_attempts.py`. | **PASS** |
| **FR-033, FR-034** | Attribution invariance (A-1) and living docs update in `BENCHMARK.md`; tests in `tests/research/test_research_dead_attempts.py`. | **PASS** |
| **FR-040** | Judge readers treat missing score as `NOT_EVALUATED` rather than 0; tests in `tests/test_benchmark_judge_none_readers.py` and retry test PINs. | **PASS** |
| **FR-050** | `plan_drift` generated artifact filtering under `017-plan-drift-generated` in `src/sdlc/stages/code/step.py`; tests in `tests/plan/test_plan_drift_generated.py`. | **PASS** |
| **FR-060, FR-061** | Replay suites, golden projections, and benchmark sequence harness green. | **PASS** |

---

## 4. Physical Line Counts (Ceiling <= 998)

Measured directly from disk:

| File | Physical Lines | Limit | Status |
|---|---|---|---|
| `src/sdlc/stages/code/step.py` | 998 | 998 | **PASS** |
| `src/sdlc/stages/analyze/step.py` | 293 | 998 | **PASS** |
| `src/sdlc/stages/analyze/models.py` | 244 | 998 | **PASS** |
| `src/sdlc/stages/analyze/prompts.py` | 125 | 998 | **PASS** |
| `src/sdlc/stages/analyze/activities.py` | 146 | 998 | **PASS** |
| `src/sdlc/stages/plan/step.py` | 202 | 998 | **PASS** |
| `src/sdlc/stages/plan/models.py` | 99 | 998 | **PASS** |
| `src/sdlc/stages/research/stage.py` | 490 | 998 | **PASS** |
| `src/sdlc/stages/research/step.py` | 476 | 998 | **PASS** |
| `src/sdlc/benchmarks/oracle.py` | 432 | 998 | **PASS** |
| `src/sdlc/benchmarks/acceptance.py` | 274 | 998 | **PASS** |
| `src/sdlc/benchmarks/runs.py` | 568 | 998 | **PASS** |
| `src/sdlc/benchmarks/workflow.py` | 530 | 998 | **PASS** |
| `BENCHMARK.md` | 927 | 998 | **PASS** |
| `tests/replay/scenarios.py` | 970 | 998 | **PASS** |

All authored files checked via `scripts/check_file_size.py` passed with 0 violations.

---

## 5. Replay Markers Taken

- `017-analyze-evidence`: Patched in `src/sdlc/stages/analyze/step.py`. Conditionally executes `build_trace_inventory`, formats analyst prompt v2 with changed file inventories and containment, enforces evidence traces mechanically via `enforce_traces`, and populates `outcome.untraced` and `report.traceability`.
- `017-research-ledger`: Patched in `src/sdlc/stages/research/step.py`. Conditionally executes `read_dead_attempt_usage` activity to fold dead attempt tokens into the stage spend record.
- `017-plan-drift-generated`: Patched in `src/sdlc/stages/code/step.py`. Filters schema-generated paths from plan drift checks.

Golden command projections in `tests/replay/golden/` were updated under `advisor-unlock-19` to project `activity:build_trace_inventory` and `activity:read_dead_attempt_usage`. The historical runs under `tests/replay/histories/` remain 100% untouched and byte-identical to baseline.

---

## 6. Whole-Round Harness Alignments & Orchestrator Waivers

In addition to `verification.md`, the following supporting alignments are bundled in T020:
- `tests/replay/test_graph_golden_chaos.py`: Filtered round 017 patched activities (`build_trace_inventory`, `read_dead_attempt_usage`) when checking immutable stored histories against golden command projections (**Orchestrator waiver granted**).
- `tests/fakes/fake_activities.py`: Added `fake_build_trace_inventory` and `fake_read_dead_attempt_usage` to `GIT_FAKES` for test workers.
- `tests/replay/scenarios.py`: Deduplicated explicit entries that are now cleanly inherited through `*GIT_FAKES`.
- `src/sdlc/demo/fakes.py`: Registered `build_trace_inventory` fake so demo worker runs unattended.
- `src/sdlc/workflows/feature.py`: Restored `untraced_criteria` re-export for backward compatibility.
- `tests/test_benchmark_workflow.py`: Updated `test_oracle_task_records_none_score_is_not_evaluated` from `FAIL` to `NOT_EVALUATED` per FR-040.
- `tests/test_grade_oracle.py`: Updated `fake_shell` stubs to return `(0, "")` conforming to `_bounded_shell` signature.

---

## 7. Stop Condition

All Phase 9 whole-round verification checks and gates are complete and green.
**STOPPING HERE** at the merge gate before merge to `main` as instructed. T021 (pre-flight run) awaits orchestrator clearance.
