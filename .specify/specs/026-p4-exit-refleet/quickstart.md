# Quickstart and validation: round 026

Run every command from the repo root.

## Part A (fast tier, $0)

```bash
uv run pytest -q tests/test_runs_paths.py tests/test_benchmark_evidence_roots.py tests/test_benchmark_sc_rollup.py tests/test_benchmark_score.py
uv run pytest -q tests/test_lint_scope.py tests/merge/ tests/qa/ tests/code/ tests/review/
uv run pytest -q tests/test_attempt_failure.py tests/test_architect_research_degrade.py tests/test_dotenv_isolation.py
uv run pytest -q          # full fast tier, WITH the fleet .env present at the repo root
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_file_size.py
uv run pytest -q tests/replay && uv run pytest -q -m temporal -k "replay or golden" && uv run python scripts/check_golden_rebaseline.py
```

Expected results:

- The named files are green.
- The fast tier shows exactly the baseline ids in `.specify/specs/024-two-worker-pools/baseline-failures.txt` (two of which are worktree-only), **with `.env` present**.
- The replay suites are green.
- `S/stages/code/step.py` stays at or under 1000 lines.

## The $0 re-score of 025 (FR-005, the Part B entry condition)

```bash
SDLC_RUNS_ROOT=/home/maksim/work/kroker-fleet-runs-025 uv run python -m sdlc.cli benchmark score --all
```

This writes `<root>/benchmarks/_all/score/`. That is a write into the 025 evidence root, so it is run **against a copy**:

```bash
D=$(mktemp -d) && cp -a /home/maksim/work/kroker-fleet-runs-025/. "$D"/ && SDLC_RUNS_ROOT="$D" uv run python -m sdlc.cli benchmark score --all
```

Expected:

- roots line naming `$D/benchmarks` and `$D/pipeline` (both from `SDLC_RUNS_ROOT`);
- 4 of 6 scored runs summarized;
- no-summary runs: `…readtime-1794957781-bccb20` crashed and `…lice-1794980735-e87339` terminated;
- smoke excluded: `…todo-api-greenfield-1794953137-1ba84e`;
- commit set `{ce3a36f8…}`;
- SC-1 0.00 (n=6);
- SC-1-strict 0.00;
- SC-2-all n/a (4 measured, median 0.75 min);
- SC-3 0.385 (n=13).

## Part B (operations; every step announced)

These are the 025 quickstart Part B steps with `--gate-policy hard` everywhere:

```bash
git worktree add ../kroker-fleet-026 <fleet-commit> && git -C ../kroker-fleet-026 status --short   # must print nothing
SDLC_RUNS_ROOT=<fresh dir> uv run python -m sdlc.cli benchmark smoke --gate-policy hard
SDLC_RUNS_ROOT=<same dir> uv run python -m sdlc.cli benchmark run --case benchmarks/cases/<case>/case.yaml --arm zai-coding-plan-glm-5.3 --gate-policy hard
SDLC_RUNS_ROOT=<same dir> uv run python -m sdlc.cli benchmark score --all
```

Pre-flight (T040) re-verifies the verbs and `--arm` names against `S/benchmarks/cli.py`, the 025 host fixes, and the attendant's liveness (a planned gate decided by `timeout` is infra, research R8).
