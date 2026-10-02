# Quickstart: validating 005 in the dev container

All commands run in `kroker-dev` with the feature worktree mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`.

## Prerequisites

- Worktree based on main `0f4ac11`.
- For step 6 only: a real `ZAI_API_KEY` in the container environment. Steps 1–5 need no credentials.

## 1. Registry and policy (fast tier)

```bash
pytest tests/test_agents_registry.py tests/test_proposer_model_validation.py
pytest tests/durability/test_zai_route.py tests/test_model_construction_sites.py
```

Expect: all 11 roles report `zai:glm-5.3`; default and overridden base URL observed on the stub for each site category; guard test green.

## 2. Doctor

```bash
pytest tests/doctor
```

Expect: `ZAI_API_KEY` absent → fail naming it; placeholder → fail; set → pass.

## 3. Full default tier

```bash
pytest
```

Expect: green with dummy keys only. Compare pass count with the baseline recorded before the flip; the difference is this feature's new tests.

## 4. Temporal tier

```bash
pytest -m temporal
```

Expect: green, including `tests/durability/test_first_workflow_task_time.py` (no deadlock warning on the flipped registry), `test_inflight_resume.py`, `test_wire_neutrality.py` against the regenerated fixture, and the single-retry tests.

## 5. Static gates

```bash
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
git diff --stat 0f4ac11 -- pyproject.toml uv.lock src/sdlc/stages/code/step.py   # expect: empty
```

## 6. Live confirmation (spends tokens; needs the real key)

Run one proposer stage (clarify is the smallest) against the flipped registry with no `ZAI_BASE_URL` and no override. Record in the verification record: the artifact validated against its schema; the request went to `api.z.ai/api/coding/paas/v4`; the model name the endpoint reported. If the key is absent, stop and report — do not substitute a stub.

## Rollback

Per role: `--role-model <role>=anthropic:glm-5.2` (needs the `ANTHROPIC_*` variables). Whole feature: revert the registry commit; memo entries for the old strings are still on disk.
