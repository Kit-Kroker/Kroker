# Skeptic Review — `020-delete-featureworkflow` (L1–L7 Pressure-Test)

## L1 — `Q1=A`: Closed `FeatureWorkflow` runs listed from visibility metadata only; no `run_summary` / `run_state` query sent (`src/sdlc/dashboard/fleet.py`)

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario A — Completed legacy runs render as FAILED (`red`) in the dashboard UI, or crash `RunSummary` validation:**
  1. `FleetSnapshot.closed` (`src/sdlc/dashboard/fleet.py:76`) is typed as `list[RunSummary]`. `RunSummary` (`src/sdlc/core/models.py:485-516`) requires non-null `run_id: str`, `mode: str`, `outcome: str`, `terminal_stage: str`, `started_at: datetime`, `ended_at: datetime`, and `duration_s: float`.
  2. Currently, `_scan_closed` (`src/sdlc/dashboard/fleet.py:116-122`) extracts **only** `(wf.id, getattr(wf, "workflow_type", None))` and discards `wf.status`, `wf.start_time`, and `wf.close_time`.
  3. On the frontend, `mapClosed` (`interfaces/dashboard/frontend/src/api/http.ts:106-140`) computes `status: closedStatus(s.outcome)` (`http.ts:36-45`), which strictly checks:
     ```ts
     const done = outcome.startsWith('deployed:') || outcome.startsWith('merged-not-deployed:');
     return done ? 'done' : 'failed';
     ```
     and maps `mode: s.mode` into `Run.mode` (`ProjectMode = 'brownfield' | 'greenfield'`, `interfaces/dashboard/frontend/src/api/types.ts:13,38`).
  4. **Wrong outcome:** If `fleet.py` synthesizes a visibility-only `RunSummary` for a closed `FeatureWorkflow` with `outcome="completed"` or `outcome="legacy"` (anything not starting with `deployed:` or `merged-not-deployed:`), **every `COMPLETED` pre-cutover `FeatureWorkflow` run renders as `'failed'` in the dashboard**. Worse, if `wf.start_time` or `wf.close_time` is `None` (which happens on fake `SimpleNamespace` objects in `tests/test_dashboard_fleet_marks.py:63`), `RunSummary(...)` raises `pydantic.ValidationError` and crashes the entire `fetch_fleet` cycle (`src/sdlc/dashboard/fleet.py:164-204`).
- **Scenario B — Branching on `t != "GraphWorkflow"` instead of `t == "FeatureWorkflow"` breaks existing fleet tests:**
  1. In `tests/test_dashboard_fleet.py:82`, `_Client.list_workflows` yields `SimpleNamespace(id=run_id)` where `getattr(wf, "workflow_type", None)` is `None`.
  2. **Wrong outcome:** If `fetch_fleet` (`src/sdlc/dashboard/fleet.py:173-189`) skips `_fetch_closed` whenever `t != "GraphWorkflow"` instead of specifically `t == "FeatureWorkflow"`, `_fetch_closed` is never called when `t is None`, breaking `test_closed_runs_are_rendered_from_run_summary`, `test_a_closed_run_whose_summary_is_none_is_skipped_not_errored`, and `test_a_closed_run_query_failure_stays_out_of_open_errors` (`tests/test_dashboard_fleet.py:160-209`).
- **Scenario C — Unhandled Temporal query errors on write/CLI/operator routes when given a closed `FeatureWorkflow` run ID:**
  1. `POST /api/runs/{run_id}/answer` and `POST /api/runs/{run_id}/decide` (`src/sdlc/dashboard/api.py:116-132, 188-208`) and operator tools `_reply` (`src/sdlc/operator/tools.py:465-475`) call `resolve_key(handle, key)` -> `fetch_pending(handle)` (`src/sdlc/channels/transport.py:129-131, 156-167`), which unconditionally executes `await handle.query("pending_decisions")` (`transport.py:166`).
  2. Similarly, `sdlc status --id <id>` (`src/sdlc/cli.py:875-877`) executes `await handle.query(GraphWorkflow.status)`, and `sdlc approve/reject/revise/answer --id <id>` (`src/sdlc/cli.py:859-868`) executes `resolve(handle, selector)` -> `await handle.query("pending_decisions")`.
  3. **Wrong outcome:** Once `FeatureWorkflow` is unregistered from the worker (`src/sdlc/worker.py:216`), any query to a closed `FeatureWorkflow` handle fails on the worker with `WorkflowType FeatureWorkflow is not registered` (`WorkflowQueryFailedError` / `RPCError`). `api.py:119,191` has no `try/except` around `resolve_key`, returning an unhandled **HTTP 500** instead of `404`/`409`, and `cli.py:863,877` crashes with a raw traceback.

