# Tasks: two worker pools — round 024 (E-91)

**Input**: `.specify/specs/024-two-worker-pools/`:
- spec.md: US1–US4, P-FR-001..013, SC-001..007
- plan.md: split decision; steps A1..J2
- research.md: R1–R12
- data-model.md; contracts/{worker-boot,routing-wire}.md; quickstart.md §0–§5

**Two crew rounds from this one file.**
- **024-i** is T001–T020. Routing stays hard-off.
- **024-ii** is T021–T042. It needs 024-i merged.
- Each round is one L. Do not start 024-ii in the 024-i crew run.

**Tests**: REQUIRED (test-first). Every implementation task is preceded by a RED test task that must fail first. The exceptions:
- **PROOF** tasks (T010, T039) test platform behaviour. If one fails, **STOP and report**; do not work around it (plan risk 1).
- The docs tasks are guarded by the battery.
- T017 and T031 put RED and the fix in one task. The test is committed failing in the same task, before the fix, and the commit body shows the red run (reviewer tasks-1 gap 3).

**Sizes**: **S** ≈ ≤30 min; **M** ≈ one focused sitting. No task is L.

**Executor rules**:
- One commit per task, with the task id in the subject.
- Commit messages are subject + body, with no attribution trailers.
- Never `git add -A`, never stash, never revert files you did not create.
- `S/` = `src/sdlc/`, `T/` = `tests/`. Commands run from the repo root with `uv run`.

**Standing constraints for every task**:
- No change to `GraphWorkflow` node or handler logic. The `S/workflows/graph_nodes/*` edits are only the `**on_harness(...)` splat at an existing activity call.
- No `<stage>.md` change.
- No trust-layer change: containment, `pre_tool`, the env allowlist, gates, ADR-6 checks.
- No file under `T/replay/histories/` or `T/replay/golden/` changes (`git status --short tests/replay/` shows only new test files).
- No workflow code reads the environment (W-3).
- No file passes 1000 lines.
- No paid run.

## Format: `[ID] [P?] [Story] Description (size)`

---

# Round 024-i — the pools exist (routing hard-off)

## Phase 1: Setup

- [x] T001 Capture the fast-tier baseline. Run `uv run pytest -q` on HEAD in a throwaway `git worktree` (for example `/tmp/opencode/024-baseline`). Write the sorted FAILED ids to `.specify/specs/024-two-worker-pools/baseline-failures.txt`, with a header naming the commit and the procedure. Diff against `.specify/specs/023b-daper-acts-verifies/baseline-failures.txt` and report any novel id rather than proceeding. The `tests/test_read_fixtures_fresh.py` ids are expected in a throwaway worktree, per 023b's note. (plan A1; quickstart §0) **(S)**

## Phase 2: Foundational — the class authority (blocks every story)

- [x] T002 RED: write `T/test_pools.py` for `S/pools.py`'s pure surface (data-model §pools).
  - `PoolMode` values.
  - `HARNESS_QUEUE_DEFAULT == "ai-sdlc-harness"`.
  - `on_harness(opts, None)` and `on_harness(opts, "")` return a dict equal to `opts`, without a `task_queue` key, and do not mutate `opts`. `on_harness(opts, "q")` adds `task_queue="q"`.
  - `resolve_harness_queue`: unset → `None`; blank → `None`; `"default"` → `HARNESS_QUEUE_DEFAULT`; `"my.q-1"` → itself; `"bad q"` and a 201-character name → `ValueError`.
  - `S/pools.py` imports nothing from `sdlc` beyond leaf modules (the test asserts that `import sdlc.pools` does not import `sdlc.worker`).
  (R2, R3) **(S)**
- [x] T003 Create `S/pools.py` with `HARNESS_QUEUE_DEFAULT`, `PoolMode` (`StrEnum`), `on_harness`, `resolve_harness_queue` (name regex `^[A-Za-z0-9._-]{1,200}$`), and `HARNESS_ACTIVITIES`, the 28 names in research R2's harness rows. Write a module docstring citing ADR-9, rule A.1(a–c) as amended in R2, and the "prefer harness when unsure" rule. Make T002 green. **(S)**
- [ ] T004 RED: write `T/test_pools_classification.py`. Build `names = {a.__temporal_activity_definition.name for a in get_worker_activities()}` from `S/worker.py`. Assert:
  - `HARNESS_ACTIVITIES ⊆ names`, so every harness name is registered;
  - `"check_test_drift" in names`;
  - `CODING_ACTIVITIES` (`S/benchmarks/drift.py:80`) `⊆ HARNESS_ACTIVITIES`;
  - every name in `S/vcs/__init__.py:ACTIVITIES` is registered;
  - the janitor is not an activity name.

  This is RED today because of `check_test_drift` (R2 defect). (P-FR-002) **(S)**
