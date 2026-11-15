# Research — round 024 (two worker pools, E-91)

`S/` = `src/sdlc/`. `T/` = `tests/`. Inputs:
- `spec.md` (GATE 1 cleared 2026-11-15);
- `consults/advisor.md` (D1–D7) and `consults/skeptic.md` (L1–L6);
- the installed `temporalio` 1.31.0 and `pydantic` 2.14.1.

Every decision below is either verified in this tree or marked as a proof task.

---

## R1 — The routing value is a `harness_queue` field on each root input

**Decision.** Add `harness_queue: str | None = Field(default=None, exclude_if=lambda v: v is None)` to these root inputs:

| Input | File |
|---|---|
| `PipelineConfig` | `S/core/models.py:369` |
| `TriageInput` | `S/workflows/triage.py:75` |
| `AssessmentInput` | `S/workflows/assessment.py:131` |
| `TidyUpInput` | `S/workflows/tidyup.py:77` |
| `DeploymentInput` | `S/workflows/deployment.py:66` |
| `CrewTaskInput` | `S/workflows/crew.py:66` |
| `CaseSpec` | `S/benchmarks/models.py:348` |
| `MaintenanceConfig` | `S/maintenance/models.py:84` |

`MaintenanceConfig` is carried in `MaintenanceKickInput` and `MaintenanceState`. The value is the resolved queue name, not a boolean (advisor D1).

**Rationale.**
- **Several roots carry no `PipelineConfig`** (advisor D1). A cfg-only field would never reach triage, assessment or maintenance activities.
- **`exclude_if` makes routing-off payloads byte-identical.** Verified 2026-11-15 through `pydantic_data_converter`: `M()` serialises to `b'{"a":1}'`, with no `"q":null`. Old payloads without the key validate to `None`. This settles skeptic L1's caveat: raw inputs are identical too, not only projections.
- **Rollback differs by input family (reviewer plan-1 gap 1).**
  - *Seven of the eight inputs* (`PipelineConfig`, `TriageInput`, `AssessmentInput`, `TidyUpInput`, `DeploymentInput`, `CrewTaskInput`, `CaseSpec`) do not set `extra="forbid"`. A pre-024 worker given a routing-on payload drops the key, routes off, and runs harness work on core. That is benign.
  - *The maintenance family is `extra="forbid"` throughout* (`S/maintenance/models.py:3, 93, 174, 192`). A pre-024 worker given a routing-on `MaintenanceKickInput` or `MaintenanceState`, including one baked into a schedule or carried by `continue_as_new`, **fails validation loudly**, and that workflow task retries without progressing.
  - *Remedy, documented in E2:* before rolling back a worker past 024, re-apply maintenance schedules with `KROKER_HARNESS_QUEUE` unset, and let in-flight routing-on maintenance loops drain or terminate them.
  - Routing-off payloads carry no key (`exclude_if`), so rollback with routing off is safe for every family. This is surfaced at GATE 2.
- **Hash check (advisor D1, done 2026-11-15).** No memoization key or benchmark config id hashes a cfg dump: `S/benchmarks/provenance.py:154` hashes `cfg.instructions` only, and `S/memoization/cache.py` `content_key` hashes stage-input JSON. With `exclude_if`, routing-off dumps are identical anyway.

**Alternatives.**
- *Workflow memo plus an outbound interceptor that stamps queues by activity name.* It needs zero call-site edits. **Rejected:**
  - `continue_as_new` carries memo only when the command sets it, and the maintenance loop continues-as-new.
  - Schedules and the replayer would need identical interceptor wiring.
  - Routing would be invisible to grep (advisor D1/D3).
  - It stays the fallback if R3's site count grows past what R4's tests can hold.
- *A separate envelope type.* **Rejected:** a ninth type for one field.

## R2 — The harness class: one authority, the rule amended

**Decision.**
- A new leaf module, `S/pools.py`, holds `HARNESS_ACTIVITIES: frozenset[str]` of activity names. It is free to import, like `S/task_queue.py`. It also holds `HARNESS_QUEUE_DEFAULT = "ai-sdlc-harness"`, `PoolMode`, `on_harness()` (R3) and `require_harness_poller()` (R6).
- **Rule A.1(c) is amended** (advisor D2 and skeptic L4 agree). It now covers activities that create, mutate, remove **or read** a run's worktree, integration branch or verification branch. Reads of the canonical checkout, or by-sha blob reads of a repository the run does not write, stay core.

