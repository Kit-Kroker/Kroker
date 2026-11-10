# Skeptic brief 1 — 020 delete FeatureWorkflow (spec: .specify/specs/020-delete-featureworkflow/spec.md)

Pressure-test the LOCKED decisions below. For each: the strongest concrete failure scenario (inputs/state -> wrong outcome), how likely, and what the plan must add to close it. Cite file:line. Write your answer to .specify/specs/020-delete-featureworkflow/skeptic-answer-1.md; edit nothing else.

L1 Q1=A: closed FeatureWorkflow runs are listed from visibility metadata only; no run_summary/run_state query is sent to them (src/sdlc/dashboard/fleet.py _fetch_closed/_fetch_marks).
L2 Q2=A: gate query 2 requires zero Running TidyUpWorkflow/BenchmarkWorkflow of ANY start time; query 1 zero Running FeatureWorkflow. Re-run before deletion and again right before deploying the worker that drops the type. No override.
L3 FR-006: _revisable_stage / StageServices.revisable_stage stay (GraphWorkflow uses them, workflows/graph.py:74).
L4 FR-007: architecture/plan step() composites are deleted (only FeatureWorkflow calls them); prepare/produce/finish stay.
L5 FR-011: goldens kept and re-baselined from GraphWorkflow; any commands/close diff is a STOP.
L6 FR-015: no wire-contract field removed (RunState/RunSummary optional None-for-legacy fields stay).
L7 Rollback is roll-forward only.

Specifically look for: other workflows or activities that start/query/signal FeatureWorkflow by NAME (string), schedules, the CLI (`sdlc` commands like status/answer/gate that take a run id and may query a closed or open FeatureWorkflow), dashboard routes (run_graph.py, read_routes.py, api.py) that query any run handle, and DeploymentWorkflow/CrewTaskWorkflow parents or children whose parent is a FeatureWorkflow.
