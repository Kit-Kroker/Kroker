# `src/sdlc/workflows/` — Attribute-Ownership Table

Attributes on `FeatureWorkflow`'s MRO across its service-host mixins.

## Rules of MRO Attribute Ownership

1. **Every attribute has exactly one owning host.** Only the owning host's `__init__` may instantiate it.
2. **Only the owning host may write an attribute**, unless explicitly documented below as a cross-host mutation.
3. **Cross-host readers are permitted** through the MRO (`self.<attr>`), but must be recorded here to prevent accidental coupling.
4. **No handlers on mixins.** Signal and query handlers live on `FeatureWorkflow` or `GateHost` (wire contract stability).

## Attribute Ownership

| Attribute | Owning Host | Readers | Writers | Notes |
|---|---|---|---|---|
| `_gate_decisions` | `GateHost` | `GateHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `GateHost.submit_gate_decision` | Map of `gate_key -> GateDecision` |
| `_pending` | `GateHost` | `GateHost.pending_decisions`, `FeatureWorkflow` | `GateHost._gate`, `FeatureWorkflow.answer_question` (pops clarify question) | Map of `gate_key -> PendingDecision` |
| `_parent_run_id` | `GateHost` | `GateHost._gate` | `GateHost.__init__` | Optional parent run ID for hierarchy |
| `_trace` | `ReportHost` | `ReportHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `ReportHost._emit` | Append-only event trace |
| `_seq` | `ReportHost` | `ReportHost` | `ReportHost._emit` | Monotonic event sequence counter |
| `_status` | `ReportHost` | `ReportHost._stage`, `GateHost._gate`, `FeatureWorkflow.status`, `FeatureWorkflow.pending_gate`, `FeatureWorkflow.run_state` | `ReportHost._stage`, `GateHost._gate`, `FeatureWorkflow` (clarify block sets `awaiting:clarify` directly) | High-level status string (`awaiting:*`, etc.). `GateHost` queries read via `getattr(..., "starting")` so GateHost-only hosts (crew, triage, assessment, tidyup) work without ReportHost. |
| `_role_usage` | `ReportHost` | `ReportHost`, `RoleHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `ReportHost._track_usage` | Per-role accumulated token and cost usage |
| `_plan_version` | `BoardHost` | `BoardHost._board_task_status`, `BoardHost._board_evidence`, `FeatureWorkflow` (plan stage) | `BoardHost._board_publish` returns it; `FeatureWorkflow` stores it (plan stage, `:2972`) | Surrogate version ID of the published plan |
| `_question_answers` | `QuestionHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow.answer_question`, `FeatureWorkflow.questions` | `FeatureWorkflow.answer_question` | Clarify Q&A map |
| `_memory_watermark` | `MemoryHost` | `MemoryHost._recall`, `FeatureWorkflow` | `FeatureWorkflow` | Watermark for memory capture |
| `_session_refs` | `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Coding attempt session references |
| `_cfg` | `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow.run` | Stashed pipeline config for queries/hooks |
| `_idea` | `FeatureWorkflow` | `FeatureWorkflow.run_state` | `FeatureWorkflow.run` | Stashed initial idea brief |
| `_started_at` | `FeatureWorkflow` | `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `FeatureWorkflow.run` | Run start timestamp |
| `_run_id` | `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow.run` | Stashed run ID for offline unit tests |
| `_run_summary` | `FeatureWorkflow` | `FeatureWorkflow.run_summary`, `FeatureWorkflow` (retro) | `FeatureWorkflow` | Terminal `RunSummary`, built once at end of run |
| `_integration_head` | `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Current commit on integration branch |
| `_integration_wt` | `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Path to task integration worktree |
| `_budget_threshold` | `RoleHost` | `RoleHost._check_budget`, `FeatureWorkflow` | `RoleHost._check_budget` | Budget threshold dollar amount |
| `_budget_crossings` | `RoleHost` | `RoleHost._check_budget`, `FeatureWorkflow.run_state` | `RoleHost._check_budget` | Number of budget alert crossings |
| `_escalation_round`| `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Tool-approval escalation counter |
| `_codebase_map` | `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Brownfield codebase map cache |