- [ ] T005 Register `check_test_drift` in `S/worker.py:get_worker_activities()`: add it to the `from .vcs import (...)` block and to the returned list beside `get_task_diff`. Make T004 green. Grep `T/` for tests that pin the registered-activity count or list (for example `T/test_vcs_activities.py:25`, `T/test_worker*.py`) and update only an exact-count assertion, naming the R2 fix in the test comment. (R2) **(S)**

---

## Phase 3: User Story 2 (024-i half) — the worker can boot as a pool (P1)

**Goal**: `KROKER_WORKER_POOL` selects `all`, `core` or `harness`, with the cap and the janitor placement. Routing is not wired yet.

**Independent test**: quickstart §1a (`T/test_worker_boot_plan.py`) and the §5 smoke refusals.

- [ ] T006 [US2] RED: write `T/test_worker_boot_plan.py`.
  - **The truth table.** One parametrised case per row of the data-model `pool_boot_plan` truth table, including every **refuse** row. A refusal raises `ValueError`, and the message names the variable and the fix.
  - **Bad env values.** `KROKER_HARNESS_CAP="0"` and `"-1"` refuse in every mode; `KROKER_WORKER_POOL="bogus"` refuses.
  - **Filters.** `core_activities()` ∪ `harness_activities()` equals `get_worker_activities()` by name, and the two are disjoint.
  (P-FR-003, P-FR-004; R5) **(S)**
- [ ] T007 [US2] Implement `PoolBootPlan` (frozen dataclass), `pool_boot_plan(mode, queue, cap)` and `boot_plan_from_env(env=os.environ)` in `S/pools.py`. Implement `core_activities()` and `harness_activities()` in `S/worker.py`, filtering `get_worker_activities()` by `activity.defn` name against `HARNESS_ACTIVITIES`. Make T006 green. **(S)**
- [ ] T008 [US2] RED: write `T/test_worker_main_pools.py` (fast tier: monkeypatch `Client.connect`, `Worker` and `worktree_janitor` with recorders; no server).
  - **No vars set (G-1, G-5).** Exactly one `Worker(task_queue="ai-sdlc")` is built with all ten workflows and every activity; the janitor starts; the printed line is exactly `worker running on task queue 'ai-sdlc'`.
  - **`all` + queue + cap 2 (G-3, G-4).** Two workers: the harness one is built **first**, with `max_concurrent_activities=2`, no workflows, the harness set and identity `harness@…`. The core one keeps everything, with identity `core@…`.
  - **`core` + queue.** One worker with the core activities only and no janitor.
  - **`harness` + queue.** One worker with no workflows, and the janitor starts.
  - **Refusals (G-2).** Every refuse row exits non-zero **before** `Client.connect` is called.
  (contracts/worker-boot.md G-1..G-5) **(M)**
- [ ] T009 [US2] Restructure `S/worker.py:main()` to make T008 green.
  - Compute `boot_plan_from_env()` first, before any connect. A refusal raises `SystemExit` with the message.
  - Keep the existing boot checks (`validate_registry`, `validate_crew_clis`, `graph_boot_problems`, `check_harness_versions`) in every mode.
  - Build the workers per the plan, using the `identity` format `f"{pool}@{socket.gethostname()}:{os.getpid()}"` for pool workers only. The single-pool `Worker(...)` call keeps today's arguments.
  - Run them with `asyncio.gather(*(w.run() for w in workers))`, harness first.
  - Start `worktree_janitor` only when `plan.janitor` is set.
  - Keep `S/worker.py` under 400 lines; move helpers into `S/pools.py` if needed.
  **(M)**
