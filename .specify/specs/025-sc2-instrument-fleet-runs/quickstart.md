# Quickstart / validation — round 025

Commands run from the repo root.

## Part A (fast tier)
```bash
uv run pytest -q tests/test_run_summary_build.py tests/test_run_summary_model.py tests/test_operator_time.py tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py
uv run pytest -q          # full fast tier; compare to the baseline list in `.specify/specs/024-two-worker-pools/baseline-failures.txt`
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/replay    # replay/golden proof; no workflow code changed
```
Expected: the five named files green; fast tier no worse than baseline; replay green.

## Part B (operations; each step announced)
```bash
# 0 pre-flight: dedicated checkout of the fleet commit, clean, worker image check, doctor
git worktree add ../kroker-fleet <fleet-commit> && git -C ../kroker-fleet status --short   # must print nothing
uv run python -m sdlc.cli doctor
# 1 smoke (paid, unscored, both arms)
SDLC_RUNS_ROOT=<fresh dir> uv run python -m sdlc.cli benchmark smoke --gate-policy soft
# 2 each scored run
SDLC_RUNS_ROOT=<same dir> uv run python -m sdlc.cli benchmark run --case benchmarks/cases/<case>/case.yaml --arm zai-coding-plan-glm-5.3 --gate-policy soft
# 3 fleet score
SDLC_RUNS_ROOT=<same dir> uv run python -m sdlc.cli benchmark score --all
```
`--arm` name and exact verbs are re-verified against `S/benchmarks/cli.py` in T020 before run 1.
