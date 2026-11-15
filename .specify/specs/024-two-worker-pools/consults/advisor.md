# Advisor consult — round 024

Scope read: spec.md (GATE 1 rulings binding), worker.py, task_queue.py, stages/code/step.py, workflows/crew.py, benchmarks/{cli,workflow,drift}.py, pipeline_child.py, graph/start.py, tests/replay/projection.py, plus the call sites, stage `ACTIVITIES` lists and the installed temporalio source where cited. Nothing was edited except this file.

Two findings the spec does not state, since they shape several answers:

- **Many roots have no `PipelineConfig`.** `TriageInput` (`workflows/triage.py:75`), `AssessmentInput` (`workflows/assessment.py:131`), `MaintenanceKickInput`/`MaintenanceState` (`maintenance/models.py:169,350`) and `CaseSpec` (`benchmarks/models.py:348`) carry none. A `PipelineConfig` field alone does not reach their harness-class activities. `TidyUpInput` carries `fix_cfg`, and `DeploymentInput` carries a `DeployConfig`, not a `PipelineConfig`.
- **The harness class is wider than the spec's list.** The stage `ACTIVITIES` lists hold repo-executing activities the spec never names (see D2): `qa.run_test_suite`/`run_lint`/`scoped_security_scan` (`stages/qa/activities.py:692`), `merge.measure_coverage`/`run_integration_checks`/`open_pull_request` (`stages/merge/activities.py:251`) and `deploy_apply`/`deploy_rollback`/`smoke_check` (`stages/deploy/activities.py:253`).

---

## D1 — Where the routing value lives, and how it reaches every child

**Pick: an explicit `harness_queue: str | None = None` field on each root input, and nowhere else.** `PipelineConfig` gets one. The roots without a cfg get the same-named field: `TriageInput`, `AssessmentInput`, `TidyUpInput`, `CaseSpec`, the maintenance config/state, `DeploymentInput` and `CrewTaskInput`. Do not build a separate envelope type.

Why:

- **`PipelineConfig` already reaches the graph hosts.** `GraphRunInput.cfg` (`workflows/models.py:98`) is stashed as `self._cfg` (`workflows/graph.py:172`), and `task_host._dev_task` already receives `cfg` (`task_host.py:257`). Every graph-side harness site (`create_worktree` at `task_host.py:274`, `merge_into_integration` at `:196`, `setup_integration_branch` at `precode.py:58`, `get_task_diff` at `postplan.py:124` and `step.py:745`, `cleanup_run_worktrees` at `graph.py:223`, `run_coding_task` at `step.py:311`) can read `cfg.harness_queue` with no signature change.
- **Children inherit by copying one value at each start site.** Every child start already copies a cfg or input, so inheritance is one extra field copy per site. There are about 8 sites:
  - `pipeline_child.py:52` and `:78`: `run_input` is built from `cfg`, so the cfg's field rides along for free.
  - `benchmarks/workflow.py:373`: the cell cfg comes from `_cell_config` (`:90`), which deep-copies a base cfg. Set `cfg.harness_queue = spec.harness_queue` there.
  - `tidyup.py:194,204,229`: `fix_cfg` is a `default_factory`, so it needs `fix_cfg.model_copy(update=...)`.
  - `assessment.py:371`, `maintenance.py:189`, `maintenance_execute.py:491,505` (triage children): pass it into `TriageInput`.
  - `stages/code/step.py:280` (crew): build `CrewTaskInput` with one more field. The crew child is "built from cfg fields, not cfg", as the brief says, so the new field is one line there.
  - `stages/deploy/step.py:138`: `DeploymentInput(...)` gets one more field.
