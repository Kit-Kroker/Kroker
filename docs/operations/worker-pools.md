# Worker pools — operations

ADR-9 splits the worker into two capability pools. The **core pool**
(queue `ai-sdlc`) runs every workflow plus the cheap, pure activities.
The **harness pool** (queue `KROKER_HARNESS_QUEUE`) runs the 28
activities that spawn a coding CLI, execute repo code, or touch a run's
worktree or branches (`src/sdlc/pools.py` is the class authority —
when unsure, harness).

## Modes and variables

| Variable | Values | Default |
|---|---|---|
| `KROKER_WORKER_POOL` | `all` \| `core` \| `harness` | `all` |
| `KROKER_HARNESS_QUEUE` | a queue name; `default` means `ai-sdlc-harness` | unset = single pool |
| `KROKER_HARNESS_CAP` | integer ≥ 1 | unset = SDK default |

The boot behaviour of every combination — including every refusal
(`core`/`harness` without a queue; a cap without a queue; a cap < 1) —
is the **truth table in
[the feature's data model](../../.specify/specs/024-two-worker-pools/data-model.md)**,
which is normative; it is not copied here. Refusals exit non-zero
before connecting to Temporal, naming the variable and the fix.

With none of the three variables set, the worker is exactly the
pre-024 single pool (same queue, same registration, same startup
line) with one addition: `check_test_drift` is newly registered
(round 024 fixed a latent defect where it was scheduled but never
served).

## The compose overlay

```bash
docker compose -f docker-compose.yml -f docker-compose.pools.yml up
```

The overlay turns the `worker` service into the core pool and adds a
`worker-harness` service from the same image: pool `harness`, the same
queue, and `KROKER_HARNESS_CAP` (default 2). `docker-compose.yml`
itself is unchanged — without the overlay nothing changes.

## The cap is per process

`KROKER_HARNESS_CAP` sets `max_concurrent_activities` on **one harness
worker process**. Two harness replicas each get the full cap; the
fleet total is cap × replicas. Core is never capped by it.

### Sizing (Q3)

Crew wall-clock semantics are unchanged from single-pool: a crew turn
waits for a free harness slot rather than failing. Two safe shapes:

- **cap ≥ concurrent crew runs** — every crew turn starts immediately;
- **or accept headroom in `wall_clock_s`** — the crew default is 5400 s
  (`crew/layouts/code.yaml`), chosen with slow-proxy latency in mind;
  a cap below the concurrency simply spends some of that headroom
  queueing.

## The janitor

The worktree janitor (the A-terminal backstop sweep) runs in `all` and
`harness` modes only — never in `core`, which never mutates worktrees.
Each sweep holds a non-blocking flock on
`<worktrees root>/.janitor.lock`, so two worker processes sharing a
root never sweep concurrently; a held lock skips that pass with an INFO
log.

## The doctor row

`python -m sdlc.cli doctor` gains a `worker pools` row: with routing
off it reports `single pool (ai-sdlc)`; with routing on it requires a
fresh harness poller on the queue (the same R6 signal the start paths
fail-fast on) and names the remedy when there is none —
start one with `KROKER_WORKER_POOL=harness`.

## Session resume — one host only (R9)

`worker-harness` shares one named volume (`harness-sessions`) across
every harness replica on the host, mounted at the two CLI store
subpaths (`/root/.claude`, `/root/.local/share/opencode/storage`) so
the operator's `auth.json` read-only bind keeps working. **Session
resume is safe only when every harness replica mounts that same volume
on one host.** It is not safe across hosts: two hosts' replicas would
hold divergent stores with no sync. Worker-specific task queues (per
replica) remain future work (AP-2.6).

## Rolling back a worker past 024 (R1)

Routing-off payloads carry no `harness_queue` key at all, so rolling
back with routing off is safe for every input family. Routing-on
payloads differ:

- seven of the eight input families tolerate a pre-024 worker — it
  drops the unknown key and runs harness work on core (benign);
- the **maintenance family is `extra="forbid"`**: a pre-024 worker
  given a routing-on maintenance input — including one baked into a
  schedule — fails validation loudly and the workflow task retries
  without progressing.

**Remedy:** before rolling a worker back past 024, re-apply
maintenance schedules with `KROKER_HARNESS_QUEUE` unset, and let
in-flight routing-on maintenance loops drain or terminate them.

## Notes for R025 (R12)

Not fixed in 024; the fleet round owns them:

- Postgres-backed Temporal, not `start-dev`'s SQLite, for five or more
  paid concurrent runs;
- staggering starts and provider RPM limits;
- one Hindsight instance shared by the fleet;
- fixed-port collisions in case test suites;
- the board SQLite WAL under fleet load.