### 2. Likelihood
**Certain (100%)** for Scenarios A and B if not specified in the plan; **Medium-High** for Scenario C (any stale browser tab, operator tool call, or CLI `--id <old-feature-run>`).

### 3. What the Plan Must Add to Close It
1. **Extend `_scan_closed` (`src/sdlc/dashboard/fleet.py:107-122`)** cleanly while preserving test-fake compatibility: extract `wf.id`, `getattr(wf, "workflow_type", None)`, `getattr(wf, "status", None)`, `getattr(wf, "start_time", None)`, and `getattr(wf, "close_time", None)`.
2. **Branch specifically on `t == "FeatureWorkflow"`** in `fetch_fleet` (`src/sdlc/dashboard/fleet.py:173-189`):
   - When `t == "FeatureWorkflow"`, do **not** call `_fetch_closed` or `_fetch_marks`. Synthesize a `RunSummary` directly from visibility metadata:
     - Map `wf.status == WorkflowExecutionStatus.COMPLETED` (or `int(status) == 2` / `status is None`) to an `outcome` that `closedStatus` in `interfaces/dashboard/frontend/src/api/http.ts:42-45` recognizes as `'done'` (or update `closedStatus` in `http.ts:42` to also accept `outcome.startsWith('legacy-completed')` / `'completed'`). Map non-completed close statuses (`FAILED`, `TERMINATED`, `CANCELED`, `TIMED_OUT`) to `'failed:legacy'`.
     - Default `started_at` / `ended_at` when `start_time` / `close_time` are absent on test fakes (`tests/test_dashboard_fleet_marks.py:63`), compute `duration_s = max(0.0, (ended_at - started_at).total_seconds())`, set `mode="brownfield"` (valid `ProjectMode` for `http.ts:111`), `terminal_stage="legacy"`, `title="legacy run, summary unavailable"`, `stage_marks=None`, `graph_sha=None`.
   - When `t != "FeatureWorkflow"` (including `t == "GraphWorkflow"` and `t is None` in unit test fakes), keep calling `_fetch_closed(client, run_id)` and (`_fetch_marks` when `t == "GraphWorkflow"`).
3. **Cache non-`GraphWorkflow` descriptions in `RunGraphs._source` (`src/sdlc/dashboard/run_graph.py:99-111`)**: currently `if desc.workflow_type != "GraphWorkflow": return RunSource(desc, None, None)` returns before caching in `self._inputs`, causing `/api/fleet/summary` (`src/sdlc/dashboard/fleet_summary.py:109`) to re-issue `handle.describe()` on every poll for every closed `FeatureWorkflow` in the 20-run window.
4. **Guard `fetch_pending` (`src/sdlc/channels/transport.py:156-167`) and `cmd_status` (`src/sdlc/cli.py:875-878`)**: catch `(RPCError, WorkflowQueryFailedError)` (or check `describe().workflow_type == "FeatureWorkflow"`) so `POST /api/runs/{run_id}/answer|decide` returns HTTP `409`/`404` (`NoPendingError` / `KeyGoneError`) rather than HTTP 500, and `sdlc status --id` prints a clean legacy-run message instead of a traceback.

---

## L2 — `Q2=A`: Gate query 2 requires zero `Running` `TidyUpWorkflow` / `BenchmarkWorkflow` of ANY start time; query 1 requires zero `Running` `FeatureWorkflow`; re-run before deletion and before deploy

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario A — FR-009's "either/or" on `workflow.patched(f"e74-graph-child:{child_id}")` breaks `test_benchmark_replay.py` and in-flight parent replay:**
  1. `src/sdlc/workflows/pipeline_child.py:41` calls `if workflow.patched(f"e74-graph-child:{child_id}"):`. Every post-E74 `BenchmarkWorkflow` and `TidyUpWorkflow` execution recorded an `EVENT_TYPE_MARKER_RECORDED` (`patch_id = "e74-graph-child:..."`, `deprecated = False`) in its Temporal history — **including the committed replay fixture `tests/replay/histories/benchmark_one_cell.json` (event 19: `e74-graph-child:bench-replay-one-cell/seq-case#opencode#openai-gpt-5.2`)**.
  2. `spec.md:281-286` (FR-009) permits two options: *"either retained as a deprecation (`workflow.deprecate_patch`) or justified as removable from the evidence of FR-001 query 2 plus FR-008."*
  3. **Wrong outcome:** If the implementer chooses the second option in FR-009 and deletes the patch call instead of calling `workflow.deprecate_patch(f"e74-graph-child:{child_id}")`, `tests/replay/test_benchmark_replay.py:15` (`test_benchmark_workflow_replays_one_cell_history`) immediately fails with Temporal **`NondeterminismError (TMPRL1100)`** when replaying event 19! Furthermore, any `BenchmarkWorkflow` or `TidyUpWorkflow` started after the gate check that later replays across a worker restart would fail a workflow task on the missing patch marker.
