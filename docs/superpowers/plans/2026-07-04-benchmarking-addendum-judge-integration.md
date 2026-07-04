# Benchmarking Addendum: Proposer-Stage Judge + Integration Tests

> Follows `2026-07-04-pipeline-step-benchmarking.md`. Closes the two gaps surfaced by the final whole-branch review (I-1 proposer-stage inertness; I-2 no integration tests).

## Goal
Make proposer stages (clarify, architect, planner, merge) actually benchmarkable by quality (wire `judge_artifact` into `FeatureWorkflow`'s benchmark path with a production judge default), and regression-protect the purity + matrix invariants with time-skipping Temporal integration tests.

**Out of scope (foundation):** making proposer agents honor per-cell `cfg.roles` (the `roles.py` module-constant `MODEL` binding). That's a foundation refactor tracked separately; it means proposer *models* still don't vary across cells, but proposer *quality scores* will now populate (closing I-1a). The model-variance half (I-1b) stays a documented foundation dependency.

## Task A1: Judge plumbing
- Add `rubrics: dict[str, str]` (stage → rubric text) and `judge_model: str | None` to `BenchmarkConfig` (in `src/sdlc/models.py`).
- Add `JudgeInput.judge_model: str | None` (the model the judge should USE; `author_model` remains the cross-family assertion target).
- New activity `load_case_assets(case_id, rubric_dir) -> dict` in `benchmarks/judge.py` (or `benchmarks/recorder.py`): reads each `rubric-<stage>.md` under the case dir, returns `{stage: rubric_text}`. File I/O in the activity.
- `BenchmarkWorkflow.run`: after expanding the matrix, call `load_case_assets` once, populate `cfg.benchmark.rubrics` + `judge_model` in `_cell_config`.

## Task A2: Production judge default
- Replace `_default_judge`'s `raise RuntimeError` with a real Pydantic AI `Agent` call: model = `inp.judge_model`, system prompt = "Score the artifact against the rubric; return ONLY JSON {score, components}", user message = rubric + artifact. Parse the response (reuse the clamping/error logic in `_judge_sync`).
- Keep the injectable boundary: `_set_judge_fn` still overrides (tests inject a fake; no real model call in CI).
- The agent is constructed lazily per call (not at module import — avoids the eager-construction smell).

## Task A3: FeatureWorkflow judge calls
- In benchmark mode, after each proposer stage (clarify, architect, plan, merge) produces its artifact, call `judge_artifact(JudgeInput(artifact_json=..., rubric=cfg.benchmark.rubrics.get(stage, ""), author_model=..., judge_model=cfg.benchmark.judge_model))` via `workflow.execute_activity`.
- Use the returned `QualityScore` in the emitted `BenchmarkRecord` (instead of the current `quality_score=None`).
- If `rubrics[stage]` is missing OR judge returns `judge="error"`, the record still emits with `quality.score=None` (graceful — no stage fails because the judge errored).
- Code-stage records unchanged (still contract-scored).

## Task B: Integration tests (time-skipping)
- `tests/test_factory_integration.py`: start a `WorkflowEnvironment.start_time_skipping()`, run a worker with FAKE activities (fake `run_coding_task`, `run_test_suite`, `create_worktree`, `get_task_diff`, the TemporalAgent activities) + real `record_benchmark`. Run `FeatureWorkflow` twice: once with `benchmark.case_id=None` → assert ZERO `record_benchmark` calls (purity); once with it set → assert records appear (emission).
- `tests/test_benchmark_workflow_integration.py`: run `BenchmarkWorkflow` with a 2-cell matrix where one cell's child escalates → assert the other completes and `finalize_benchmark_report` runs.
- Use `temporalio.testing.WorkflowEnvironment`. Fake activities return canned `HarnessRunResult`/`QAReport`/etc. Keep the judge injectable (fake judge_fn) so no real model calls.

## Testing
- A1: unit test `load_case_assets` reads rubric files (tmp dir); `BenchmarkConfig` carries rubrics + judge_model.
- A2: unit test the production judge with a fake Pydantic AI agent response (mock `Agent.run_sync` or inject); confirm clamping + error paths.
- A3: unit test that the judge score flows into the record (extend `test_factory_recorder.py` or a new focused test with a fake judge_fn).
- B: the integration tests above.
- Full suite stays green throughout.