- **Alternatives:**
  - *Workflow memo.* It is ambient, so it would need no call-site threading. I reject it. P-FR-005 says "carried in workflow input". `continue_as_new` only carries memo if the command sets it (`_workflow_instance.py:3659-3685`), and the maintenance loop does `continue_as_new` (`maintenance/models.py:350`). The ambient read is also invisible to grep.
  - *Interceptor plus headers.* It would remove every call-site edit. I reject it for a spec-literal round. It needs a client interceptor, an outbound child and CAN interceptor and a replayer configured identically. It also needs the schedule action to carry headers. The interceptor is the fallback if D3's call-site count balloons.
- **The queue name travels, not a boolean.** It is resolved once at start, so a later env change cannot affect a run.
- **Serialisation:** the routing-off payload gains `"harness_queue": null`. Replays read the recorded input and fill the default, so nothing changes. Check that nothing hashes `PipelineConfig`'s dump: my grep for cfg hashing and fingerprinting found no hit, but the plan should re-confirm for memoization keys and benchmark config ids. Also check whether `PipelineConfig` or the other inputs forbid extras: a rollback to a pre-024 worker would then fail to load routing-on inputs. Document that routing-on runs cannot be replayed by a pre-024 worker.

**Risk:** a root input is missed, so its children silently route off and run on core. The D3 test catches it.

## D2 — The harness-class boundary

**Pick: amend rule A.1(c).** The class is every activity that (a) spawns a harness CLI, (b) executes target-repo code, (c) writes a repo, worktree or branch, **or reads state a harness-class activity writes**. That means a run's worktree, or its integration and verification branches. Read-only access to the canonical checkout, or to immutable content by sha, is core.

Why: single-host with a shared filesystem is only an assumption (spec Assumptions). The state a worktree writer produces should be read by the process that owns that volume. Otherwise AP-2.6 and multi-host later have to reclassify the read-only git activities. This is one sentence now and keeps the classification stable.

Proposed table. Items marked **VERIFY** are ones I could not settle from the signatures.

| Activity | Class | Reason |
|---|---|---|
| `run_coding_task`, `run_crew_turn` | harness | (a) |
| `create_worktree`, `merge_into_integration`, `setup_integration_branch`, `build_verification_branch`, `prepare_base_worktree`, `remove_verification_tree`, `cleanup_run_worktrees`, `prepare_crew`, `checkpoint_round` | harness | (c) writes |
| `read_round`, `get_task_diff`, `read_committed_bytes`, `is_ancestor` | harness | reads of run worktrees and branches |
| `grade_oracle`, `triage_build_probe`, `qa.run_test_suite`, `qa.run_lint`, `merge.measure_coverage`, `merge.run_integration_checks`, `deploy_apply`, `deploy_rollback`, `smoke_check` | harness | (b) executes repo code |
| `scoped_security_scan`, `measure_code_axis`, `open_pull_request` | harness (**VERIFY**) | reads the run worktree or the pushed branch; `open_pull_request` also touches a remote |
| `paths_exist` | **core** | `clarify/step.py:149` passes `repo_path` (the canonical checkout), read-only |
| `assessment_resolve_tree`, `triage_resolve_commit`, `triage_baseline/secrets/dependencies/misconfig/outliers/scaffold`, `scan_*`, `verify_*_refs`, `discover_*` | core | by-sha `git rev-parse` or blob reads (`assessment/activities.py:130`, `triage/activities.py:113`) |
| `load_crew`, `load_drift_globs`, `classify_repo`, `check_brownfield_delta` | core | config or canonical-tree reads (**VERIFY** the last two: they may read a live tree) |
| `probe_repair_child` | core | a client call; it starts and reads a workflow, no repo access |
| `check_test_drift` | **VERIFY** | it sits in `vcs.ACTIVITIES` (`vcs/__init__.py:48`) but not in `get_worker_activities()`, so check whether it is ever an activity |
| janitor task (`worker.py:313`) | **harness and `all`; not `core`** | `sweep_once` removes worktree dirs (`vcs/janitor.py:73`); it is idempotent, so two harness workers are fine |

One behaviour to note: `triage_*` read the target tree by sha from `repo_dir`. Triage is run-independent, so core can serve it. `triage_build_probe` is the only execution there.

