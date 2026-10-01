# Quickstart: validating 004 in the dev container

All runs in `kroker-dev` (repo bind-mounted, named-volume venv). Never the host Windows venv. One pytest per command; do not chain two pytest runs. Contracts: [model-resolution-contract.md](contracts/model-resolution-contract.md), [proposer-override-validation.md](contracts/proposer-override-validation.md).

```bash
# once per session; mount the PRIMARY checkout (real .git), not a worktree
docker run --rm -v "D:\own\Kroker:/app" -v kroker-verify-venv:/app/.venv -w /app kroker-dev \
  sh -c "uv sync --frozen --extra dev --extra logfire && uv run --no-sync pytest -q"
```

New test files below are named by the tasks; paths are the planned ones.

| Step | Command (after the sync above) | Expected |
|---|---|---|
| Baseline (Phase A, on main) | `pytest -q` then `pytest -m temporal -q` | pass counts recorded |
| Stacked retries on main | `pytest -m temporal tests/durability/test_single_retry_layer.py -q` on a clean worktree of main | always-429 count is above the budget (expected 9): the test fails on main |
| Single layer | same file on the branch | always-429 count <= 3; fail-once == 2; 400 stub == 1; override provider bound holds |
| Capability coverage | `pytest tests/durability/test_single_retry_coverage.py -q` | every durable agent and both plain research-stage agents carry it; every constructible provider runs single-layer |
| Wire neutrality | `pytest -m temporal tests/durability/test_wire_neutrality.py -q` | no-override names, order and model ids equal the Phase A fixture |
| Which model answered | `pytest -m temporal tests/test_model_forwarding.py -q` | serial role, both clarify fan-out agents, the research sub-question fan-out and a benchmark-arm default see the override id; an un-overridden role sees its registry id; usage, price input and cache key match |
| Label guard | `pytest tests/test_run_role_guard.py -q` | disagreeing label under an override fails non-retryably |
| Validation | `pytest tests/test_cli_role_model.py tests/test_proposer_model_validation.py -q` | table in the validation contract holds on all three entry paths |
| Memo re-key | `pytest tests/test_role_model_resolution.py -q` | override key differs from the pre-fix override key; no-override key unchanged |
| Existing replays and goldens | `pytest -m temporal tests/replay -q` | green, no history or golden edited |
| First workflow task time | `pytest -m temporal tests/durability/test_first_workflow_task_time.py -q` | under the detector budget, including a non-anthropic override |
| Fast tier | `pytest -q` | green, count >= baseline |
| Temporal tier | `pytest -m temporal -q` | green, count >= baseline |
| Lint / size | `ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py` | clean; `stages/code/step.py` <= 991 lines |

Success = spec SC-001..SC-005. A replay failure, a changed no-override wire fixture, or an always-429 count above the budget after the capability is attached stops the run and goes to the orchestrator (plan stop-guards SG-1..SG-5).
