# Test inventory (final, T003) — 020

Generated 2026-11-08 at `d57c381d` by grep; **finalised 2026-11-10 by T003**
(plan T010, FR-012) against `4f6fc2c3`. Every one of the 76 `.py` rows has
exactly one class: `delete`, `migrate`, `repoint`, `comment-only` or `keep`.
Each `delete` names its GraphWorkflow counterpart as `path::test_name`; each
`migrate` names what replaces the FeatureWorkflow leg. T026 (plan T070)
executes this table: one commit per class bucket (`delete`, `migrate`,
`comment-only`); `repoint` was executed by T005 and T020; `keep` needs no
commit.

The 37 `.json` fixtures are handled by T018 (re-capture), not by this table.

## A. Import FeatureWorkflow code (45)

| File | Class | Counterpart (delete) / what replaces the FeatureWorkflow leg |
|---|---|---|
| `tests/replay/test_research_retain_replay.py` | migrate | Re-capture `research_retain_grounded` from `GRAPH_STARTER` (T018); replay via `replayer(*GRAPH_STARTER.workflows)`; pin `fixture["workflow"] == "GraphWorkflow"`. |
| `tests/replay/test_capture_feature.py` | delete | Counterpart: `tests/replay/test_capture_graph.py::test_capture_graph_scenario` (T017), the `GRAPH_STARTER` twin behind the same `SDLC_CAPTURE_HISTORIES=1` switch and capture-twice rule. |
| `tests/test_model_forwarding.py` | migrate | Swap `FEATURE_STARTER`→`GRAPH_STARTER` in the capture legs (`_capture_with_override`, tests e/h); roles/memo/fan-out assertions unchanged (RoleHost-shared). |
| `tests/replay/harness.py` | migrate | Delete `FEATURE_STARTER`, `_start_feature`, `_feature_workflows` (T021); gains `replayer()` (T004). |
| `tests/replay/test_graph_golden.py` | migrate | Drop the memo_parity FeatureWorkflow leg; assert the GraphWorkflow keys `== MEMO_PARITY_KEYS` (pinned by T007, dropped by T021). |
| `tests/durability/wire_dump.py` | migrate | `capture_no_override_wire` re-points to `GRAPH_STARTER`; `fixtures/wire_no_override.json` is deliberately re-baselined from GraphWorkflow in the same commit (consumer: `test_wire_neutrality.py`, outside this table). |
| `tests/test_run_state_query.py` | migrate | Drop the `feature` fixture param (keep the graph leg); re-point the canonical `_stage`-name scan from `feature.py` to `src/sdlc/workflows/graph_nodes/*.py`. |
| `tests/durability/test_priced_usage_parity.py` | migrate | Live leg re-points to `GRAPH_STARTER`; recorded side asserts against `T/durability/fixtures/priced_usage_pre_e74.json` (extracted by T007) instead of the live Feature capture. |
| `tests/test_tool_approval_gate.py` | migrate | Re-point the 3 temporal tests to a GraphWorkflow worker (`[GraphWorkflow, DeploymentWorkflow]`, start via `build_run_input`); signals/queries already by name. |
| `tests/retro/test_retro_stage.py` | migrate | Re-point the 4 temporal tests to GraphWorkflow; `run_summary`/retention assertions unchanged (RunHost._retro shared). |
| `tests/test_gate_notifications.py` | migrate | Re-point the 3 temporal tests to GraphWorkflow; notify-reason sequence assertions unchanged (GateHost._gate/_notify shared). |
| `tests/integration/test_feature_host_mixins.py` | migrate | Re-point all 6 mixin/MRO/attribute-inventory tests to `GraphWorkflow` (same mixin set, `graph.py` MRO). |
| `tests/research/test_research_e2e.py` | migrate | Re-point the 3 temporal tests to GraphWorkflow (`_research_cfg` selects `SHIPPED["default-research"]`); `_research_fake_activities` stays (imported by `scenarios.py`). |
| `tests/test_budget_gate.py` | migrate | Re-point both tests to GraphWorkflow; the approve-extends-through-4-rounds leg has no golden counterpart and is unique coverage. |
| `tests/test_e2e_greenfield.py` | migrate | Happy-path test is deleted citing `tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[greenfield_happy]`; the untraced-analyst advisory leg re-points to a GraphWorkflow run. |
| `tests/test_feature_brownfield_stages.py` | migrate | Delete the 3 `_pipeline` source pins (ordering is the graph topology's job); keep `SCAN_FAKES`/`BROWNFIELD_SPECS`/`fake_resolve_tree` (imported by `scenarios.py`); full-run rows duplicate the `brownfield_happy`/`intake_reject`/`context_reject` goldens. |
| `tests/test_gate_timeout_action.py` | migrate | Keep the workflow-free config rows; re-point the 2 temporal rows (architecture timeout rejects; HOLD stays decidable) to GraphWorkflow. |
| `tests/test_task_gate_revise_loop.py` | migrate | Re-point `_run` to a GraphWorkflow worker; drive `awaiting:task:t1` by name (TaskHost._dev_task shared). |
| `tests/test_crew_feature_wiring.py` | migrate | Re-point both tests to `[GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow]` via `build_run_input`; fake activities/asserts unchanged. |
| `tests/test_board_workflow.py` | migrate | Re-point both real-BoardStore e2e tests to GraphWorkflow; board activities and gate names identical. |
| `tests/deploy/test_deploy_workflow_paths.py` | migrate | Re-point `_run` to GraphWorkflow; the six deploy paths drive the same shared `DeploymentWorkflow` child; `run_summary` query already string-based. |
| `tests/test_pending_wiring.py` | repoint | Composition-root instance swaps `FeatureWorkflow`→`GraphWorkflow`; monkeypatch target becomes the shared host module; drop `feature.py` from the SRC concat. |
| `tests/test_run_host.py` | repoint | Swap `FeatureWorkflow`→`GraphWorkflow` in the 5 MRO/RunHost tests; assertions identical through MRO. |
| `tests/test_feature_delta_gate.py` | migrate | `_arch_src` drops the `_pipeline` half (keeps `stages/architecture/step.py` + `graph_nodes/precode.py`); the exhausted-retries temporal row is deleted citing the `delta_failed` golden (`tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[delta_failed]`). |
| `tests/test_model_usage_capture.py` | migrate | Re-point the single temporal test to GraphWorkflow; `events.jsonl` export path is ReportHost-shared. |
| `tests/test_seeded_work.py` | migrate | Keep the SeededWork model rows; replace the FW.run third-argument pin with a `build_run_input`/`SHIPPED["seeded"]` catalog pin; the temporal skip proof duplicates the `seeded` golden (`...[seeded]`). |
| `tests/durability/test_first_workflow_task_time.py` | migrate | Swap the worker to `[GraphWorkflow, DeploymentWorkflow]` and start via `build_run_input`; plugin/sandbox posture unchanged. |
| `tests/graph_workflow/test_graph_workflow_class.py` | migrate | Re-cast the FW-parity query/signal test as a frozen name-set pin; the worker-registration row drops the `FeatureWorkflow` expectation (see also T025/T026 on `test_worker_registration.py`, outside this table). |
| `tests/durability/test_inflight_resume.py` | migrate | Re-point to the re-captured `greenfield_happy` history and register GraphWorkflow (T020); the in-flight-resume proof now replays a GraphWorkflow-recorded prefix. |
| `tests/durability/test_payload_guard_callsites.py` | repoint | Swap `FeatureWorkflow()`→`GraphWorkflow()` in the `_run_role` row; all other rows workflow-free. |
| `tests/integration/test_feature_question_host.py` | repoint | Swap `FeatureWorkflow`→`GraphWorkflow` in the 3 QuestionHost wiring tests. |
| `tests/replay/test_feature_replay.py` | delete | Counterpart: `tests/replay/test_graph_replay.py::test_graph_workflow_replays_captured_history` (T020), replaying all 18 scenario histories with `raise_on_replay_failure=True`. `replayer()` moves to `harness.py` first (T004). |
| `tests/test_gate_host.py` | repoint | The 2 FW rows (inherits GateHost; override signature) swap to `GraphWorkflow`; the rest is GateHost-only. |
| `tests/test_operator_e2e.py` | migrate | Start a GraphWorkflow (via `build_run_input`) instead; the run still parks at its first gate so the operator verbs exercise the same paths. |
| `tests/test_pinned_base_e2e.py` | migrate | Re-point the single test to a GraphWorkflow start; DIFFS/BASES recorder assertions unchanged. |
| `tests/integration/test_feature_stage_services.py` | repoint | Swap `FeatureWorkflow`→`GraphWorkflow`; the `_ctx` StageContext contract is identical (`graph.py` builds the same `_ctx`). |
| `tests/integration/test_feature_task_host.py` | repoint | Swap the class to `GraphWorkflow`; drop the `feature.py` source-read row (the `task_host.py` rows already carry the invariant). |
| `tests/research/test_research_durability_nested.py` | migrate | Re-point worker/start to GraphWorkflow (`default-research` graph); tool-activity/no-fanout projection assertions unchanged. |
| `tests/review/test_review_step_shadowing_chaos.py` | migrate | Re-point `_replay_chain` to `*GRAPH_STARTER.workflows` and replay a graph-recorded history (T020); the shadowing invariant assertions are unchanged. |
| `tests/test_dashboard_e2e.py` | migrate | Start a GraphWorkflow via `build_run_input`; the real-visibility fleet leg keeps `start_local`. |
| `tests/test_factory_recorder.py` | repoint | Swap `FeatureWorkflow._benchmarking`→`GraphWorkflow._benchmarking`; the predicate is BenchmarkHost's. |
| `tests/durability/test_sandbox_module_marking.py` | repoint | Swap the Replayer workflow set to `[GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow]`; the pinned-module row is workflow-independent. |
| `tests/graph_workflow/test_outcome_string.py` | repoint | Swap the Replayer construction class; the parametrized outcome table untouched. |
| `tests/test_waste_population_wiring.py` | migrate | Swap `_stage_record` target to `GraphWorkflow`; the SRC scan drops `feature.py` and adds `src/sdlc/workflows/build.py` + `graph_nodes/postplan.py` (where the single `waste=WasteBag.from_digest(...)` site lives). |
| `tests/clarify/test_clarify_stage_wiring.py` | repoint | The `:30` import becomes `from sdlc.stages.architecture.step import _requirements_for_downstream` (T005); the one AST row re-targets the requirements-publish owner on the graph side. |

## B. Name the type only (31)

| File | Class | Counterpart (delete) / what replaces the FeatureWorkflow leg |
|---|---|---|
| `tests/test_factory_purity.py` | migrate | Drop the `feature_class` fixture and its loop term (keep `benchmark_host_class`; the graph side is already covered by its GRAPH_MODULES test). The `FEATURE_PY` export is removed last — `test_memoization_wiring`, `test_memory_purity`, `test_memory_wiring` import it and move in the same commit. |
| `tests/test_inbox_query.py` | migrate | T024 updates it first: the default-tuple test drops the `FeatureWorkflow` expectation (default becomes `("GraphWorkflow",)`); explicit-type rows unchanged. |
| `tests/graph_workflow/test_pipeline_child_upgrade.py` | migrate | T022 rewrites it: `StubFeature` and the pre-cutover parent are removed; a new parent starts a GraphWorkflow child and its history replays. The deleted FW-branch test's counterpart is `test_on_graph_fires_once_with_content_sha_before_the_child_starts` (same file). |
| `tests/analyze/test_analyst_stage_wiring.py` | migrate | `_src()` re-points to `graph_nodes/postplan.py` (`analyze_node` calls `analyze.step(..., analyst_agent=t_analyst, ...)`); the ordering row becomes a topology assertion (analysis precedes merge in the shipped graph). |
| `tests/test_triage_cli_wiring.py` | comment-only | Mentions are prose; the negative import assertion stays trivially true. |
| `tests/test_dashboard_run_graph_routes.py` | keep | The `wf_type="FeatureWorkflow"` handles are legacy-run fixtures matching real historical rows (production detects legacy by `!= "GraphWorkflow"`); needed forever (FR-015). |
| `tests/graph_workflow/test_cutover_wiring.py` | keep | The fleet closed-query pin (`WorkflowType='FeatureWorkflow'` AND GraphWorkflow) is the permanent legacy-row wire fallback (020 contract §1.4); the two negative prose assertions stay trivially true. |
| `tests/fakes/fake_activities.py` | comment-only | Docstring/comment mentions only; fakes dispatch by activity name. |
| `tests/replay/test_fixtures_present.py` | migrate | T020: expect `workflow == "GraphWorkflow"` for the `SCENARIOS` goldens/histories after the re-capture (`assessment_discover_risk` keeps its own expectation). |
| `tests/research/test_research_stage_wiring.py` | migrate | `_pipeline_src()` re-points to `graph_nodes/precode.py` (`research_node`/`clarify_node` carry the `research_enabled` gate and the `brief_digest` memo input); the enable/disable row becomes a graph-catalog assertion. |
| `tests/test_board_wiring.py` | migrate | Workflow-side rows re-point to `GraphWorkflow` + a `graph_nodes/` scan (precode publishes `"requirements"`; `gate.py` publishes architecture/plan); `board_host`-only rows unchanged. |
| `tests/test_crew_gates.py` | comment-only | Drives `CrewTaskWorkflow` exclusively; mentions are docstring prose. |
| `tests/test_integration_branch_wired.py` | migrate | `SRC` re-points to `graph_nodes/precode.py` (`setup_integration_branch`, `_integration_head`, `_integration_wt`) plus `graph.py` (attribute declarations); host/build/vcs rows unchanged. |
| `tests/test_memoization_wiring.py` | migrate | Drop the `_pipeline` cached-stage term (slices alone satisfy `>= 3`); the hardcoded-model-literal scan re-points from `FEATURE_PY` to `graph_nodes/*.py` + `graph.py`. |
| `tests/test_memory_purity.py` | migrate | Drop the `feature_class` fixture and its loop term; add the graph-modules scan mirroring `test_factory_purity`'s (recall/retain never called ungated). |
| `tests/test_tidyup_cli_wiring.py` | comment-only | Prose mention; the negative transport-import assertion stays trivially true. |
| `tests/replay/scenarios.py` | comment-only | Prose mentions only; drivers talk query/signal by name precisely so one scenario drives either workflow. |
| `tests/test_dashboard_fleet_marks.py` | keep | The `"FeatureWorkflow"` closed row is the legacy fixture proving marks are never asked of non-Graph rows; real exclusion behaviour (fleet.py selects `t == "GraphWorkflow"`). |
| `tests/deploy/test_deployment_workflow.py` | comment-only | Docstring prose only; pure DeploymentWorkflow tests. |
| `tests/fakes/fake_deploy.py` | comment-only | Docstring prose only. |
| `tests/graph_workflow/test_host_attribution.py` | comment-only | Docstring prose only; drives a local host composition. |
| `tests/graph_workflow/test_parent_wiring.py` | keep | The negative guard (parents never start `FeatureWorkflow.run` directly) stays a meaningful regression pin after deletion. |
| `tests/qa/test_qa_stage_judging.py` | migrate | The `_dev_task` source term re-points to `TaskHost._dev_task` (`workflows/task_host.py`) or is dropped — `stages/code/step.py` alone satisfies every assertion. |
| `tests/research/test_research_degradation.py` | comment-only | Docstring prose only; pure unit tests of research.step helpers. |
| `tests/test_benchmark_models.py` | comment-only | Docstring prose only; `BenchmarkRecord.graph` is optional and legacy-shaped records keep parsing. |
| `tests/test_dashboard_fleet_summary.py` | keep | The `"legacy-run": _Handle(wf_type="FeatureWorkflow")` fixture is the FR-015 wire-fallback case (`scripts/dump_read_fixtures.py:86` consumer); stays forever. |
| `tests/test_integration_checks_wiring.py` | migrate | The module-level `feature.py` read re-points to `graph_nodes/postplan.py` (`merge_node` delegates to `merge.step`, no direct activity calls); the MERGE_SRC AST rows and the worker row are unchanged. |
| `tests/test_memory_wiring.py` | migrate | Drop the `_pipeline` terms (slices alone satisfy `>= 3`); the stage-summary retain row re-points to the graph `StageServices` retain wiring + `precode.py`'s `ctx.retain` call. |
| `tests/test_run_state_model.py` | comment-only | One comment ("None for FeatureWorkflow runs") describes the legacy shape; optional reword only. |
| `tests/test_tidyup_workflow.py` | comment-only | Docstring prose only; the outcome-string contract is now GraphWorkflow's. |
| `tests/test_channel_inbox.py` | migrate | T024 updates it first: the query pin drops the `FeatureWorkflow` assertion (open-run types become `"GraphWorkflow", "CrewTaskWorkflow"`); the rest of the file never touches FW. |

## Known special cases (from consults; executed by T005, T020, T022, T024, T026)

- Helper imports through `sdlc.workflows.feature` (repoint, T005): `tests/plan/test_plan_validation_module.py:5` and `tests/plan/test_plan_graph_validation.py:9` become `from sdlc.stages.plan.validation import validate_task_graph` (call sites renamed); `tests/test_untraced_criteria.py:7` → `sdlc.stages.analyze.models`; `tests/merge/test_merge_gate_wiring.py:91` → `sdlc.stages.merge.step`; `tests/test_stack_contract.py:4` imports `DEFAULT_LINT_CMD` from `sdlc.stages.merge.step`; `tests/clarify/test_clarify_stage_wiring.py:30` → `sdlc.stages.architecture.step`. These five files are not part of the 76 (they import helpers only, never the class).
- `tests/review/test_adversary_workflow.py:151` (plan T051): **repoint** — `_src()` drops its `feature.py` term; `test_handoff_is_fail_open_and_never_reaches_a_validator` still finds the live `async def _run_handoff` in `stages/code/step.py` (already in the concat). Not part of the 76 (it names the path, not the type).
- Keep as-is (wire fallback for non-graph rows, FR-015): `tests/test_dashboard_fleet_summary.py:133,150`, `scripts/dump_read_fixtures.py:86`.
- Pin then drop Feature leg (T007 → T021): `tests/replay/test_graph_golden.py` memo_parity.
- Move helper (T004): `replayer()` from `tests/replay/test_feature_replay.py` to `tests/replay/harness.py` (importers: `test_feature_replay.py`, `test_benchmark_replay.py`, `test_architect_research_usage_replay.py`, `test_research_retain_replay.py`).
- Coupled outside the table: `tests/durability/test_wire_neutrality.py` (consumes `wire_dump`; re-baselined with it), `tests/test_worker_registration.py` (T025 pins the registered set without FeatureWorkflow).

## Tally (T003, must total 76)

delete 2 · migrate 46 · repoint 11 · comment-only 12 · keep 5 = **76**