**Single authority:** a leaf module `src/sdlc/pools.py` holds `HARNESS_ACTIVITIES: frozenset[str]` (names, so importing it costs nothing, like `task_queue.py`). `drift.CODING_ACTIVITIES` becomes a subset assertion in a test, not an import. The classification test (P-FR-002) checks `registered == core ∪ harness`, `core ∩ harness = ∅`, and that every name in `HARNESS_ACTIVITIES` is registered.

**Risk:** a mis-classified read-only activity on core that touches a harness-only volume. This only bites on multi-host, which is out of scope. The reverse mistake costs a harness slot. Prefer harness when unsure.

## D3 — Call-site mechanism and the no-missed-site guarantee

**Pick: one pure helper in `pools.py`, spliced at every harness-class site.**

```python
def on_harness(opts, queue):   # opts: ActivityConfig mapping, queue: str | None
    return opts if not queue else {**opts, "task_queue": queue}
```

Call sites change from `**ACT` to `**on_harness(ACT, cfg.harness_queue)`. With routing off it returns the same dict, so no `task_queue` key reaches the SDK. The SDK then does `input.task_queue or info.task_queue` (`_workflow_instance.py:3311`), so the command is the same as today. Sites that pass `args=`, `start_to_close_timeout=` and so on inline (`clarify/step.py:149`, `graph.py:223`) become `**on_harness(dict(...), q)`.

Two details:

- **`stages/code/step.py` is at 998 lines, and SC-007 forbids growth past 1000.** Make the helper edits line-neutral, for example by editing `_long_act` in place, or extract a line or two elsewhere. Budget two lines for the `CrewTaskInput` field. Do the same check for other files near the ceiling.
- **Local activities:** `execute_local_activity` takes no `task_queue`. If any harness-class activity is called locally, that is a silent routing hole. Grep showed no such call, so assert it in the test.

**Guarantee, in two layers:**

1. **A static AST test.** Walk `src/sdlc` for `execute_activity(<Name>, ...)`. Resolve each first argument to its activity name. If it is in `HARNESS_ACTIVITIES`, require that the call has a `**on_harness(...)` splat; if it is core, require that it has no `task_queue`. This fails the build when someone adds a harness site without routing, or classifies a name wrong.
2. **A dynamic oracle in the temporal tier.** Use a test `Worker` outbound interceptor on `start_activity` (it is a recorder, not production code). Run with routing on and assert `input.task_queue` is the harness queue iff the activity is in the harness set. Run it across a pipeline, a crew turn, a benchmark cell, triage, assessment, tidy-up and maintenance. The same recorder, run with routing off, asserts no activity has an explicit queue. This also covers SC-002 and the golden-history comparison.

**Rejected:** the production interceptor that stamps the queue by activity name. It would remove the miss class entirely, but it hides the routing and needs header propagation for children and schedules. See D1.

**Risk:** the dynamic test only exercises paths the fakes reach. The AST layer covers the rest, and the AST layer's weakness is aliasing (`act = workflow.execute_activity`). Grep shows none, so assert that there are none.

## D4 — Fail-fast "no harness poller" check

**Pick: a leaf `pools.require_harness_poller(client, queue)`, called at every client start site with `queue=cfg/spec.harness_queue`, raising a typed error that names the queue.**

API: `client.workflow_service.describe_task_queue(DescribeTaskQueueRequest(namespace=..., task_queue=TaskQueue(name=q), task_queue_type=TASK_QUEUE_TYPE_ACTIVITY))`, which is in the SDK's `workflowservice/v1`. Pass if `pollers` is non-empty and any `last_access_time` is within about 90 s. The server lists a poller for roughly five minutes after it stops, so the freshness check matters and the plan should confirm the retention figure against the server in use (the temporal tier will show it). Query the **activity** type: the harness worker registers no workflows, so a workflow-type query would always report no pollers. Also make the call with a short timeout (SC-005 wants refusal within 10 s).