- **Scenario B — False-empty gate check against the wrong Temporal host/namespace, or uninspected server schedules:**
  1. The gate commands in `spec.md:71-72` (`temporal workflow list --query ...`) omit `--address` and `--namespace`. Running `temporal workflow list` in a local shell defaults to `localhost:7233` / `default`, whereas `docker-compose.yml` or a remote environment may point `TEMPORAL_HOST` elsewhere (or no local server may be running, or an empty local dev server may answer).
  2. In `src/sdlc/schedules/apply.py:64-65`, `from_temporal` silently drops any server schedule whose workflow type is not in `KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}` (`src/sdlc/schedules/models.py:16`). If an unmanaged Temporal schedule targeting `FeatureWorkflow`, `TidyUpWorkflow`, or `BenchmarkWorkflow` exists on the server, `sdlc schedules list` will not show it, and it can trigger a run in the window between the pre-deploy check and worker replacement.

### 2. Likelihood
**Certain (100%)** if FR-009's "remove without `deprecate_patch`" option is taken (`test_benchmark_replay.py` fails immediately in CI); **Medium** for target-environment mismatch on the CLI gate check.

### 3. What the Plan Must Add to Close It
1. **Amend FR-009 (`src/sdlc/workflows/pipeline_child.py:41`)**: forbid deleting the patch marker raw; require `workflow.deprecate_patch(f"e74-graph-child:{child_id}")` before `return await workflow.execute_child_workflow("GraphWorkflow", ...)`.
2. **Harden the FR-001/FR-002 gate commands**:
   - Explicitly pass `--address "${TEMPORAL_HOST:-localhost:7233}" --namespace "${TEMPORAL_NAMESPACE:-default}"`.
   - Record the output of `temporal workflow count --address ...` (total workflows in namespace) and `temporal schedule list --address ...` alongside the two drain queries so an empty/wrong dev namespace or an unmanaged schedule cannot masquerade as a drained store.

---

## L3 — `FR-006`: `_revisable_stage` / `StageServices.revisable_stage` stay (`workflows/graph.py:74`)

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario — False premise in `FR-006` leaves calibration & soft-gate tests asserting against dead code while `test_calibration_plumbing.py` breaks outright:**
  1. `FR-006` (`spec.md:272-274`) claims: *"It is live `GraphWorkflow` plumbing (`src/sdlc/workflows/graph.py:74`), not `FeatureWorkflow`-only scaffolding."*
  2. **Fact check:** While `GraphWorkflow.__init__` (`src/sdlc/workflows/graph.py:74`) passes `revisable_stage=self._revisable_stage` into `StageServices(...)`, **zero graph nodes ever call `ctx.revisable_stage`!** In `GraphWorkflow`, `architect_node` (`src/sdlc/workflows/graph_nodes/precode.py:131-156`) and `plan_node` (`precode.py:159-177`) call `prepare` and `produce` directly, and `gate_node` (`src/sdlc/workflows/graph_nodes/gate.py:46-99`) runs the gate via `nc.ctx.gate(...)` and graph-edge looping (`NodeResult(port="revise", payload=decision)`).
  3. The **only** callers of `ctx.revisable_stage` in the entire repository are `src/sdlc/stages/architecture/step.py:303` and `src/sdlc/stages/plan/step.py:194` — the exact two `step()` functions that `L4` (`FR-007`) deletes!
  4. **Wrong outcome 1 (Immediate test breakage):** `tests/calibration/test_calibration_plumbing.py:188-202` (`test_both_proposer_stages_pass_their_resolved_model`) reads `src/sdlc/stages/architecture/step.py` and `src/sdlc/stages/plan/step.py` and asserts `idx = src.find("revisable_stage("); assert idx != -1` and `"author_model=prep.resolved_model" in call`. Deleting `step()` in L4 immediately fails `test_calibration_plumbing.py:201` with `AssertionError`.
  5. **Wrong outcome 2 (Silent loss of live calibration enforcement):** `tests/calibration/test_gate_requires_calibration.py:22-43` and `tests/test_soft_gate_auto_approval.py:69-81` inspect `_revisable_stage` in `src/sdlc/workflows/role_host.py:327-379` to enforce C7 (`judge_error` and `author_model` must be plumbed into `self._gate`) and SG-4 (`calibration=calibration` passed to `self._gate`), **and never inspect `src/sdlc/workflows/graph_nodes/gate.py:46-99` (`gate_node`)**. Once L4 deletes `architecture.step()` and `plan.step()`, `_revisable_stage` has **zero callers in `src/`**, turning those C7 and SG-4 tests into vacuous assertions on dead code while leaving the live `gate_node` (`src/sdlc/workflows/graph_nodes/gate.py:57-74`) unpinned!

