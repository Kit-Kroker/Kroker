# Quickstart — validating round 024

Run everything from the repo root. `S/` = `src/sdlc/`, `T/` = `tests/`. No paid run is needed: every check uses fakes.

## 0. Baseline (before any change)

```bash
uv run pytest -q 2>&1 | tail -30 > .specify/specs/024-two-worker-pools/baseline-failures.txt
```

This captures the fast-tier failure ids on the shared tree. The SC-001 bar is "no ids beyond these".

## 1. Fast tier — pure pieces

**§1a — 024-i:**

```bash
uv run pytest -q tests/test_pools.py tests/test_pools_classification.py tests/test_worker_boot_plan.py tests/test_doctor_pools.py tests/test_bench_ids.py tests/test_janitor_lock.py tests/test_axis_prune.py
```

**§1b — 024-ii additions:**

```bash
uv run pytest -q tests/test_pools.py::test_inputs_omit_none tests/test_pools_call_sites.py
```

Expected:
- `pool_boot_plan` matches every row of the data-model truth table;
- `HARNESS_ACTIVITIES` partitions the registered set, and `CODING_ACTIVITIES` is a subset;
- `check_test_drift` is registered;
- the AST walk finds 0 unrouted harness sites and 0 routed core sites (§1b);
- `resolve_harness_queue` handles unset, blank, `default` and invalid names;
- every root input dumps with no `harness_queue` key when it is `None` (§1b);
- `axis` leaves no stale worktree registration (§1a);
- 50 same-second benchmark ids are distinct;
- a second janitor sweep is skipped while the lock is held;
- the doctor rows are as in contracts/worker-boot.md.

## 2. Temporal tier — placement, fail-fast, fleet (024-ii)

```bash
uv run pytest -q -m temporal tests/test_pools_routing.py tests/test_pools_failfast.py tests/test_pools_fleet.py
```

Expected:
- **SC-002:** the recorder interceptor shows routing on → harness names on `q` and everything else on default; routing off → no explicit queue. The harness `Worker`'s identity completed 100% of harness activities.
- **SC-005:** with no harness worker, each start path raises `HarnessQueueUnpolled` within 10 s, and `list_workflows` shows none created.
- **SC-003 / SC-004:** 5 concurrent benchmarks with cap 2 on the barrier fake (research R11): all complete; peak harness concurrency ≤ 2; some harness wait ≥ 0.5 s; core schedule-to-start p95 < 1 s.

## 3. Replay (SC-001, SC-006)

```bash
uv run pytest -q tests/replay/
git status --short tests/replay/   # must print nothing
```

Expected:
- every stored history replays;
- `test_pools_replay.py` (a) passes with the forced queue, and (b) shows the routing-on `greenfield_happy` projection equal to its stored golden.

## 4. Full battery (close-out)

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run python scripts/check_file_size.py
uv run pytest -q
uv run pytest -q -m temporal
```

Expected: fast-tier failures ⊆ `baseline-failures.txt`, no new temporal failures, and no file over 1000 lines.

## 5. Compose and manual smoke

Required for P-FR-010 (no daemon needed):

```bash
docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q   # exits 0
```

Optional, token-free:

```bash
KROKER_WORKER_POOL=harness uv run python -m sdlc.worker                                   # refuses: no queue
KROKER_WORKER_POOL=core KROKER_HARNESS_QUEUE=default uv run python -m sdlc.worker         # core worker
KROKER_WORKER_POOL=harness KROKER_HARNESS_QUEUE=default KROKER_HARNESS_CAP=2 uv run python -m sdlc.worker
KROKER_HARNESS_QUEUE=default uv run python -m sdlc.cli doctor                                        # pools row passes only while the harness worker runs
```
