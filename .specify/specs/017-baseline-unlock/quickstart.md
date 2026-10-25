# Quickstart: validating 017 Baseline Unlock

Everything runs in `kroker-dev` (`kroker-kroker-dev-1` or `docker compose exec kroker-dev`) after its `/app` bind has been checked:
`docker inspect kroker-kroker-dev-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'`
must show this checkout on `/app`. Use `MSYS_NO_PATHCONV=1` for `docker exec`
from Git Bash.

## 1. Baseline (before any change)

```bash
docker exec kroker-dev uv run pytest                       # fast tier: note pass/fail counts
docker exec kroker-dev uv run pytest -m temporal tests/replay
docker exec kroker-dev uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py
python scripts/check_file_size.py                          # code/step.py at 998
```

Write the per-file manifest of `runs/benchmarks` to `baseline-records.sha256`
in this directory, using the same procedure as round 016. Records are
read-only for the whole round.

Record the `BenchmarkWorkflow` replay history now, on the pre-change code
(research D-6): one cell through the sequence test's stub-activity harness,
with no model call. Save it under `tests/replay/histories/`, and add its
replay test beside the existing ones. It must replay green on the baseline
before any change lands.

## 2. Per item (each task's own files, then the slice suite)

| Item | Commands | Expected |
|---|---|---|
| A analyze | `uv run pytest tests/analyze/ -q` | the fixture scenarios of US1 pass, including the >60k diff, normalization, containment and `task_unchanged` (empty, unknown, inherited) |
| B reach and verdict | `uv run pytest tests/test_benchmark_cell*.py tests/test_benchmark_acceptance*.py tests/test_benchmark_runs*.py -q` | US2 scenarios; recomputing the stored verdicts is identical (step 3) |
| C research | `uv run pytest tests/research/ -q` | US3 scenarios; `_check_budget` sum identical; attribution invariant test green |
| D judge | the reader tests named in tasks.md | `None` is never 0 |
| E plan_drift | `uv run pytest tests/plan/ tests/code/ -q` | US5 scenarios, patched and unpatched |

## 3. Whole-round checks

```bash
docker exec kroker-dev uv run pytest -m "slow or temporal"
docker exec kroker-dev uv run ruff check . && docker exec kroker-dev uv run ruff format --check .
docker exec kroker-dev uv run mypy
python scripts/check_file_size.py && python scripts/check_clauses.py
```

- **SC-003:** recompute every stored `acceptance.yaml`, following the
  reviewer plan finding 3 procedure.
  - Do NOT use `--offline`. It skips separation (`B/cli.py:526-527`), so
    `decide(..., separation=None)` returns `not_assessed` for every case.
  - For each case, copy its case dir to a throwaway root. Run the non-offline
    `sdlc benchmark accept` with `cases_root` pointed at the copy
    (`B/cli.py:485`). It reads stored records only (`load_evidence` /
    `build_runs`, `cli.py:539-546`) and starts no run.
  - Compare `verdict`, `reason`, `note` and the `separation` block against
    the stored file, ignoring `kroker_commit` and `updated` (always
    rewritten, `cli.py:501-502`). The comparison must be equal for every
    case.
  - The stored case dirs are never written. `dispatch_accept` saves into the
    root it is given (`cli.py:515`).
- **SC-004:** load every record under `runs/benchmarks` with the new model
  (the round 012 reader script pattern). There must be zero validation
  errors.
- **Records:** the manifest from step 1 is unchanged.

## 4. Pre-flight (paid, stop for user confirmation)

Steps:
1. Rebuild the worker on the merged main:
   `docker compose build --build-arg KROKER_COMMIT=$(git rev-parse --short HEAD) worker`,
   then recreate it.
2. Launch one todo-api-greenfield run (benchmark runbook memory) against the
   live temporal, with gate policy off.
3. Read the report and records.

Expected:
- analyze PASS, or each untraced criterion classified by hand from
  `trace.criteria_trace`;
- research spend present in the run summary's `research` role;
- `stage_reach` on the cell and oracle records;
- no judge `0` from a transient.

Any SC-001 item seen here means the round failed.