### 2. Likelihood
**Certain (100%)** — `tests/calibration/test_calibration_plumbing.py:201` will fail immediately when L4 is applied, and `test_gate_requires_calibration.py` / `test_soft_gate_auto_approval.py` will silently stop testing live gate execution.

### 3. What the Plan Must Add to Close It
1. **Migrate `tests/calibration/test_calibration_plumbing.py:188-202`** (`test_both_proposer_stages_pass_their_resolved_model`) to inspect the live `GraphWorkflow` nodes — `architect_node` and `plan_node` in `src/sdlc/workflows/graph_nodes/precode.py:131-177` (verifying `resolved_model=prep.resolved_model` is stored on `PendingGate` at lines `156` and `177`) and `gate_node` in `src/sdlc/workflows/graph_nodes/gate.py:46-75` (verifying `author_model=pending.resolved_model` is passed into `calibrate_proposer_output` and `nc.ctx.gate`).
2. **Extend `tests/calibration/test_gate_requires_calibration.py:22-43` and `tests/test_soft_gate_auto_approval.py:69-81`** to also inspect `gate_node` in `src/sdlc/workflows/graph_nodes/gate.py:46-99`, so C7 and SG-4 are enforced on the live `GraphWorkflow` gate path even while `_revisable_stage` remains on `RoleHostMixin` per L3.

---