Where to call it. Start paths found:

- `cli.py:581` (run, through `start_graph_run`), `:793` (triage), `:839`, `:889`
- `benchmarks/cli.py:336`
- `maintenance/cli.py:252`
- `operator/runtime.py:76` (through `start_graph_run`)
- MCP (a client; it reaches the operator path)
- `schedules/apply.py:62`

Put one call in `graph/start.py:start_graph_run` before `client.start_workflow` (it already takes duck-typed `client`; no new imports there beyond `pools`), and one explicit call at each direct `client.start_workflow` site. A grep-based test (every `.start_workflow(` in `src` sits in a function that also calls `require_harness_poller`, or is on an allowlist) keeps new start paths honest.

**Schedules:** they start the workflow later, server-side, so a start-time check cannot run. Do three things:

1. Check at `schedules apply` time and refuse. Bake the resolved queue into the schedule's action input (`apply.py:to_temporal`), not an env read at fire time, so a schedule's routing is fixed when it is applied.
2. Add the doctor check (P-FR-008).
3. Add a routing-on-only core pre-flight activity at the top of `MaintenanceKickWorkflow`, the one root that is only ever started server-side. It runs `require_harness_poller` and fails non-retryably. It issues a command only when routing is on, so it needs no patch marker.

The residual gap: a harness worker that dies after a schedule fire leaves that run's harness activity scheduled but not started, with no timeout. That is the intended F1 semantics. The doctor and the Temporal UI show it, so it is a known operating mode, not a hang defect.

**Risk:** the server's poller list is eventually consistent, so a worker booted in the last few seconds may not appear yet. Tests should poll-wait before starting. A short race for a human operator is acceptable.

## D5 — Should `all` also poll the harness queue

**Pick: yes. In `all`, boot a second `Worker` for the harness queue in the same process and run both with `asyncio.gather`.** It is created only when a harness queue name is configured, so with nothing configured `all` is today's single worker byte for byte.

