# Contract — worker boot and pools

The entry point is unchanged: `python -m sdlc.worker` (and the compose `worker` service). Behaviour is selected by the environment (`data-model.md` §Environment). The truth table in `data-model.md` is normative.

## Guarantees

1. **G-1 (single pool unchanged).** With none of the three vars set, the process registers the same workflows and the same activities as pre-024, with one exception: **`check_test_drift` is newly registered** (research R2 defect fix). It polls only `ai-sdlc` and starts the janitor. The startup print line is unchanged.
2. **G-2 (refusals).** Every **refuse** row exits non-zero before connecting to Temporal, with one line naming the variable and the fix.
3. **G-3 (identity).** Each `Worker` carries the identity `"<core|harness>@<hostname>:<pid>"`.
4. **G-4 (order).** In `all` with a queue set, the harness `Worker` is started before the core `Worker`.
5. **G-5 (print).** Each `Worker` prints `worker running on task queue '<q>' (pool=<mode>[, cap=<n>])`. The single-pool line stays byte-identical to today's: `worker running on task queue 'ai-sdlc'`.

## Compose (P-FR-010)

`docker-compose.yml` keeps the `worker` service, which is the single-pool default. A new **`docker-compose.pools.yml`** overlay, used as `docker compose -f docker-compose.yml -f docker-compose.pools.yml up`, does three things:

- It sets `worker` to `KROKER_WORKER_POOL=core`.
- It adds a `worker-harness` service from the same image, with `KROKER_WORKER_POOL=harness` and `KROKER_HARNESS_CAP` (default 2).
- It sets `KROKER_HARNESS_QUEUE` on both. Both services mount `worker-worktrees`, `worker-repos` and the runs volume. `worker-harness` also mounts the `harness-sessions` volume at the R9 subpaths.

## Doctor (P-FR-008)

A new `check_worker_pools()` sits in `src/sdlc/doctor/checks.py`.

| Condition | Status | Message |
|---|---|---|
| `KROKER_HARNESS_QUEUE` unset | pass | `single pool (ai-sdlc)` |
| set, with a fresh poller | pass | `routing on: '<q>' polled by <n> worker(s)` |
| set, no fresh poller | fail | `routing on: '<q>' has no harness worker — start one with KROKER_WORKER_POOL=harness` |
| set, Temporal unreachable | fail | `routing on: cannot reach <host> to check '<q>'` (the same wait_for timeout as `check_temporal`) |
