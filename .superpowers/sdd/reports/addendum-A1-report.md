# Addendum A1 — Judge Plumbing

## Status
**Complete.** All five plumbing pieces landed; full suite green (77 passed, +6 new).

## Commits
- `26d523f` — `feat(benchmarks): judge plumbing — rubrics/judge_model on config, load_case_assets activity` (code + tests + report)

## What was built
1. **`BenchmarkConfig`** (`src/sdlc/models.py`): added `rubrics: dict[str, str]` (stage → rubric text) and `judge_model: str | None = None`. Additive, both safe defaults — `PipelineConfig()` behavior unchanged.
2. **`JudgeInput`** (`src/sdlc/benchmarks/judge.py`): added `judge_model: str | None = None` (the model the judge should USE). `author_model` retained (cross-family assertion target). Existing callers untouched.
3. **`load_case_assets` activity** (`src/sdlc/benchmarks/judge.py`): `async def load_case_assets(case_id, rubric_files) -> dict[str, str]`. Reads each rubric file path; relative paths resolve against `benchmarks/cases/<case_id>/`, absolute paths used as-is. Missing files are skipped (no crash) — that stage simply isn't judged. All file I/O isolated in the activity.
4. **`BenchmarkWorkflow.run`** (`src/sdlc/benchmarks/workflow.py`): calls `load_case_assets` once after `expand_matrix` and before the cell loop (via `execute_activity` with `RECORD_ACT` options); `_cell_config` now sets `cfg.benchmark.rubrics` + `judge_model` per cell. Import added to the `imports_passed_through()` block.
5. **Worker** (`src/sdlc/worker.py`): `load_case_assets` registered alongside `judge_artifact`.

## Test results
Commands run (worktree root `D:\own\ai-sdlc-temporal\.worktrees\pipeline-step-benchmarking`):
- `python -m pytest --tb=line` → **77 passed** (baseline 71 + 6 new)
- `python -m pytest tests/test_load_case_assets.py tests/test_benchmark_config.py tests/test_benchmark_judge.py tests/test_worker_registration.py tests/test_benchmark_workflow.py -v` → **17 passed**

New tests:
- `tests/test_load_case_assets.py` (3): reads two rubric files → `{stage: text}`; missing file skipped; empty map → `{}`.
- `tests/test_benchmark_config.py` (+1): `BenchmarkConfig()` defaults `rubrics == {}`, `judge_model is None`.
- `tests/test_benchmark_judge.py` (+2): `JudgeInput` accepts `judge_model`; defaults to `None`.

## Files
Changed:
- `src/sdlc/models.py`
- `src/sdlc/benchmarks/judge.py`
- `src/sdlc/benchmarks/workflow.py`
- `src/sdlc/worker.py`
- `tests/test_benchmark_config.py`
- `tests/test_benchmark_judge.py`
New:
- `tests/test_load_case_assets.py`

## Self-review
- **Additive + safe defaults:** `BenchmarkConfig()` and `PipelineConfig()` construct with no new required args — verified by the unchanged `test_default_pipeline_config_has_no_benchmark` and the new default test.
- **No file I/O in workflow code:** the only `load_case_assets` call site is `workflow.execute_activity(...)`; the activity owns all `Path`/`read_text`. Matches the determinism rule in the module docstring.
- **Serializable workflow args:** only `case_id` (str) + `dict(spec.rubrics)` (dict[str,str]) cross the activity boundary; the large rubric text returns through Temporal but stays well under the 2MB claim-check budget for these small rubric files.
- **`JudgeInput` is a dataclass** — `judge_model` placed after the required fields with a default, so positional construction still works; existing test instantiations unchanged.
- **Relative-path resolution verified** against the real golden case (`add-login-greenfield`): both `architect` and `clarifier` rubrics load via their `case.yaml` relative paths.
- **Existing `_cell_config` callers** (the two in `test_benchmark_workflow.py`) still work because `rubrics` defaults to `None` → `{}`.

## Concerns
- **`_CASES_DIR` is derived from `__file__`** (`parents[3]`). This relies on the editable install resolving `__file__` to the worktree source (true here, and the normal dev/CI posture). Under a wheel/non-editable install it would point into site-packages and relative rubric paths would silently no-op (returning `{}` — safe, but proposer judging would be inert). Acceptable for the current foundation; if benchmark runs ever move off editable installs, a `SDLC_CASES_ROOT` env var (mirroring `SDLC_BENCHMARKS_ROOT`) would be the clean fix. Not blocking A1.
- **`JudgeInput.judge_model` is plumbed but unused by `judge_artifact` yet** — by design. A2 wires the production Pydantic AI agent to read it; A3 populates it at call sites. For A1 it only needs to exist and round-trip.
- Rubric text travels through Temporal history as the `rubrics` dict on `BenchmarkConfig`. For the current single golden case this is ~1 KB total; if rubrics ever grow large, consider a claim-check (`ArtifactRef`) instead. Not a concern at current scale.
