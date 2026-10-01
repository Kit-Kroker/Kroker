# Quickstart: validating 003 in the dev container

All runs in `kroker-dev` (repo bind-mounted, named-volume venv). Never the host Windows venv. Read `.workspace/tasks/2026-09-09-temporal-tier-hangs-on-windows.md` first. One pytest per command; do not chain two pytest runs.

```bash
# once per session; mount the PRIMARY checkout (real .git), not a worktree
docker run --rm -v "D:\own\Kroker:/app" -v kroker-verify-venv:/app/.venv -w /app kroker-dev \
  sh -c "uv sync --frozen --extra dev --extra logfire && uv run --no-sync pytest -m temporal tests/replay -q"
```

| Step | Command (after the sync above) | Expected |
|---|---|---|
| Baseline (Phase A, on main) | `pytest -m temporal -q` | pass count recorded (was 160) |
| Existing replays | `pytest tests/replay/test_feature_replay.py -q` | all 16 replay, no history edited |
| Graph goldens | `pytest -m temporal tests/replay/test_graph_golden.py -q` | unchanged |
| New histories | `pytest tests/replay -q` | 3 new histories replay |
| Name/attribute fixture | `pytest tests/durability/test_activity_fixture.py -q` | scheduled sets exactly equal, heartbeat 0, registered deltas as listed |
| Loader contract | `pytest tests/durability -q` | fail-closed cases red->green |
| D8 pins | `pytest tests/graph_workflow/test_graph_dispatch_chaos.py -q` | green, expected set unedited |
| Research nested path | `pytest -m temporal tests/research -q` | brief produced; persisted budget holds |
| Assessment e2e | `pytest -m temporal tests/test_assessment_workflow_e2e.py -q` | completes |
| Fast tier | `pytest -q` | green |
| Lint / size | `ruff check . && ruff format --check . && python scripts/check_file_size.py` | clean |

Success = spec SC-001..SC-008. Anything that would break replay stops the run and goes to the orchestrator.