- [ ] T010 [US2] PROOF: write `T/test_pools_failfast.py::test_poller_freshness` (`-m temporal`, ephemeral dev-server) and implement `require_harness_poller(client, queue, *, freshness_s=90, timeout_s=5)` plus `HarnessQueueUnpolled` in `S/pools.py` (R6).
  - The call is `client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(namespace=client.namespace, task_queue=TaskQueue(name=queue), task_queue_type=TASK_QUEUE_TYPE_ACTIVITY))`, wrapped in `asyncio.wait_for(…, timeout_s)`.
  - **Assert:**
    - (a) with no worker it raises within 10 s, and the message names the queue and `KROKER_WORKER_POOL=harness`;
    - (b) after starting a harness-only `Worker` on the queue, it passes within 5 s (poll-wait ≤ 5 s);
    - (c) after shutting that worker down, it raises once `freshness_s` (set to 3 in the test) has elapsed.
  - Record the observed lag and linger in the test docstring. **If (b) or (c) cannot be made to hold, STOP and report: R6 is re-planned.**
  (plan C3, risk 1) **(M)**

---

## Phase 4: User Story 4 — operators can see pool health (P2)

**Goal**: the doctor reports the pool state.

**Independent test**: `uv run pytest -q tests/test_doctor_pools.py`.

- [ ] T011 [P] [US4] RED: write `T/test_doctor_pools.py`. `check_worker_pools(client_factory=…)` against stubs, one case per row of the contracts/worker-boot.md §Doctor table:
  - unset → PASS `single pool (ai-sdlc)`;
  - set, with a stub that returns one fresh poller → PASS naming the queue and the count;
  - set, with a stub that returns no or stale pollers → FAIL with the exact remedy text;
  - set, with a connect that times out → FAIL `routing on: cannot reach …`.

  The check never raises (SG-3). (P-FR-008) **(S)**
- [ ] T012 [US4] Implement `async def check_worker_pools(connect=None)` in `S/doctor/checks.py`, reusing `_TEMPORAL_TIMEOUT_S` and the `check_temporal` connect pattern (`S/doctor/checks.py:272-291`) and calling `require_harness_poller`. Add it to the doctor's row list next to `check_temporal` (locate the list by grepping `check_temporal` in `S/doctor/`). Update any test that pins the row count. Make T011 green. **(S)**

---

## Phase 5: User Story 3 (024-i half) — fleet enablers (P1)

**Goal**: same-second benchmark starts get distinct ids, and worktree hygiene holds under several processes.

**Independent test**: quickstart §1a (`test_bench_ids`, `test_janitor_lock`, `test_axis_prune`).

