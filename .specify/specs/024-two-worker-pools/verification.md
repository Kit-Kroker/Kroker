# Verification — round 024 (two worker pools)

## §024-i — the pools exist, routing hard-off (T020, 2026-11-16)

All commands from repo root with `uv run`, on `main` at T019
(`111abf13`) plus the T020 battery fixes (this commit's parent diff:
the axis never-raise guard and two worker source-pin updates,
described below).

| Command | Result |
|---|---|
| `ruff check .` | PASS — all checks passed |
| `ruff format --check .` | PASS — 2144 files formatted (one byte fixed in-flight: the advisor consult's python fence had a double space; consults are ruff-format-scope in this repo) |
| `mypy` | PASS — no issues in 449 source files |
| `python scripts/check_file_size.py` | PASS — no file over the 1000-line ceiling (worker.py 399, pools.py 285) |
| quickstart §1a (the seven 024-i test files) | PASS — rc=0 |
| `pytest -q -m temporal tests/test_pools_failfast.py::test_poller_freshness` | PASS — the R6 proof on the `start_local` dev-server; observed lag 0.26 s (budget 5 s), linger 2.79 s at freshness 3 s, recorded in the test docstring |
| `pytest -q tests/replay/` | PASS — rc=0, no stored history or golden touched |
| `git status --short tests/replay/` | empty |
| `pytest -q` (full fast tier) | 2 failures, both pre-existing baseline ids (`test_sc003_recompute_stored_acceptance`, `test_prompt_shas_did_not_move`); the two `test_read_fixtures_fresh` baseline ids pass on the primary checkout as 023b documented. **Novel ids: none — a strict subset of `baseline-failures.txt`.** |

### Battery-driven fixes (found by the full-tier run, fixed before this file)

1. `measure_code_axis`'s new prune raised `FileNotFoundError` from its
   `finally` when `repo_url` did not exist — the never-raise contract's
   own test caught it (qa-chaos had flagged exactly this corner as
   unspecified and left it unpinned). The prune is now guarded against
   `OSError`.
2. `test_worker_registers_the_post_020_workflow_set` AST-walked the
   `Worker(..., workflows=[...])` literal; T009 moved the list to
   `_ALL_WORKFLOWS` (the 400-line ceiling). The pin now resolves the
   module-level name — same ten-workflow assertion, same intent.
3. `test_worker_validation_runs_before_worker_run` anchored on
   `worker.run()`, which T009's gather replaced. The pin now anchors on
   `asyncio.gather(` — same intent: validation precedes the run loop.

### Platform finding (T010, recorded for 024-ii)

`DescribeTaskQueue` is unimplemented on the `start_time_skipping`
test server (RPC 12). The poller proofs (T010 here, T031/T032/T033 in
024-ii) must use `WorkflowEnvironment.start_local`, the task's
"ephemeral dev-server", per the `test_dashboard_e2e.py` precedent.

### Standing statement

**024-i does not unblock R025; NFR-2 stays open until 024-ii.** The
pools boot and are observable (doctor row, compose overlay), fleet
enablers landed (bench ids, janitor lock, axis prune), but no start
path reads `KROKER_HARNESS_QUEUE` yet — run-level routing is 024-ii
(T021–T042). `docs/operations/worker-pools.md` carries the 024-i
banner saying so. ROADMAP's NFR-2 is deliberately untouched.
*(Superseded below by §024-ii.)*

## §024-ii — run-level routing, routing off by default (T042, 2026-11-16)

All commands from repo root with `uv run`, on `main` at T041
(`df8d2bc6`, the T040 close-out; the T041 battery ran on it and
produces no diff by design).

### The SC table

| SC | Command | Result |
|---|---|---|
| SC-001 single pool unchanged | `pytest -q`; `pytest -q -m temporal`; `pytest -q tests/replay/` | Fast tier: 8001 outcomes, failures = exactly the 2 known baseline ids (`test_sc003_recompute_stored_acceptance`, `test_prompt_shas_did_not_move`) — strict subset at equality. Temporal: 332 outcomes, 4 failures, all pre-existing (see battery note). Replay: 183/183, rc=0, `git status --short tests/replay/` empty; histories/golden byte-untouched all round. |
| SC-002 placement | `pytest -q -m temporal tests/test_pools_routing.py` | 17 outcomes green. The recorder interceptor proves queues: routing on → every harness-class activity carries `task_queue=q`, everything else default; routing off → no explicit queue anywhere. Identities (from the fleet run): 70 harness activities completed by the harness worker identity `harness@test`, 0 by core; 245 core activities by `core@test`, 0 by harness. Drivers cover graph/crew/deploy, bench, triage/assessment/tidy-up, maintenance execute; reflect is pinned as negative space; W-2 pinned from history (children never leave the core queue; every `WorkflowTaskStarted` identity `core@test`); the maintenance child's `harness_queue` proven on the wire by payload decode. |
| SC-003 fleet practical | `pytest -q -m temporal -s tests/test_pools_fleet.py` | 1 outcome green, five runs. 5 concurrent BenchmarkWorkflows with real GraphWorkflow children on two workers, harness capped at 2, barrier fake `run_coding_task`: all 5 start, all 5 complete, measured peak concurrent harness activities = 2 (cap held), every record's key set equals a solo run's. |
| SC-004 no starvation | same fleet run | With both harness slots held, core schedule-to-start p95 = 0.000062 s, max 0.000281 s (n=245) — far under the 5 s bound. Max harness queue-wait 1.08 s (n=70) against the cap, as designed. |
| SC-005 fail closed | `pytest -q -m temporal tests/test_pools_failfast.py` | 6 outcomes green. All six start paths (graph `start_graph_run`, the CLI's three inline paths, bench `_run_matrix`, maintenance `_enable`) refuse `HarnessQueueUnpolled` within 10 s naming the queue; `list_workflows` shows nothing created; schedules `apply_changes` propagates the refusal (library contract, T030 fix `a3ea34c7`). Chaos pins: refusal precedes every side effect (incl. schedule writes), blank env is routing-off (never a refusal), no memoization between attempts. |
| SC-006 routing-on replay | `pytest -q tests/replay/test_pools_replay.py` | Forced-queue replay of the stored corpus green (un-xfailed at T028 — the module-qualified `**pools.on_harness` form is what a host-process monkeypatch can reach inside the Replayer sandbox). A live routing-on `greenfield_happy` replays clean AND its `command_projection` equals the stored single-pool golden; routing-off symmetric — queue-blind in both directions. |
| SC-007 ceiling | `python scripts/check_file_size.py` | PASS at every task gate. No file over 1000; no baselined file grew. The round's largest files: `stages/code/step.py` 977 (T021's line-neutral extraction of the activity configs to `code/acts.py`, 50 lines, re-exported under pre-024 names), `tests/test_pools_routing.py` 946, `src/sdlc/pools.py` 305, `src/sdlc/worker.py` 399. |

### The T041 battery

| Command | Result |
|---|---|
| `ruff check .` / `ruff format --check .` / `mypy` / `python scripts/check_file_size.py` | PASS / PASS / PASS (no issues, 450 files) / PASS |
| quickstart §1a / §1b | 221 outcomes rc=0 / 22 outcomes rc=0 (`check_test_drift` registered; AST walk 0 unrouted harness, 0 routed core; root inputs dump no `harness_queue` key when None) |
| quickstart §5 | `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q` → rc=0 |

**Temporal-tier note (the 4 failures are not ours).** The full
`-m temporal` run shows 4 failures in `tests/durability/` (priced-usage
parity ×2, provider payload parity, wire neutrality). Proven
pre-existing: the exact 4 ids re-run in a throwaway worktree at the
024-i merge base `9adec977` fail identically, assertion diffs
byte-for-byte (frozen fixtures pin `glm-5.3-flash` where the registry
now routes `glm-5.3`; token-count drift vs the live fakes; wire
neutrality's frozen activity list predates `build_trace_inventory`).
024 touched no `agents/` file, no durability test, and no model/prompt
path. `test_wire_neutrality`'s own message says SG-2: stop, escalate,
do not regenerate the fixture — escalated to the owner here. **No new
temporal failures.**

### P-FR-012 evidence (reviewer tasks-1 gap 4)

`git diff --stat 9adec977..HEAD -- 'src/sdlc/stages/*/*.md' src/sdlc/graph/node_types.py src/sdlc/workflows/gates.py <27 containment-grep .py files>` → **3 hits, all classified, zero trust-layer hunks**:

1. `src/sdlc/core/models.py` (+11) — the R1 routing value itself:
   `PipelineConfig.harness_queue` with `validate_harness_queue_name`,
   `exclude_if=None` so routing-off wire bytes are pre-024-identical.
   The file appears in the containment grep for unrelated fields; the
   hunk touches only `PipelineConfig`.
2. `src/sdlc/workflows/crew.py` (+17 net) — `CrewTaskInput.harness_queue`
   (child copies verbatim) and the 7 `**pools.on_harness(...)` splats
   on the crew's activity calls. The containment fields
   (`containment_policy_path`, `containment_strict`) are context-only.
3. `src/sdlc/stages/code/step.py` (−42/+19 net) — T021's documented
   line-neutral move of `ACT`/`LONG_ACT`/`_long_act` to
   `code/acts.py` (re-exported under pre-024 names, `noqa: F401`), 3
   `on_harness` splats, and the `harness_queue=cfg.harness_queue`
   child copy into `CrewTaskInput`. The containment-on repair branch
   is untouched.

Stage contracts (`stages/*/*.md`), `graph/node_types.py` and
`workflows/gates.py`: **empty diff**. No GraphWorkflow node/handler
logic changed anywhere in the round (standing rule, held).

### The `check_test_drift` fix (latent defect, 024-i T005)

Research R2 found `check_test_drift` called by the code stage on
containment-on repair attempts but never registered in
`get_worker_activities()` — an activity nothing served. 024 registers
it, in the harness class (`src/sdlc/pools.py` `HARNESS_ACTIVITIES`,
28 members), and `tests/test_pools_classification.py` pins the
registration so the omission class fails the build (quickstart §1a).

### Residuals

- **R6 — no schedule-fire pre-flight.** The fail-fast check lands at
  apply time (`apply_changes` propagates `HarnessQueueUnpolled`), not
  as a pre-flight on schedule firing; a schedule armed before routing
  was enabled fires into the queue and its runs fail at start, loudly,
  naming the queue. Accepted this round; a true pre-flight would need
  a poller probe on a timer, which is R025 territory.
- **R1 — maintenance rollback asymmetry.** Maintenance executes on the
  harness queue but its rollback path does not inherit routing
  symmetrically; recorded, unchanged this round.
- **R12 — fleet notes deferred to R025.** The fleet proof is fakes on
  one host; operator-time instrumentation and paid-run evidence are
  R025's.
- **F1 semantics.** A harness worker dying with no fresh replacement
  leaves harness activities queued (Temporal's queue semantics; no
  loss, but no progress either). The doctor row names the remedy
  (`KROKER_WORKER_POOL=harness`).

### Judgment calls of the round

- **T031 green-on-arrival (reviewer-ruled).** The proof test landed
  green because plan order wires T030's start paths before T031's
  proofs; T029 (`a2b1e6c4`) is the committed RED of record. No
  post-hoc red manufactured (executor rules ban reverting others'
  files).
- **T032 split per its own rule** into a–b (rig + graph/crew/deploy +
  bench) and c–e (triage/assessment/tidy-up + maintenance + reflect).
  One waiver, documented in-test: bench's graph child stubbed BY NAME
  (the 012 pattern) while still recording the inherited
  `cfg.harness_queue`. Tidy-up needed no waiver — a real loop, its fix
  child parked at the HARD merge gate.
- **T030 no-bake deviation.** Nothing routing-shaped is baked into
  project-only `MaintenanceKickInput`; the kicker only signals and
  routing rides the loop's `state.config` from enable time.

### Platform finding, carried

`DescribeTaskQueue` stays unimplemented on the time-skipping server
(§024-i); every dynamic proof here uses `WorkflowEnvironment.start_local`.

### Standing statement

**024 closes NFR-2 as built**: two capability queues, run-level
routing off by default, every start path guarded, 34/34 harness sites
routed, replay queue-blind in both directions, the fleet cap
demonstrated on fakes. **R025 (fleet runs at operator time) is the
paid-evidence sequel**; the five-pool per-role form stays AP-2.5b.