| Class | Activities | Rule |
|---|---|---|
| harness | `run_coding_task`, `run_crew_turn` | (a) |
| harness | `create_worktree`, `merge_into_integration`, `setup_integration_branch`, `build_verification_branch`, `prepare_base_worktree`, `remove_verification_tree`, `cleanup_run_worktrees`, `prepare_crew`, `checkpoint_round`, `check_test_drift`, `measure_code_axis` | (c) writes |
| harness | `read_round`, `get_task_diff`, `read_committed_bytes`, `is_ancestor` | (c) reads of run state |
| harness | `grade_oracle`, `triage_build_probe`, `run_test_suite`, `run_lint`, `scoped_security_scan`, `measure_coverage`, `run_integration_checks`, `open_pull_request`, `deploy_apply`, `deploy_rollback`, `smoke_check` | (b) executes repo code, or uses the repo remote |
| core | everything else registered, including `paths_exist` (reads the canonical `repo_path`: `S/stages/clarify/step.py:149-151`), `classify_repo` and `check_brownfield_delta` (canonical-tree `git rev-parse`/`ls-tree`: `S/stages/context/activities.py:31,91`), `triage_*` other than the probe, `scan_*`, `verify_*_refs` and `discover_*` (by-sha blob reads), `probe_repair_child` (client only), `load_crew`, `load_drift_globs`, and all `TemporalDurability` agent activities | — |

- **Pre-existing defect found:** `check_test_drift` is in `S/vcs/__init__.py:55` (`vcs.ACTIVITIES`) and is called at `S/stages/code/step.py:711`, but it is **not registered** in `S/worker.py:get_worker_activities()`. A containment-on repair attempt would therefore schedule an activity no worker serves. 024 registers it, in the harness class. The classification test (R4) makes this kind of omission fail the build.
- **The janitor** (`S/worker.py:313`) is not an activity, but it removes worktrees (`S/vcs/janitor.py:62`). It runs in `all` and `harness` modes only, never in `core` (skeptic L3).

**Rationale.** When unsure, route to harness: a misplaced read costs one harness slot, while a misplaced write breaks the split (advisor D2). `drift.CODING_ACTIVITIES` (`S/benchmarks/drift.py:80`) must be a subset, asserted by a test rather than an import.

## R3 — The call-site mechanism

**Decision.** `on_harness(opts: Mapping, queue: str | None) -> dict` returns `dict(opts)` when `queue` is falsy, and `{**opts, "task_queue": queue}` otherwise. Every harness-class call site changes from `**ACT` to `**on_harness(ACT, q)`. Sites that pass inline keywords wrap them in `dict(...)`.

With routing off, no `task_queue` key reaches the SDK. The SDK then sets `input.task_queue or info.task_queue` (`temporalio/worker/_workflow_instance.py:3311`), so the command is unchanged.

The **33 call sites in 13 files**, by grep on 2026-11-15:

| File | Lines |
|---|---|
| `S/stages/code/step.py` | 311, 711, 740, 745 |
| `S/workflows/crew.py` | 149, 175, 322, 359, 367, 385 |
| `S/workflows/task_host.py` | 196, 274 |
| `S/workflows/graph_nodes/precode.py` | 58 |
| `S/workflows/graph_nodes/postplan.py` | 124 |
| `S/workflows/graph.py` | 223 |
| `S/workflows/tidyup.py` | 321 |
| `S/workflows/maintenance_execute.py` | 346, 475, 536 |
| `S/benchmarks/workflow.py` | 396, 472, 501 |
| `S/workflows/triage.py` | 194 |
| `S/stages/qa/step.py` | 139 |
| `S/stages/merge/step.py` | 340, 350, 396, 414, 420, 681 |
| `S/workflows/deployment.py` | 119, 141, 151 |

The crew-child `CrewTaskInput` construction at `S/stages/code/step.py:280` is not a site: it gets one field copy instead.

**How each site gets `q`:**
- graph hosts and stage steps: `cfg.harness_queue`;
- crew: `inp.harness_queue`;
- triage, tidy-up, deployment and assessment: `inp.harness_queue`;
- benchmark: `spec.harness_queue`;
- maintenance: `state.cfg.harness_queue`.

**Rationale.** It is explicit, greppable and pure. Two layers prove it (R4).

**Ceiling.** `S/stages/code/step.py` is at **998** lines. Its edits must be line-neutral, so step G1 first moves `LONG_ACT`, `_long_act` and the `ACT` constants (`step.py:~80-105`) to a new `S/stages/code/acts.py`. That frees about 25 lines and is a stage-internal move, not a cross-stage call. Other touched files above 700 lines are `S/cli.py` (959; it gets about 12 lines across 3 H1 sites, so it ends at about 971) and `S/workflows/assessment.py` (843; it gets about 2 lines). `S/benchmarks/models.py` (721) gets 2 lines. None is at risk.

## R4 — Two layers guarantee that no site is missed

