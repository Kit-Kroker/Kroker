# Test inventory (preliminary) — 020

Generated 2026-11-08 at `d57c381d` by grep. **Preliminary**: task T010 classifies every row as delete / migrate / repoint / comment-only / keep and records the GraphWorkflow counterpart for each delete. Columns: imports = lines importing `workflows.feature` or `FEATURE_STARTER`; FW = `FeatureWorkflow` mentions; GW = `GraphWorkflow` mentions.

113 files = 76 `.py` + 37 `.json` (19 FeatureWorkflow histories: the 18 `SCENARIOS` plus `research_retain_grounded`; and 18 FeatureWorkflow-captured goldens). The `.json` files are handled by T041 (re-capture), not by this table.

## A. Import FeatureWorkflow code (45)

| File | imports | FW | GW | preliminary class |
|---|---|---|---|---|
| `tests/replay/test_research_retain_replay.py` | 4 | 2 | 0 | migrate or delete |
| `tests/replay/test_capture_feature.py` | 4 | 1 | 0 | migrate or delete |
| `tests/test_model_forwarding.py` | 4 | 1 | 0 | migrate or delete |
| `tests/replay/harness.py` | 3 | 6 | 5 | migrate (drop Feature leg) |
| `tests/replay/test_graph_golden.py` | 2 | 4 | 4 | migrate (drop Feature leg) |
| `tests/durability/wire_dump.py` | 2 | 2 | 0 | migrate or delete |
| `tests/test_run_state_query.py` | 2 | 2 | 2 | migrate (drop Feature leg) |
| `tests/durability/test_priced_usage_parity.py` | 2 | 1 | 0 | migrate or delete |
| `tests/test_tool_approval_gate.py` | 1 | 19 | 0 | migrate or delete |
| `tests/retro/test_retro_stage.py` | 1 | 17 | 0 | migrate or delete |
| `tests/test_gate_notifications.py` | 1 | 14 | 0 | migrate or delete |
| `tests/integration/test_feature_host_mixins.py` | 1 | 11 | 0 | migrate or delete |
| `tests/research/test_research_e2e.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_budget_gate.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_e2e_greenfield.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_feature_brownfield_stages.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_gate_timeout_action.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_task_gate_revise_loop.py` | 1 | 11 | 0 | migrate or delete |
| `tests/test_crew_feature_wiring.py` | 1 | 9 | 0 | migrate or delete |
| `tests/test_board_workflow.py` | 1 | 8 | 0 | migrate or delete |
| `tests/deploy/test_deploy_workflow_paths.py` | 1 | 7 | 0 | migrate or delete |
| `tests/test_pending_wiring.py` | 1 | 7 | 0 | migrate or delete |
| `tests/test_run_host.py` | 1 | 7 | 1 | migrate (drop Feature leg) |
| `tests/test_feature_delta_gate.py` | 1 | 6 | 0 | migrate or delete |
| `tests/test_model_usage_capture.py` | 1 | 6 | 0 | migrate or delete |
| `tests/test_seeded_work.py` | 1 | 6 | 0 | migrate or delete |
| `tests/durability/test_first_workflow_task_time.py` | 1 | 5 | 0 | migrate or delete |
| `tests/graph_workflow/test_graph_workflow_class.py` | 1 | 5 | 7 | migrate (drop Feature leg) |
| `tests/durability/test_inflight_resume.py` | 1 | 4 | 0 | migrate or delete |
| `tests/durability/test_payload_guard_callsites.py` | 1 | 4 | 0 | migrate or delete |
| `tests/integration/test_feature_question_host.py` | 1 | 4 | 0 | migrate or delete |
| `tests/replay/test_feature_replay.py` | 1 | 4 | 0 | migrate or delete |
| `tests/test_gate_host.py` | 1 | 4 | 0 | migrate or delete |
| `tests/test_operator_e2e.py` | 1 | 4 | 0 | migrate or delete |
| `tests/test_pinned_base_e2e.py` | 1 | 4 | 0 | migrate or delete |
| `tests/integration/test_feature_stage_services.py` | 1 | 3 | 0 | migrate or delete |
| `tests/integration/test_feature_task_host.py` | 1 | 3 | 0 | migrate or delete |
| `tests/research/test_research_durability_nested.py` | 1 | 3 | 0 | migrate or delete |
| `tests/review/test_review_step_shadowing_chaos.py` | 1 | 3 | 0 | migrate or delete |
| `tests/test_dashboard_e2e.py` | 1 | 3 | 0 | migrate or delete |
| `tests/test_factory_recorder.py` | 1 | 3 | 0 | migrate or delete |
| `tests/durability/test_sandbox_module_marking.py` | 1 | 2 | 0 | migrate or delete |
| `tests/graph_workflow/test_outcome_string.py` | 1 | 2 | 0 | migrate or delete |
| `tests/test_waste_population_wiring.py` | 1 | 2 | 0 | migrate or delete |
| `tests/clarify/test_clarify_stage_wiring.py` | 1 | 1 | 0 | migrate or delete |