## L4 — `FR-007`: `architecture` and `plan` `step()` composites are deleted; `prepare` / `produce` / `finish` stay

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario A — `_StageModule` descriptor trap in `src/sdlc/stages/architecture/__init__.py` and `src/sdlc/stages/plan/__init__.py` raises `ImportError` across the codebase:**
  1. Both `src/sdlc/stages/architecture/__init__.py:24,32,42-46,59-78` and `src/sdlc/stages/plan/__init__.py:21,39,49-53,66-85` export `"step"` in `__all__` and replace `sys.modules[__name__]` with a custom `_StageModule(types.ModuleType)` whose `@property def step(self)` executes `from .step import step as _fn; return _fn` and whose `@step.setter` executes `pass` (swallowing Python's submodule attribute binding when `sdlc.stages.architecture.step` is imported!).
  2. **Wrong outcome:** When `def step` is removed from `src/sdlc/stages/architecture/step.py:279-314` and `src/sdlc/stages/plan/step.py:174-202`, if `_StageModule` and `"step"` in `__init__.py` are not removed in the same diff:
     - Any attribute access `sdlc.stages.architecture.step` or `sdlc.stages.plan.step` — including `unittest.mock.patch("sdlc.stages.architecture.step.produce", ...)`, `from ...stages.architecture.step import prepare` inside Temporal's `SandboxedWorkflowRunner` importer (`src/sdlc/workflows/graph_nodes/precode.py:28-31`), or `hasattr(architecture, "step")` — triggers `_StageModule.step` and crashes with **`ImportError: cannot import name 'step' from 'sdlc.stages.architecture.step'`**!
- **Scenario B — Clause verification (`scripts/check_clauses.py`) and the `AGENTS.md` Artifact Boundary fail:**
  1. `src/sdlc/stages/architecture/architecture.md:5,9-20` (`ARCH-1.1`..`ARCH-1.4`) and `src/sdlc/stages/plan/plan.md:5,9-20` (`PLAN-1.1`..`PLAN-1.4`) specify the slice contract in terms of `step(ctx, ...) -> tuple[ArchitectureSpec, GateDecision]` / `tuple[ImplementationPlan, GateDecision]`.
  2. `tests/architecture/test_architecture_slice_contract.py:18-144` (`@pytest.mark.clause("ARCH-1.1".."ARCH-1.3")`) and `tests/plan/test_plan_slice_contract.py:26-159` (`@pytest.mark.clause("PLAN-1.1".."PLAN-1.3")`) directly call and inspect `architecture.step` / `plan.step`.
  3. `tests/architecture/test_architecture_step_split.py:116-145` and `tests/plan/test_plan_step_split.py:101-130` (`test_a_judge_error_records_its_reason`) call `step(...)` to verify R0 judge-error recording in `finish(...)`.
  4. **Wrong outcome:** Deleting `step()` without updating `architecture.md` and `plan.md` in the same diff violates the repo's binding Artifact Boundary rule (`AGENTS.md`: *"Whoever changes a stage's behaviour must update its clauses in the same diff"*) and breaks `test_architecture_slice_contract.py`, `test_plan_slice_contract.py`, `test_architecture_step_split.py:137`, and `test_plan_step_split.py:122`.
- **Scenario C — Six unit test files import non-`FeatureWorkflow` helper functions from `sdlc.workflows.feature`:**
  1. Deleting `src/sdlc/workflows/feature.py` (`FR-003`) breaks 6 test files that import stage helpers through `sdlc.workflows.feature` even though `FeatureWorkflow` is not what they test:
     - `tests/plan/test_plan_validation_module.py:5` and `tests/plan/test_plan_graph_validation.py:9` (`from sdlc.workflows.feature import _validate_task_graph` -> live at `sdlc.stages.plan.validation.validate_task_graph`)
     - `tests/test_untraced_criteria.py:7` (`from sdlc.workflows.feature import untraced_criteria` -> live at `sdlc.stages.analyze.models.untraced_criteria`)
     - `tests/merge/test_merge_gate_wiring.py:91` (`from sdlc.workflows.feature import _merge_evidence_all_green` -> live at `sdlc.stages.merge.step._merge_evidence_all_green`, line 42)
     - `tests/test_stack_contract.py:4` (`from sdlc.workflows.feature import DEFAULT_LINT_CMD` -> live at `sdlc.stages.qa.step.DEFAULT_LINT_CMD`, line 44)
     - `tests/clarify/test_clarify_stage_wiring.py:30` (`from sdlc.workflows.feature import _requirements_for_downstream` -> live at `sdlc.stages.architecture.step._requirements_for_downstream`, line 55)

### 2. Likelihood
**Certain (100%)** — every one of these imports/contracts is exercised by default `pytest` and `scripts/check_clauses.py`.

### 3. What the Plan Must Add to Close It
1. **Clean up `src/sdlc/stages/architecture/__init__.py:20-78` and `src/sdlc/stages/plan/__init__.py:20-85`**: remove `"step"` from `__all__`, remove the `if name == "step":` branch in `__getattr__`, and delete the `_StageModule` class and `sys.modules[__name__].__class__ = _StageModule` hook so `sdlc.stages.architecture.step` and `sdlc.stages.plan.step` resolve normally as submodules.
2. **Update `src/sdlc/stages/architecture/architecture.md` and `src/sdlc/stages/plan/plan.md`** in the same diff to state the contract in terms of `prepare` / `produce` / `finish` (and note `AGENTS.md`'s sandbox rule: edits to `<stage>.md` must be performed in the orchestrator/primary checkout, never by a sandboxed worktree harness).
3. **Rewrite `tests/architecture/test_architecture_slice_contract.py`, `tests/plan/test_plan_slice_contract.py`, `tests/architecture/test_architecture_step_split.py:116-145`, and `tests/plan/test_plan_step_split.py:101-130`** to test `prepare` / `produce` / `finish` directly while preserving `@pytest.mark.clause("ARCH-1.1".."ARCH-1.4")` and `@pytest.mark.clause("PLAN-1.1".."PLAN-1.4")`.
4. **Repoint the 6 helper imports** in `tests/plan/test_plan_validation_module.py:5`, `tests/plan/test_plan_graph_validation.py:9`, `tests/test_untraced_criteria.py:7`, `tests/merge/test_merge_gate_wiring.py:91`, `tests/test_stack_contract.py:4`, and `tests/clarify/test_clarify_stage_wiring.py:30` to their canonical stage modules.

---

## L5 — `FR-011`: Goldens kept and re-baselined from `GraphWorkflow`; any `commands` / `close` diff is a STOP

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario A — `spec.md` is factually wrong about `research_retain_grounded.json` (`spec.md:43, 186`):**
  1. `spec.md:43` (Card verification row 5) and `spec.md:186` claim: *"Four histories are not FeatureWorkflow runs and are loaded by live tests: `benchmark_one_cell`, `assessment_discover_risk`, `architect_research_usage`, `research_retain_grounded` (`test_research_retain_replay.py`)."*
  2. **Fact check:** `tests/replay/histories/research_retain_grounded.json` **IS a `FeatureWorkflow` history** (`"workflow": "FeatureWorkflow"`, event 1 `workflow_type.name == "FeatureWorkflow"`)! And `tests/replay/test_research_retain_replay.py:26,34,44,77,106` imports `FEATURE_STARTER` from `tests.replay.harness` and `replayer` from `tests.replay.test_feature_replay`, replays `research_retain_grounded.json` against `FeatureWorkflow`, and asserts `assert fixture["workflow"] == "FeatureWorkflow"` at line 106!
  3. **Wrong outcome:** Leaving `research_retain_grounded.json` untouched while deleting `FeatureWorkflow`, `FEATURE_STARTER`, and `test_feature_replay.py` immediately breaks `tests/replay/test_research_retain_replay.py` with `ImportError` and `KeyError: Workflow type FeatureWorkflow is not registered`.
- **Scenario B — Deleting the 19 scenario histories (`FR-010`) instead of replacing them with `GraphWorkflow`-captured histories breaks 8 test files and destroys `GraphWorkflow` replay determinism coverage:**
  1. `FR-010` (`spec.md:288-293`) says *"the FeatureWorkflow-captured histories MUST be removed"*, whereas `US4 AC3` (`spec.md:190-193`) and `SC-004` (`spec.md:344-348`) require every replay/golden/chaos test to exercise `GraphWorkflow`.
  2. In `tests/replay/harness.py:130-156`, `write_fixtures(name, captured, starter_name)` writes **both** `tests/replay/histories/<name>.json` and `tests/replay/golden/<name>.json` as a paired unit.
  3. **Wrong outcome:** If the 19 scenario files under `tests/replay/histories/` are deleted rather than overwritten with `GraphWorkflow`-captured histories via `write_fixtures(..., GRAPH_STARTER.name)`:
     - `tests/replay/test_graph_golden_chaos.py:59-77, 80, 102` fails on **all 19 scenarios** (`FileNotFoundError` in `load_history(name)` for `test_command_projection_matches_the_paired_history`, `test_close_projection_matches_the_paired_history`, `test_drift_in_command_sequence_fails_Loudly`, and `test_drift_in_close_payload_fails_loudly`).
     - `tests/replay/test_fixtures_present.py:35-41` fails on all 19 `SCENARIOS` (`assert load_history(scenario.name).events` at `:41`, plus `assert golden["workflow"] == "FeatureWorkflow"` at `:38` which must become `"GraphWorkflow"`).
     - `tests/replay/test_architect_research_usage_replay.py:172` fails because `test_pin_rejects_an_unharvested_history` calls `load_history("architect_research_tool")`.
     - `tests/durability/test_inflight_resume.py:75,96`, `tests/durability/test_priced_usage_parity.py:101`, and `tests/review/test_review_step_shadowing_chaos.py:57` all fail because they call `load_history("architect_research_tool")` or `load_history("greenfield_happy")`.
     - `tests/replay/test_benchmark_replay.py:9` and `tests/replay/test_architect_research_usage_replay.py:33` fail with `ModuleNotFoundError: No module named 'tests.replay.test_feature_replay'` because they import `replayer` from `tests.replay.test_feature_replay`!
     - `GraphWorkflow` would have **zero** `Replayer` determinism tests across the 19 pipeline scenarios once `test_feature_replay.py` is deleted.

### 2. Likelihood
**Certain (100%)** — deleting `histories/*.json` and `test_feature_replay.py` without re-capturing `GraphWorkflow` histories and moving `replayer` breaks 8 test files immediately.

### 3. What the Plan Must Add to Close It
1. **Re-capture all 19 `SCENARIOS` histories AND goldens from `GRAPH_STARTER`** via `write_fixtures(scenario.name, captured, GRAPH_STARTER.name)` (`tests/replay/harness.py:130-156`), and verify that in `git diff tests/replay/golden/` **only** `"workflow"` (`"FeatureWorkflow"` -> `"GraphWorkflow"`) and `"source_commit"` change — zero diff in `commands` or `close` (`L5` STOP gate).
2. **Note the existing skew in `tests/replay/test_graph_golden_chaos.py:61-70`**: 10 of the 19 old `FeatureWorkflow` histories (`076db363`) lacked `activity:build_trace_inventory` (and `research_greenfield` lacked `activity:read_dead_attempt_usage`) while the goldens (`98dc7a3e`) already had them. Once histories are re-captured from `GraphWorkflow`, `histories/<name>.json` and `golden/<name>.json` match identically and the grace-period filter in `test_graph_golden_chaos.py:61-70` can be simplified or kept clean.
3. **Re-capture `tests/replay/histories/research_retain_grounded.json` under `GRAPH_STARTER`** (`tests/replay/test_research_retain_replay.py:34,77,106`) and update `test_research_retain_replay.py` to use `GRAPH_STARTER` and assert `fixture["workflow"] == "GraphWorkflow"`.
4. **Move `replayer(...)` into `tests/replay/harness.py`** defaulting to `workflows=GRAPH_STARTER.workflows` (`[GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow]`), update `tests/replay/test_benchmark_replay.py:9` and `tests/replay/test_architect_research_usage_replay.py:33` to import `replayer` from `tests.replay.harness`, replace `test_feature_replay.py` / `test_capture_feature.py` with `GraphWorkflow` equivalents (or update them in place), and update `tests/replay/test_fixtures_present.py:38` to assert `golden["workflow"] == "GraphWorkflow"`.

---

## L6 — `FR-015`: No wire-contract field removed (`RunState` / `RunSummary` optional `None`-for-legacy fields stay)

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario — Committed read-side golden fixtures (`scripts/dump_read_fixtures.py`) model `"legacy-run"` as an OPEN `FeatureWorkflow`:**
  1. `scripts/dump_read_fixtures.py:50,86,88` and `tests/test_dashboard_fleet_summary.py:133,150` construct `"legacy-run": _Handle(wf_type="FeatureWorkflow")` and place `"legacy-run"` into **`open_ids`** (`open_ids=["bp-run", "custom-run", "legacy-run"]`).
  2. `tests/test_read_fixtures_fresh.py` enforces that the output of `scripts/dump_read_fixtures.py` matches committed JSON fixtures byte-for-byte.
  3. **Wrong outcome:** If someone edits `scripts/dump_read_fixtures.py` or `tests/test_dashboard_fleet_summary.py` to drop `"legacy-run"` (thinking `FeatureWorkflow` cannot be open after `FR-005`), `tests/test_read_fixtures_fresh.py` and the frontend contract tests for the `null`-arm `FleetRunSummaryWire` (`stage_marks=None`, `graph_sha=None`) will break or lose coverage of the legacy wire arm that `L6` (`FR-015`) explicitly preserves.

### 2. Likelihood
**Medium** — any blanket grep-and-delete of `"FeatureWorkflow"` across `scripts/` and `tests/` will hit `scripts/dump_read_fixtures.py:86` and `tests/test_dashboard_fleet_summary.py:133,150`.

### 3. What the Plan Must Add to Close It
1. **Explicitly exempt `scripts/dump_read_fixtures.py:86` and `tests/test_dashboard_fleet_summary.py:133,150` from `SC-002`'s zero-match grep** (or document that they test the non-`GraphWorkflow` wire fallback in `RunGraphs._source` / `fleet_summary._row`), and run `pytest tests/test_read_fixtures_fresh.py tests/test_dashboard_fleet_summary.py` as a verification step.

---

## L7 — Rollback is roll-forward only

### 1. Strongest Concrete Failure Scenario (`inputs/state -> wrong outcome`)
- **Scenario — Stranded workflow task infinite retry loop on Temporal server after worker cutover:**
  1. Suppose a `FeatureWorkflow` was in `CONTINUED_AS_NEW` / `Running` on a non-default namespace, or an in-flight `BenchmarkWorkflow` / `TidyUpWorkflow` hits `NondeterminismError` because `workflow.deprecate_patch(f"e74-graph-child:{child_id}")` was omitted in `src/sdlc/workflows/pipeline_child.py:41`.
  2. Temporal **does not fail** a workflow execution when a worker rejects a workflow task with `WorkflowType FeatureWorkflow is not registered` or `NondeterminismError`; instead, Temporal retries the Workflow Task forever on `sdlc-task-queue` with backoff, saturating worker error logs and `workflow_task_execution_failed` metrics.
  3. **Wrong outcome:** Under "roll-forward only", operators have no documented runbook command in the plan to clear a stuck workflow task without re-introducing `FeatureWorkflow`.

### 2. Likelihood
**Low** if `L2`'s gate and `deprecate_patch` mitigations are followed; **High impact** if triggered.

### 3. What the Plan Must Add to Close It
1. **Document the roll-forward recovery actions in the plan:**
   - For a `NondeterminismError` in `pipeline_child.py`: ship a roll-forward fix restoring `workflow.deprecate_patch(f"e74-graph-child:{child_id}")` (which immediately unblocks the stuck `BenchmarkWorkflow` / `TidyUpWorkflow` task).
   - For any unexpected zombie `FeatureWorkflow` discovered on a task queue post-cutover: terminate via `temporal workflow terminate --workflow-id <id> --reason "020-delete-featureworkflow post-cutover cleanup"` and re-submit the idea via `sdlc start` (`GraphWorkflow`).

---

## Explicit Audit of the 5 Requested Surfaces (`skeptic-brief-1.md` line 13)

| # | Surface | Exact Code Locations (`file:line`) | Findings & Required Plan Mitigations |
|---|---|---|---|
| 1 | **Workflows or activities starting / querying / signaling `FeatureWorkflow` by name** | - `src/sdlc/workflows/pipeline_child.py:41-51` (`execute_pipeline_child` used by `BenchmarkWorkflow` at `src/sdlc/benchmarks/workflow.py:298` and `TidyUpWorkflow` at `src/sdlc/workflows/tidyup.py:228`)<br>- `src/sdlc/vcs/janitor.py:32-38` (`list_open_workflow_ids` uses `ExecutionStatus="Running"` without type filter)<br>- `src/sdlc/workflows/assessment.py:361` (starts `TriageWorkflow` only)<br>- `src/sdlc/workflows/reflect.py:42` (activities only) | Only `pipeline_child.py:51` starts `"FeatureWorkflow"` by string name. When deleting the `else` branch in `pipeline_child.py:41-51`, **must keep `workflow.deprecate_patch(f"e74-graph-child:{child_id}")`** so `tests/replay/test_benchmark_replay.py` and in-flight `BenchmarkWorkflow` / `TidyUpWorkflow` histories do not fail with `NondeterminismError`. |
| 2 | **Schedules** | - `src/sdlc/schedules/models.py:16` (`KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}`)<br>- `src/sdlc/schedules/apply.py:44-68` (`from_temporal` ignores unknown workflow types at lines `64-65`) | Managed schedules only permit `"ReflectWorkflow"`. However, `from_temporal` (`apply.py:64-65`) silently ignores any unmanaged server schedule targeting `"FeatureWorkflow"`. Add `temporal schedule list` to the pre-cutover check in `L2`. |
| 3 | **CLI (`sdlc status` / `answer` / `approve` / `reject` / `revise`) & Operator tools** | - `src/sdlc/cli.py:859-878` (`_cmd_reply`, `cmd_status`)<br>- `src/sdlc/channels/transport.py:129-131, 156-167, 170-189` (`resolve_key`, `fetch_pending`, `submit`)<br>- `src/sdlc/channels/inbox.py:90-98` (`list_open_run_ids`)<br>- `src/sdlc/operator/tools.py:460-500` (`_handle`, `_reply`, `answer_question`, `decide_gate`) | `inbox.py:91` drops `'FeatureWorkflow'` per `FR-005`. However, `sdlc status --id <id>` (`cli.py:877`) queries `GraphWorkflow.status` and `sdlc approve/reject/revise/answer --id <id>` (`cli.py:863` -> `transport.py:166`) queries `"pending_decisions"` directly on `get_workflow_handle(run_id)`. On a closed `FeatureWorkflow`, the worker has no `FeatureWorkflow` registered and raises `WorkflowQueryFailedError` / `RPCError`. Catch query failure in `transport.py:156-167` and `cli.py:875-878` to surface a clean error instead of a crash. |
| 4 | **Dashboard routes (`fleet.py`, `api.py`, `read_routes.py`, `fleet_summary.py`, `run_graph.py`)** | - `src/sdlc/dashboard/fleet.py:89-204` (`_scan_open`, `_scan_closed`, `_fetch_closed`, `_fetch_marks`, `fetch_fleet`)<br>- `src/sdlc/dashboard/api.py:116-147, 188-208, 309-355` (`/answer`, `/runs/{id}`, `/decide`, `/graph`, `/graph_state`)<br>- `src/sdlc/dashboard/read_routes.py:21-45` (`/api/fleet/summary`)<br>- `src/sdlc/dashboard/fleet_summary.py:69-119` (`_row`, `build_fleet_summary`)<br>- `src/sdlc/dashboard/run_graph.py:95-126` (`RunGraphs._source`, `source`, `source_readonly`)<br>- `interfaces/dashboard/frontend/src/api/http.ts:36-45, 106-140` (`closedStatus`, `mapClosed`) | 1. `fleet.py`: must synthesize `RunSummary` from visibility metadata when `t == "FeatureWorkflow"` with an `outcome` that `http.ts:closedStatus` maps to `'done'` for completed runs (see `L1`).<br>2. `api.py:309-355` (`/graph`, `/graph_state`) and `fleet_summary.py:109` (`/api/fleet/summary`) use `RunGraphs._source` (`run_graph.py:99-111`), which calls `handle.describe()` (server RPC, safe without worker registration) and short-circuits when `desc.workflow_type != "GraphWorkflow"`. Cache that non-`GraphWorkflow` `RunSource` in `run_graph.py:110` to avoid repeated `describe()` RPCs on every poll.<br>3. `api.py:116-132, 188-208` (`/answer`, `/decide`): guard `resolve_key` when `fetch_pending` fails on a closed `FeatureWorkflow` handle so it returns HTTP 404/409 instead of HTTP 500. |
| 5 | **`DeploymentWorkflow` / `CrewTaskWorkflow` parents or children whose parent is a `FeatureWorkflow`** | - `src/sdlc/stages/deploy/step.py:138-143` (starts `DeploymentWorkflow` child)<br>- `src/sdlc/workflows/deployment.py:8-10, 48-163` (`DeploymentWorkflow` has no child workflows; `ObservationWorkflow` is deferred to E-70)<br>- `src/sdlc/stages/code/step.py:280-306` (starts `CrewTaskWorkflow` child)<br>- `src/sdlc/workflows/crew.py:117-518` (`CrewTaskWorkflow` runs activities only; no parent queries/signals) | Both `DeploymentWorkflow` and `CrewTaskWorkflow` are invoked via `workflow.execute_child_workflow(...)` with Temporal's default `ParentClosePolicy.TERMINATE` and never query or signal their parent by workflow type name. Thus, neither can be `Running` under a `FeatureWorkflow` parent once FR-001 Query 1 (`WorkflowType = "FeatureWorkflow" AND ExecutionStatus = "Running"`) returns zero rows. |