1. **Static (fast tier).** `T/test_pools_classification.py`:
   - `registered == core ∪ harness` and `core ∩ harness = ∅`, built from `get_worker_activities()` names;
   - every `HARNESS_ACTIVITIES` name is registered;
   - `CODING_ACTIVITIES ⊆ HARNESS_ACTIVITIES`.

   `T/test_pools_call_sites.py` walks the AST of `S/`:
   - for each `workflow.execute_activity(` / `start_activity(`, it resolves the first argument's name;
   - a harness name requires a `**on_harness(...)` splat;
   - a core name forbids both `task_queue=` and `on_harness`;
   - it asserts no aliasing of `execute_activity` and no `execute_local_activity` of a harness name (advisor D3).
2. **Dynamic (temporal tier).** A test-only `Worker` outbound interceptor records `StartActivityInput.activity` and `.task_queue`. These fields were verified on `temporalio.worker.StartActivityInput`. It runs over a fake pipeline (code + crew + deploy), a benchmark cell, triage, tidy-up, assessment and a maintenance execute path. That covers the nine workflow types with harness-class sites (W-2). `ReflectWorkflow` schedules only the core `reflect` activity and is asserted all-core:
   - routing on: the queue equals the harness queue if and only if the name is in the class;
   - routing off: every recorded `task_queue` is `None`.

## R5 — Worker pool modes

**Decision.** These are env-configured, consistent with `TEMPORAL_HOST` (`S/worker.py:288`):

| Env | Values | Default |
|---|---|---|
| `KROKER_WORKER_POOL` | `all` \| `core` \| `harness` | `all` |
| `KROKER_HARNESS_QUEUE` | a queue name | unset (routing off) |
| `KROKER_HARNESS_CAP` | int ≥ 1 | unset (SDK default) |

**`all`, with no `KROKER_HARNESS_QUEUE`:** exactly today. One `Worker` on `ai-sdlc` registers everything, and the janitor runs.

**`all`, with the queue set:** two `Worker` objects in one process (advisor D5).
- The core `Worker` registers everything on `ai-sdlc` and is unchanged, so routing-off runs and pre-024 runs still work.
- The harness `Worker` registers only `HARNESS_ACTIVITIES` on the queue, with `max_concurrent_activities=cap`.
- The harness `Worker` starts first, and the two run under `asyncio.gather`.

**`core`:** all workflows plus the core activities only, on `ai-sdlc`, and no janitor. Boot is **refused** unless `KROKER_HARNESS_QUEUE` is set (advisor D5). This makes a missing queue loud.

**`harness`:** no workflows; `HARNESS_ACTIVITIES` only, on the queue (required); the cap applies; the janitor runs. Boot checks: `validate_crew_clis` and `check_harness_versions` always run. The registry and graph checks also run, as the safer default, because they cost about 1 s.

**Refusals:** a cap below 1 refuses boot in every mode. A cap set with no queue in `all` mode refuses boot, because it would have no effect.

**Identity.** Each `Worker` gets `identity=f"{pool}@{hostname}:{pid}"`, so SC-002 can tell from history which pool ran an activity.

## R6 — The fail-fast poller check

**Decision.** `require_harness_poller(client, queue, *, freshness_s=90, timeout_s=5)`:
- calls `client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(namespace, TaskQueue(name=queue), task_queue_type=TASK_QUEUE_TYPE_ACTIVITY))`;
- passes if any poller's `last_access_time` is within `freshness_s`;
- otherwise raises `HarnessQueueUnpolled(queue)`.

It queries the activity type because the harness worker registers no workflows. The freshness window matters because the server keeps listing a poller for about 5 minutes after it stops (advisor D4). Proof task C3 measures this against the dev-server.

**Where it is called.** Through `pools.resolve_harness_queue()` (reads `KROKER_HARNESS_QUEUE`), the value is set into the root input **and** checked, at:
- `S/graph/start.py:start_graph_run`, which covers `S/cli.py:581` and `S/operator/runtime.py:76` and so MCP;
- `S/cli.py:793, 839, 889`;
- `S/benchmarks/cli.py:336`;
- `S/maintenance/cli.py:252`;
- `S/schedules/apply.py:62`, at apply time. The resolved queue is baked into the schedule's action input.

A grep test asserts that every `.start_workflow(` in `S/` sits in a function that calls `resolve_harness_queue`, or is allowlisted. The allowlist covers child starts inside workflows and `S/demo/run.py`, which uses its own queue.

**Not adopted:** advisor D4.3, a routing-on pre-flight activity at the top of `MaintenanceKickWorkflow`. A schedule-fired run whose harness worker is down queues its harness work. That is the defined F1 semantics, identical to a harness worker dying mid-run, and the doctor and the Temporal UI show it. Adding a command to the kick workflow would buy a faster error at the cost of a new workflow-side surface. **Residual:** recorded in verification.