## B. Name the type only (31)

| File | FW | GW | preliminary class |
|---|---|---|---|
| `tests/test_factory_purity.py` | 5 | 0 | comment/string: review |
| `tests/test_inbox_query.py` | 5 | 0 | comment/string: review |
| `tests/graph_workflow/test_pipeline_child_upgrade.py` | 5 | 3 | comment/string: review |
| `tests/analyze/test_analyst_stage_wiring.py` | 3 | 0 | comment/string: review |
| `tests/test_triage_cli_wiring.py` | 3 | 0 | comment/string: review |
| `tests/test_dashboard_run_graph_routes.py` | 3 | 1 | comment/string: review |
| `tests/graph_workflow/test_cutover_wiring.py` | 3 | 6 | comment/string: review |
| `tests/fakes/fake_activities.py` | 2 | 0 | comment/string: review |
| `tests/replay/test_fixtures_present.py` | 2 | 0 | comment/string: review |
| `tests/research/test_research_stage_wiring.py` | 2 | 0 | comment/string: review |
| `tests/test_board_wiring.py` | 2 | 0 | comment/string: review |
| `tests/test_crew_gates.py` | 2 | 0 | comment/string: review |
| `tests/test_integration_branch_wired.py` | 2 | 0 | comment/string: review |
| `tests/test_memoization_wiring.py` | 2 | 0 | comment/string: review |
| `tests/test_memory_purity.py` | 2 | 0 | comment/string: review |
| `tests/test_tidyup_cli_wiring.py` | 2 | 0 | comment/string: review |
| `tests/replay/scenarios.py` | 2 | 1 | comment/string: review |
| `tests/test_dashboard_fleet_marks.py` | 2 | 4 | comment/string: review |
| `tests/deploy/test_deployment_workflow.py` | 1 | 0 | comment/string: review |
| `tests/fakes/fake_deploy.py` | 1 | 0 | comment/string: review |
| `tests/graph_workflow/test_host_attribution.py` | 1 | 0 | comment/string: review |
| `tests/graph_workflow/test_parent_wiring.py` | 1 | 0 | comment/string: review |
| `tests/qa/test_qa_stage_judging.py` | 1 | 0 | comment/string: review |
| `tests/research/test_research_degradation.py` | 1 | 0 | comment/string: review |
| `tests/test_benchmark_models.py` | 1 | 0 | comment/string: review |
| `tests/test_dashboard_fleet_summary.py` | 1 | 0 | comment/string: review |
| `tests/test_integration_checks_wiring.py` | 1 | 0 | comment/string: review |
| `tests/test_memory_wiring.py` | 1 | 0 | comment/string: review |
| `tests/test_run_state_model.py` | 1 | 0 | comment/string: review |
| `tests/test_tidyup_workflow.py` | 1 | 0 | comment/string: review |
| `tests/test_channel_inbox.py` | 1 | 1 | comment/string: review |

## Known special cases (from consults)

- Helper imports through `sdlc.workflows.feature` (repoint, not delete): `tests/plan/test_plan_validation_module.py:5`, `tests/plan/test_plan_graph_validation.py:9` → `sdlc.stages.plan.validation` (the import becomes `validate_task_graph`; `_validate_task_graph` was an alias created only in `feature.py:67`, so call sites are renamed or aliased locally); `tests/test_untraced_criteria.py:7` → `sdlc.stages.analyze.models`; `tests/merge/test_merge_gate_wiring.py:91` → `sdlc.stages.merge.step`; `tests/test_stack_contract.py:4` → `sdlc.stages.merge.step` (`DEFAULT_LINT_CMD`, `merge/step.py:66`); `tests/clarify/test_clarify_stage_wiring.py:30` → `sdlc.stages.architecture.step`. (T010 verifies each target still exports the name.)
- Keep as-is (wire fallback for non-graph rows, FR-015): `tests/test_dashboard_fleet_summary.py:133,150`, `scripts/dump_read_fixtures.py:86`.
- Keep, by name, as test stubs: `tests/graph_workflow/test_pipeline_child_upgrade.py` (`StubFeature` named `FeatureWorkflow`) — rewritten by T046 for the deprecate_patch path.
- Pin then drop Feature leg: `tests/replay/test_graph_golden.py:112` memo_parity.
- Move helper: `replayer()` from `tests/replay/test_feature_replay.py` to `tests/replay/harness.py` (importers: `test_benchmark_replay.py`, `test_architect_research_usage_replay.py`, `test_research_retain_replay.py`).