- The core `Worker` in `all` still registers **every** activity and every workflow, as today. A routing-off run, or a run in flight from before 024, keeps working against it. The harness `Worker` registers only the harness set, on the harness queue. Activities may be registered on both, so there is no placement ambiguity (the queue decides).
- **Cap semantics:** `max_concurrent_activities=cap` applies to the harness `Worker` object only. The core `Worker` stays uncapped as today. So in `all`, with routing off, harness-class work is still uncapped on core; document it. A cap below 1 refuses boot in every mode (P-FR-004), and a cap set with no harness queue is a boot error in `all` (it would have no effect).
- **`core` mode:** refuse to boot unless a harness queue is configured. A core-only worker with no harness queue name would leave every in-flight routing-off run without any activity worker for harness-class work. If an operator really wants that, they can run `all`. This also makes a missing env var loud.
- **`harness` mode:** registers no workflows and only the harness set; it validates crew CLIs and harness versions (`worker.py:273,279`). It skips the registry and graph boot checks only if they are pure workflow-side (the plan should decide; keeping them is the safer default). The janitor runs in `harness` and `all`, not `core`.
- **Tests and small hosts:** this is what lets the temporal-tier test and a laptop run routing on in one process. The two-process test (SC-002's per-worker identity assertion) still needs two `Worker` objects with distinct `identity=`, which the same helper builds.

**Risk:** one process holds two pollers over one gRPC client. That is supported. The remaining risk is boot ordering: start the harness `Worker` before the core `Worker` so a routing-on run never sees core up first.

## D6 — Replay

**Does the SDK's replay check compare an activity's task queue? I am not certain.** What I can establish:

- The Python SDK side only sets `command.schedule_activity.task_queue = input.task_queue or info.task_queue` (`_workflow_instance.py:3311`). It does no queue comparison of its own.
- Matching a command to a history event happens in the Rust core bridge, which I cannot read here. My recollection is that it matches on activity id and type, not queue. Treat that as unverified.

**Cheapest proof, in the replay tier:** take the existing graph and benchmark golden histories (those that contain a code stage) and replay them through `Replayer` with a test patch that forces every harness-class activity to `task_queue="x"` (patch `pools.on_harness`'s routing in the test, or monkeypatch `cfg.harness_queue` through the input). If no `NondeterminismError` is raised, the SDK ignores the queue. It is a one-file test using `tests/replay/harness.py`.

**Does routing-on need `workflow.patched()`? No, whichever way that proof comes out.** The value is a pure function of the recorded workflow input, so replaying any history always recomputes the queue it recorded. A routing-on run's history can only exist after 024, so there is no old history that routing-on code could mis-replay. A pre-024 history has no field and routes off, which matches it. Routing never changes after start (spec edge case 2). The only new risk is the one the proof covers: if a determinism check did compare queues, the *first* 024 routing-on capture would still replay, since code and history agree.

So the SC-006 two-pool capture is the real test: capture once with routing on, then replay it and compare its command projection with the single-pool projection (`tests/replay/projection.py:24-40` records activity type only, so equality is expected). The routing-on-only pre-flight activity in D4 adds one extra command in `MaintenanceKickWorkflow`'s projection. Either exclude that workflow from the equality check or filter that one activity type in the comparison.

**Risk:** low. The failure mode is a mismatched replay of a routing-on history by a worker whose code lacks the helper (a rollback), which is the same rollback caveat as D1.

## D7 — Sizing

**Pick: take the pre-authorized 024-i / 024-ii split, but draw the line slightly differently from Part A.4.**

Count of the work: about 35 harness call sites in about 15 files, 8 root inputs, 8 child-start copies, the worker pool modes with two `Worker` objects, the cap, the janitor placement, 6 start-path guards plus the schedule path, doctor, compose, the F2 id fix, the classification and AST tests, a captured routing-on replay, and a fleet load test. Several touched files sit at the ceiling (`stages/code/step.py` at 998). Two different review surfaces are involved: boot and operations, and workflow determinism. The second needs the replay proof from D6 before anything lands.

- **024-i (boot and ops; routing hard-off):** `pools.py` with the class registry and the classification test (it is also the base for 024-ii), worker pool modes including the `all` dual worker, the cap, the janitor placement, `require_harness_poller` and the doctor check, compose, and the F2 id fix (`benchmarks/cli.py:338`, which is independent and cheap). Shippable alone: the harness worker boots and the system is unchanged.
- **024-ii (routing on):** the root input fields, the call-site helper and its AST and dynamic tests, the child copies, the start-path guards, the schedule path and the pre-flight, the replay proof and capture, and the SC-003/004 load test.

This moves the poller check function and the doctor into 024-i (they need no routing), so 024-ii is purely workflow-side. The one cost is that 024-i's value is operational only. R025 is unblocked only after 024-ii, so do not let the first round's merge be mistaken for the capability landing.

---

## Summary of picks

| | Pick | Main risk |
|---|---|---|
| D1 | `harness_queue` field on every root input; children copy it | a root input missed (caught by D3 tests) |
| D2 | class = (a) CLI, (b) executes repo code, (c) writes or reads run worktrees/branches; table above | `check_test_drift`, `scoped_security_scan`, `measure_code_axis`, `classify_repo` need verifying |
| D3 | `on_harness(opts, queue)` at each site; AST test plus interceptor oracle | `step.py` line ceiling; aliasing and local-activity holes |
| D4 | `pools.require_harness_poller` via activity-type `DescribeTaskQueue`; apply-time and pre-flight for schedules | poller-list lag and the 5-minute retention |
| D5 | yes: `all` runs two `Worker`s; cap on the harness one only; `core` needs a queue configured | boot ordering |
| D6 | no `patched()`; prove with a forced-queue replay of existing goldens | low; rollback caveat |
| D7 | split 024-i / 024-ii, cut as above | 024-i alone does not unblock R025 |