## R7 — Replay

**Decision.** No `workflow.patched()` marker is needed.

**Evidence:**
- skeptic L1 replayed a history recorded without `task_queue` against code passing `task_queue="q2"` under `Replayer(raise_on_replay_failure=True)`. It produced `replay_failure=None` on temporalio 1.31.0, so sdk-core does not compare activity queues.
- With routing off, the commands *and* the payloads are unchanged (R1, R3).
- The queue is a pure function of the recorded input, so any history recomputes its own queue (advisor D6).

**Permanent guard:** `T/replay/test_pools_replay.py`:
- **(a)** replays every stored graph and benchmark history with `on_harness` forced to `"x"`, and expects no failure;
- **(b)** records a routing-on run of the `greenfield_happy` scenario (it reaches the code stage) in-test, on two `Worker`s, replays it, and asserts its `command_projection` equals the stored single-pool golden for that scenario.

**No stored fixture is written.** This complies with `T/replay/AGENTS.md` rule 1, because (b) is in-test only. The scenario name is taken from `T/replay/golden/greenfield_happy.json`.

## R8 — Fleet-safe benchmark ids

**Decision.** `S/benchmarks/cli.py:338` changes from `bench-{case_id}-{int(time)}` to `bench-{case_id}-{int(time)}-{uuid4().hex[:6]}`. The `bench-{case_id}-{epoch}` prefix is kept, so readers that parse the prefix are unaffected. No in-tree code parses `bench-` ids: the string appears only at its construction site (grep, 2026-11-15).

## R9 — Session stores across harness replicas (GATE 1 Q2; skeptic L2)

**Decision.** The ruling holds as written. Every harness replica mounts **one shared session-store volume**, at the harness CLIs' store subpaths, **not** at a parent directory that would shadow the read-only `auth.json` bind (`docker-compose.override.example.yml:17`). Step E1 confirms the exact in-image paths before writing compose:
- `/root/.claude` (claude);
- `/root/.local/share/opencode/storage` (opencode).

**Skeptic L2 is partly rebutted.**
- *Concurrent writers on one store are already the status quo:* today's single worker runs many concurrent CLI subprocesses under one `HOME` (`S/harness/base.py:74,245`).
- *Containers on one host share one kernel,* so POSIX locks on a local named volume are honoured.

The residual risk is the CLIs' own file-locking discipline, which is unchanged from today.

**Accepted from L2:** the mount-path care, and the boundary statement. The crew note (P-FR-013) will say: resume is safe when every harness replica mounts the same session-store volume on **one host**, and not safe across hosts (AP-2.6).

## R10 — Janitor concurrency (skeptic L3)

**Decision.**
- The janitor runs only in `all` and `harness` modes (R5).
- `sweep_once` (`S/vcs/janitor.py:34`) takes a non-blocking advisory `fcntl.flock` on `<worktrees_root>/.janitor.lock` and skips the sweep if the lock is held. This covers two or more harness replicas sharing the worktree volume.
- `measure_code_axis` (`S/benchmarks/axis.py:222-236`) gains `git worktree prune` in its `finally`, so its `rmtree` no longer leaks registrations.

## R11 — Load proof (skeptic L5)

**Decision.** `T/test_pools_fleet.py` (temporal tier) uses a **scripted, barrier-holding fake** `run_coding_task`. It is registered under that name in the test's harness `Worker`, and each turn awaits a shared `asyncio.Event` with a ≥ 1 s hold.

The test runs **5 concurrent `BenchmarkWorkflow`s**: 2 of them on the same case, all started inside one second, with cap 2. It asserts from history timestamps:
- peak concurrent harness `ActivityTaskStarted` without completion ≤ 2;
- at least one harness activity waited ≥ 0.5 s between scheduled and started;
- while the barrier holds, a core model-call activity is scheduled, and its schedule-to-start p95 is < 1 s. That bound is stricter than SC-004's 5 s, so the test has a margin;
- all 5 complete;
- the record shapes match a solo run.

`S/demo/fakes.py` is unchanged. The barrier fake is test-local.

## R12 — R025 operating notes (skeptic L6; GATE 1 Q3)

**Decision.** This is documentation only, in `docs/operations/worker-pools.md` (new):
- the sizing rule: harness cap ≥ concurrent crew runs, or a wall-clock with headroom (Q3);
- the 5400 s crew default;
- Postgres-backed Temporal rather than `start-dev`'s SQLite (`docker-compose.yml:18`) for 5 or more *paid* runs;
- staggering and provider RPM;
- the one Hindsight instance;
- fixed-port collisions in case test suites;
- the board SQLite WAL.

None of these is fixed in 024. R025 owns them.