- [ ] T013 [P] [US3] RED: write `T/test_bench_ids.py`. Extract the id construction into a pure `bench_workflow_id(case_id, now=time.time)` in `S/benchmarks/cli.py`, and test it. 50 calls with a frozen `now` give 50 distinct ids, and each matches `^bench-<case_id>-<epoch>-[0-9a-f]{6}$`. (P-FR-009; R8; W-5) **(S)**
- [ ] T014 [US3] Implement `bench_workflow_id` in `S/benchmarks/cli.py` (`uuid.uuid4().hex[:6]`) and use it at `:338`. Make T013 green. **(S)**
- [ ] T015 [P] [US3] RED: write `T/test_janitor_lock.py`. With `_worktrees_root()` monkeypatched to a tmp dir, hold `fcntl.flock(<root>/.janitor.lock, LOCK_EX)` from a second open file. `sweep_once(...)` must then return without calling `cleanup_run_dir` (monkeypatched recorder) and log a skip. With the lock free, it sweeps as before. (R10) **(S)**
- [ ] T016 [US3] Add the non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` around `sweep_once`'s body in `S/vcs/janitor.py:34`. Create the lock file under `_worktrees_root()`, release it in `finally`, and on `BlockingIOError` log at INFO and return. Make T015 green. **(S)**
- [ ] T017 [P] [US3] RED then fix: write `T/test_axis_prune.py`. Run the worktree-creating path of `measure_code_axis` (`S/benchmarks/axis.py:198-236`; call its inner helper, or the activity with a tmp git repo and a stub measurement). Afterwards, `git worktree list --porcelain` in the repo shows only the main worktree. This is RED today. Then add `git worktree prune` (via the module's existing git runner) in the `finally` at `S/benchmarks/axis.py:235-236`. (R10, skeptic L3) **(S)**

---

## Phase 6: Deployment and docs (024-i)

- [ ] T018 Confirm the session-store paths in the runtime image. Read `Dockerfile` (the `HOME`/user of the `runtime` stage) and `S/harness/claude_code.py` and `S/harness/opencode.py`, and record the claude store dir and the opencode storage dir in this task's commit body. Then create `docker-compose.pools.yml` per contracts/worker-boot.md §Compose:
  - `worker` gets `KROKER_WORKER_POOL: core` and `KROKER_HARNESS_QUEUE: ${KROKER_HARNESS_QUEUE:-default}`.
  - `worker-harness` uses the same `image`/`build` as `worker`, with `KROKER_WORKER_POOL: harness`, the same queue and `KROKER_HARNESS_CAP: ${KROKER_HARNESS_CAP:-2}`.
  - Both mount `worker-worktrees`, `worker-repos` and `${KROKER_RUNS_BIND:-worker-runs}`. `worker-harness` also mounts the `harness-sessions` named volume at the two confirmed store **subpaths**, never their parent, so the `auth.json` `:ro` bind in `docker-compose.override.example.yml:17` is not shadowed (R9).
  - Declare `harness-sessions` under `volumes:`.

  Validate with `docker compose -f docker-compose.yml -f docker-compose.pools.yml config -q`, which must exit 0. `docker-compose.yml` itself is unchanged. (P-FR-010; quickstart §5) **(M)**
- [ ] T019 Write `docs/operations/worker-pools.md` (new; under 250 lines). Cover:
  - the three modes, the three env vars and the truth table, linking data-model.md rather than copying it;
  - the compose overlay command;
  - the cap, and that it is per process;
  - the janitor placement;
  - the doctor row;
  - the **Q3 sizing rule** (harness cap ≥ concurrent crew runs, or a crew `wall_clock_s` with headroom; the default is 5400 s, `crew/layouts/code.yaml:26`);
  - the **R9 boundary** (session resume is safe only when every harness replica mounts the same session-store volume on one host);
  - the **R1 rollback remedy** for the maintenance family;
  - the **R12 notes for R025**;
  - a top banner: `> 024-i: pools can boot; run-level routing lands in 024-ii (KROKER_HARNESS_QUEUE is not yet read by start paths).`

  Link it from the `docs/` index or the README operations section, wherever `docs/operations/` siblings are linked (grep). (P-FR-013 partial; GATE 1 Q2/Q3) **(S)**

## Phase 7: 024-i close-out

- [ ] T020 Run the 024-i battery:
  ```bash
  uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run python scripts/check_file_size.py
  ```
  - quickstart §1a;
  - `uv run pytest -q -m temporal tests/test_pools_failfast.py::test_poller_freshness`;
  - `uv run pytest -q tests/replay/`;
  - `git status --short tests/replay/` (empty);
  - `uv run pytest -q`, whose failures must be ⊆ `baseline-failures.txt`.

  Write `.specify/specs/024-two-worker-pools/verification.md` §024-i, with each command's result and the statement: "024-i does not unblock R025; NFR-2 stays open until 024-ii." Do **not** touch ROADMAP NFR-2. (plan F3) **(S)**

---

# Round 024-ii — routing on (requires 024-i merged)

## Phase 8: Foundational (024-ii)

- [ ] T021 Line-neutral extraction. Move `LONG_ACT_TIMEOUT_HOURS`, `LONG_ACT_HEARTBEAT_MINUTES`, `LONG_ACT`, `ACT` and `_long_act` (and only the constants they need) from `S/stages/code/step.py` (~lines 60–105; locate them by name) into a new `S/stages/code/acts.py`. Re-import them in `step.py` under the same names, and keep the re-exports any test imports from `step` (grep `T/` for `from sdlc.stages.code.step import`). No behaviour change: the fast tier is unchanged. Assert in the commit body that `wc -l src/sdlc/stages/code/step.py` ≤ 975. (plan G1; R3 ceiling) **(S)**
- [ ] T022 RED: add `test_inputs_omit_none` and `test_inputs_roundtrip_queue` to `T/test_pools.py`. For each of `PipelineConfig`, `TriageInput`, `AssessmentInput`, `TidyUpInput`, `DeploymentInput`, `CrewTaskInput`, `CaseSpec` and `MaintenanceConfig` (built from the minimal valid instances the existing tests use; grep their factories):
  - `"harness_queue" not in model_dump_json()` when it is unset;
  - `pydantic_data_converter.payload_converter.to_payloads([m])[0].data` has no `harness_queue` key;
  - with `harness_queue="q"`, it round-trips;
  - an invalid name is rejected;
  - a pre-024 payload, the JSON without the key, validates to `None`.
  (P-FR-005/011; R1; W-1) **(S)**
- [ ] T023 Add `harness_queue: str | None = Field(default=None, exclude_if=lambda v: v is None)`, plus a validator reusing `pools` name validation, to the 8 models. The locations are research R1's table: `S/core/models.py:369`, `S/workflows/triage.py:75`, `S/workflows/assessment.py:131`, `S/workflows/tidyup.py:77`, `S/workflows/deployment.py:66`, `S/workflows/crew.py:66`, `S/benchmarks/models.py:348` and `S/maintenance/models.py:84` (`extra="forbid"` stays). Make T022 green. Run `uv run pytest -q tests/replay/`, which must stay green. **(M)**

---

## Phase 9: User Story 1 — single-pool deployments unchanged (P1) 🎯

**Goal**: with routing off, commands, payloads and replay are identical (W-1). This is proven before any site is touched, and it stays pinned while the sites change.

**Independent test**: quickstart §1b (the AST walk) plus §3 (replay).

- [ ] T024 [US1] RED: write `T/test_pools_call_sites.py::test_harness_sites_routed`, the R4 static layer. `ast.parse` every `src/sdlc/**/*.py`, and for each call whose func is `workflow.execute_activity` or `workflow.start_activity`, resolve the first positional argument:
  - a `Name`: its activity name is the `@activity.defn(name=…)` or the function name;
  - a string `Constant`: itself.

  Then assert:
  - a harness name has a `**` keyword whose value is a `Call` to `pools.on_harness` (the module-qualified form; see T025);
  - a core name has neither a `task_queue=` keyword nor an `on_harness` splat;
  - no module assigns `workflow.execute_activity` to another name;
  - no `execute_local_activity` call names a harness activity.

  Print the offending `file:line`s. It is RED with the 33 sites of research R3 listed. (P-FR-002/005; R4) **(M)**
- [ ] T025 [P] [US1] RED: write `T/replay/test_pools_replay.py::test_forced_queue_replay`, R7(a). Force every harness queue to `"forced-q"`. T026/T027 call sites use the module-qualified form `**pools.on_harness(...)` (`from sdlc import pools`), so one `monkeypatch.setattr(sdlc.pools, "on_harness", …)` reaches them all. T024's AST check accepts `pools.on_harness` and requires that form (reviewer tasks-1 gap 2). Replay every history under `T/replay/histories/` with the replay harness's existing `Replayer` setup (`T/replay/harness.py`, `T/replay/test_graph_replay.py`), and assert `replay_failure is None`. Until T026–T028 land, no call site uses `on_harness`, so the patch is vacuous. Mark the test `xfail(strict=True, reason="vacuous until T028")` and assert inside it that at least one forced queue was applied; that assertion is what fails before T028. T028 removes the xfail. (SC-001; R7) **(S)**

---

## Phase 10: User Story 2 (024-ii half) — routing on, every harness activity on the harness pool (P1)

**Goal**: W-2, W-3 and W-4.

**Independent test**: quickstart §2 (`test_pools_routing`, `test_pools_failfast`).

- [ ] T026 [US2] Apply `**pools.on_harness(<opts>, <q>)` (module-qualified; see T025) at the graph-side and stage sites. The value of `q` is `cfg.harness_queue`; inline-keyword sites wrap them as `dict(...)`.
  - `S/stages/code/step.py:311, 711, 740, 745`
  - `S/workflows/task_host.py:196, 274`
  - `S/workflows/graph_nodes/precode.py:58`
  - `S/workflows/graph_nodes/postplan.py:124`
  - `S/workflows/graph.py:223`
  - `S/stages/qa/step.py:139`
  - `S/stages/merge/step.py:340, 350, 396, 414, 420, 681`

  Where a step function lacks `cfg`, find the nearest caller that holds it and thread `harness_queue` through as a keyword argument. Record each such signature change in the commit body. (R3) **(M)**
- [ ] T027 [US2] Apply `**pools.on_harness(...)` (module-qualified) at the child-workflow sites:
  - `S/workflows/crew.py:149, 175, 322, 359, 367, 385`, with `q = inp.harness_queue`;
  - `S/workflows/deployment.py:119, 141, 151` (`inp.harness_queue`);
  - `S/workflows/triage.py:194` (`inp.harness_queue`);
  - `S/workflows/tidyup.py:321` (`inp.harness_queue`);
  - `S/workflows/maintenance_execute.py:346, 475, 536` (the state's `cfg.harness_queue`; thread it as an argument per that module's explicit-argument rule in `S/workflows/AGENTS.md`);
  - `S/benchmarks/workflow.py:396, 472, 501` (`spec.harness_queue`).

  (R3) **(M)**
- [ ] T028 [US2] Add the child copies at the 11 inheritance sites (data-model §Inheritance):
  - `S/benchmarks/workflow.py:_cell_config` (`:90`);
  - `S/workflows/tidyup.py:194, 204, 229`;
  - `S/workflows/assessment.py:371`;
  - `S/workflows/maintenance.py:189`;
  - `S/workflows/maintenance_execute.py:260, 491, 505`;
  - `S/stages/code/step.py:280` (`CrewTaskInput(…, harness_queue=cfg.harness_queue)`);
  - `S/stages/deploy/step.py:138`.

  Then T024 must be green, so remove T025's xfail: T025 must pass. Run `uv run pytest -q tests/replay/`, which must stay green. (P-FR-006) **(M)**
- [ ] T029 [US2] RED: add `test_start_paths_resolve` to `T/test_pools_call_sites.py`. Every `.start_workflow(` and `.create_schedule(` call in `S/` outside `@workflow.defn` classes must sit in a function that calls `resolve_harness_queue`, or in one whose callee does (`start_graph_run`). The allowlist is `S/demo/run.py`, with a reason comment. The test lists the expected sites:
  - `S/graph/start.py:59`;
  - `S/cli.py` (the 3 direct sites);
  - `S/benchmarks/cli.py`;
  - `S/maintenance/cli.py`;
  - `S/schedules/apply.py`.

  (P-FR-007; R6) **(S)**
- [ ] T030 [US2] Wire the start paths (R6; W-3, W-4) to make T029 green. Each path calls `q = resolve_harness_queue()`, then, if `q`, `await require_harness_poller(client, q)`, and sets `harness_queue=q` on the root input.
  - `S/graph/start.py:start_graph_run` sets it on `run_input.cfg`.
  - `S/cli.py:793, 839, 889`.
  - `S/benchmarks/cli.py:336` sets it on `spec`.
  - `S/maintenance/cli.py:252` sets it on the config.
  - `S/schedules/apply.py:62` checks at apply time and bakes `q` into the action's input.

  The CLI catches `HarnessQueueUnpolled`, prints its message to stderr and exits 2. Keep `S/cli.py` ≤ 975 lines. **(M)**
- [ ] T031 [US2] RED → green: write `T/test_pools_failfast.py::test_start_paths_refuse` (`-m temporal`). With `KROKER_HARNESS_QUEUE=failfast-q` and no harness worker, invoke each start path's function directly:
  - `start_graph_run`;
  - the triage/tidy-up/assessment CLI coroutines;
  - the benchmark start;
  - the maintenance enable;
  - the schedules apply.

  Each must raise `HarnessQueueUnpolled` within 10 s (`asyncio.wait_for`), and afterwards `client.list_workflows()` returns none and no schedule exists. With the env unset, the same calls proceed as before; stub the workflow so it completes immediately. (SC-005; US2-AS4) **(M)**
- [ ] T032 [US2] Write `T/test_pools_routing.py` (`-m temporal`), the R4 dynamic layer and SC-002. Use a test-only `temporalio.worker.Interceptor` whose `WorkflowOutboundInterceptor.start_activity` records `(input.activity, input.task_queue)`. Run two `Worker`s on one ephemeral server:
  - core: `ai-sdlc-test`, all workflows plus the core activities, identity `core@test`;
  - harness: `pools-q`, the harness activities, identity `harness@test`.

  Register the repo fakes (`S/demo/fakes.py` and `T/replay/scenarios.py` stubs) under their real names. Drive:
  - (a) a greenfield GraphWorkflow through code with a crew task and a deploy;
  - (b) a one-cell BenchmarkWorkflow;
  - (c) TriageWorkflow, TidyUpWorkflow and AssessmentWorkflow on the `T/maintenance/conftest.py` fixture repo;
  - (d) a MaintenanceWorkflow execute path, reusing 023b's stub child;
  - (e) ReflectWorkflow.

  Assert:
  - routing on: every recorded harness name has `task_queue == "pools-q"`, and every core name has `None`;
  - from history, every harness `ActivityTaskStarted` has identity `harness@test`, and every other has `core@test`;
  - routing off, re-run (a) and (b): every recorded `task_queue is None`.

  Scenarios that cannot be driven on fakes are listed in the test docstring, with the AST layer named as their coverage. If this task overruns one sitting, split (a)–(e) in-round into T032a–T032e, one per driver, so no hidden L (reviewer tasks-1 gap 5). (SC-002; W-2; P-FR-006) **(M)**

---

## Phase 11: User Story 3 (024-ii half) — five concurrent benchmark runs (P1)

**Goal**: SC-003 and SC-004 on a barrier fake (R11).

**Independent test**: `uv run pytest -q -m temporal tests/test_pools_fleet.py`.

- [ ] T033 [US3] Write `T/test_pools_fleet.py` (`-m temporal`).
  - **Barrier fake.** Define `@activity.defn(name="run_coding_task")` in the test. It increments a shared in-flight counter, records the peak, awaits an `asyncio.Event` that the test releases after ≥ 1.0 s, and returns the `S/demo/fakes.py` result shape. Register it on the harness `Worker` only, with `max_concurrent_activities=2` and the identity asserted.
  - **The run.** Start 5 `BenchmarkWorkflow`s via `bench_workflow_id` within one second, 2 of them on the same case. Use a one-cell spec over the demo fakes.
  - **During the hold.** Schedule a core model-call activity (the fake agent request) and record its schedule-to-start from history.
  - **Assert:**
    - all 5 complete;
    - peak in-flight ≤ 2;
    - at least one harness activity's (started − scheduled) ≥ 0.5 s;
    - the core p95 schedule-to-start < 1.0 s;
    - every benchmark record's key set equals a solo run's.
  (SC-003, SC-004; US3 AS1–3) **(M)**

---

## Phase 12: Replay and the routing-on capture (SC-006)

- [ ] T034 Write `T/replay/test_pools_replay.py::test_routing_on_projection`, R7(b). In-test, run the `greenfield_happy` scenario from `T/replay/scenarios.py` on two `Worker`s with `harness_queue="replay-q"`, using the capture harness's setup without writing files. Fetch the history, replay it with `Replayer`, and assert `command_projection(history)` equals the projection in `T/replay/golden/greenfield_happy.json`. Assert `git status --short tests/replay/histories tests/replay/golden` is empty. (SC-006; P-FR-011) **(M)**

---

## Phase 13: Docs and close-out (024-ii)

- [ ] T035 [P] Update `ARCHITECTURE.md` §9. Replace the "Status: the split above is designed, not built" note with: two queues built (E-91, 024); `ai-sdlc` core plus `KROKER_HARNESS_QUEUE` harness; routing off by default; the five-pool target still plan (AP-2.5b, needs AP-2.1); worker-specific queues still AP-2.6. Link `docs/operations/worker-pools.md`. (P-FR-013) **(S)**
- [ ] T036 [P] In `docs/adr.md`, change ADR-9's status line to "two capability queues built 2026-11-xx (E-91); the five-pool amendment stays plan (AP-2.5b)". (P-FR-013) **(S)**
- [ ] T037 [P] In `docs/roadmap/agent-architecture-plan.md:41`, split AP-2.5 into `[x] AP-2.5a` (two capability queues and pools, E-91) and `[ ] AP-2.5b` (per-role routing from `RoleSpec`, depends on AP-2.1). (GATE 1 Q1/Q4) **(S)**
- [ ] T038 [P] In `docs/roadmap/crew.md:69-71`, reword the session-resume boundary per R9. Resume across harness workers is safe on one host when every harness replica mounts the same session-store volume (`docker-compose.pools.yml`). It is not safe across hosts. Worker-Specific Task Queues remain AP-2.6. (GATE 1 Q2) **(S)**
- [ ] T039 PROOF (re-run): run `uv run pytest -q -m temporal tests/test_pools_failfast.py tests/test_pools_routing.py tests/test_pools_fleet.py` and `uv run pytest -q tests/replay/`. Any red here is a STOP, not a fix-forward. (quickstart §2–§3) **(S)**
- [ ] T040 Update `ROADMAP.md`:
  - NFR-2 (`:462`) becomes `[x]` "two capability pools (E-91); five-pool form AP-2.5b";
  - the ADR-9 row (`:527`);
  - §8 item 1 (`:569`): the next step is R025 fleet runs;
  - the `Last verified` cell gets one sentence, and the full entry is prepended to `docs/roadmap/last-verified-log.md` per the AGENTS.md rule.

  Remove the 024-i banner from `docs/operations/worker-pools.md`. (P-FR-013) **(S)**
- [ ] T041 Run the full battery (quickstart §4):
  ```bash
  uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run python scripts/check_file_size.py
  uv run pytest -q
  uv run pytest -q -m temporal
  ```
  - The fast tier must be ⊆ the baseline, and the temporal tier must show no new failures.
  - Also run quickstart §1a, §1b and §5 (`docker compose … config -q`).
  - Then run `git diff --stat <024-i merge base>..HEAD -- 'src/sdlc/stages/*/*.md' src/sdlc/graph/node_types.py src/sdlc/workflows/gates.py $(grep -ril containment src/sdlc --include=*.py -l | grep -v pools.py)`, which must be empty apart from the documented `**pools.on_harness` splats (P-FR-012). List any hit in verification.md with its reason (reviewer tasks-1 gap 4).
  **(S)**
- [ ] T042 Write `verification.md` §024-ii:
  - the SC-001..SC-007 table, with command and result;
  - the P-FR-012 diff evidence;
  - the residuals: R6's no schedule-fire pre-flight; R1's maintenance rollback asymmetry; R12's notes deferred to R025; a harness worker dying with no fresh replacement leaves activities queued (the F1 semantics);
  - the `check_test_drift` fix.
  (plan J2) **(S)**

---

## Dependencies & execution order

**024-i:**
- T001 → T002 → T003 → T004 → T005.
- Then US2: T006 → T007 → T008 → T009 → T010.
- T011 and US3 (T013–T017) can run after T003, in parallel with US2. **T012 runs after T010**, because it calls `require_harness_poller` (reviewer tasks-1 gap 1).
- T018–T019 after T009.
- T020 last.

**024-ii (after 024-i is merged):**
- T021 → T022 → T023 → T024 (RED) ∥ T025 (xfail).
- Then T026 → T027 → T028 (T024 green; T025 un-xfailed).
- Then T029 → T030 → T031.
- T032 after T028 and T030.
- T033 after T030.
- T034 after T028.
- T035–T038 ∥ at any point after T030.
- Then T039 → T040 → T041 → T042.

### Shared-file sequencing

- `S/pools.py` is touched by T003, T007 and T010. They are sequential.
- `S/worker.py` is touched by T005, T007 and T009. They are sequential.
- `S/stages/code/step.py` is touched by T021, T026 and T028. They are sequential, and T021 comes first because of the ceiling.
- `S/workflows/tidyup.py`, `maintenance_execute.py` and `benchmarks/workflow.py` are touched by both T027 and T028, so T028 follows T027.
- `T/test_pools.py` is touched by T002 and T022, and `T/test_pools_call_sites.py` by T024 and T029, in separate rounds or in sequence.
- `T/test_pools_failfast.py` gets T010's test in 024-i and T031's in 024-ii.

## Parallel opportunities

- 024-i: T011, T013, T015 and T017 are all different files, [P] after T003.
- 024-ii: T025 ∥ T024, and T035–T038 are docs in four files.

## Implementation strategy

- **024-i** is an ops-only increment: the harness worker boots, the doctor sees it, ids are fleet-safe, and the janitor is safe. Nothing a workflow schedules changes.
- **024-ii** first pins US1 (byte-identity guards), then turns routing on (US2), then proves the fleet (US3).
- The MVP for R025 is the end of 024-ii (T033 green).

## Size summary

| Round | Tasks | S | M |
|---|---|---|---|
| 024-i | T001–T020 (20) | 16 | 4 |
| 024-ii | T021–T042 (22) | 12 | 10 |
| **Total** | **42** | **28** | **14** |
