# `src/sdlc/workflows/` — Attribute-Ownership Table

Attributes on the MRO of `FeatureWorkflow` and `GraphWorkflow` across its service-host mixins.

## Rules of MRO Attribute Ownership

1. **Every attribute has exactly one owning host.** Only the owning host's `__init__` may instantiate it.
2. **Only the owning host may write an attribute**, unless explicitly documented below as a cross-host mutation.
3. **Cross-host readers are permitted** through the MRO (`self.<attr>`), but must be recorded here to prevent accidental coupling.
4. **No handlers on mixins — one blessed exception.** Signal and query handlers live on the concrete workflow class (`FeatureWorkflow`, `GraphWorkflow`) or `GateHost`. `QuestionHost.answer_question` is the sanctioned exception (spec A §3.1's own design: the signal and the wait are one service). Its handler name is a wire contract; never rename it.

## Attribute Ownership

| Attribute | Owning Host | Readers | Writers | Notes |
|---|---|---|---|---|
| `_gate_decisions` | `GateHost` | `GateHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `GateHost.submit_gate_decision` | Map of `gate_key -> GateDecision` |
| `_pending` | `GateHost` | `GateHost.pending_decisions`, `FeatureWorkflow` | `GateHost._gate`, `FeatureWorkflow.answer_question` (pops clarify question) | Map of `gate_key -> PendingDecision` |
| `_parent_run_id` | `GateHost` | `GateHost._gate` | `GateHost.__init__` | Optional parent run ID for hierarchy |
| `_trace` | `ReportHost` | `ReportHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `ReportHost._emit` | Append-only event trace |
| `_seq` | `ReportHost` | `ReportHost` | `ReportHost._emit` | Monotonic event sequence counter |
| `_status` | `ReportHost` | `ReportHost._stage`, `GateHost._gate`, `QuestionHost.ask_and_wait`, `FeatureWorkflow.status`, `FeatureWorkflow.pending_gate`, `FeatureWorkflow.run_state` | `ReportHost._stage`, `GateHost._gate` | High-level status string (`awaiting:*`, etc.). `GateHost` queries read via `getattr(..., "starting")` so GateHost-only hosts (crew, triage, assessment, tidyup) work without ReportHost. |
| `_role_usage` | `ReportHost` | `ReportHost`, `RoleHost`, `FeatureWorkflow.run_state`, `FeatureWorkflow.run_summary` | `ReportHost._track_usage` | Per-role accumulated token and cost usage |
| `_plan_version` | `BoardHost` | `BoardHost._board_task_status`, `BoardHost._board_evidence`, `FeatureWorkflow` (plan stage) | `BoardHost._board_publish` returns it; `FeatureWorkflow` stores it (plan stage, `:2972`) | Surrogate version ID of the published plan |
| `_question_answers` | `QuestionHost` | `QuestionHost.ask_and_wait`, `QuestionHost.answer_question`, `FeatureWorkflow` (clarify flag-off branch reads it for `answered_by`) | `QuestionHost.answer_question` | Clarify Q&A map |
| `_pending_questions` | `QuestionHost` | `QuestionHost.ask_and_wait` | `QuestionHost.ask_and_wait` | List of open question IDs currently awaiting answers |
| `_memory_watermark` | `MemoryHost` | `MemoryHost._recall`, `FeatureWorkflow` | `FeatureWorkflow` | Watermark for memory capture |
| `_session_refs` | `TaskHost` | `TaskHost._dev_task`, `FeatureWorkflow` (retro) | `TaskHost._dev_task` | Coding attempt session references |
| `_cfg` | `RunHost` | `FeatureWorkflow`, `GateHost._notify`, `RunHost._snapshot_run_state` (reads `project_key`) | `FeatureWorkflow.run`, `GraphWorkflow.run` | Stashed pipeline config for queries/hooks. `GateHost._notify` reads `project_key` via `getattr(self, "_cfg", None)` for F4 artifact links, so GateHost-only hosts (crew, triage, assessment, tidyup) send no link. `RunHost._snapshot_run_state` reads `project_key` the same guarded way (002 G4: the run wire carries it for the board tab). |
| `_idea` | `RunHost` | `RunHost._snapshot_run_state` | `FeatureWorkflow.run` | Stashed initial idea brief |
| `_started_at` | `RunHost` | `RunHost._snapshot_run_state`, `FeatureWorkflow.run_summary` | `FeatureWorkflow.run` | Run start timestamp |
| `_run_id` | `RunHost` | `FeatureWorkflow` | `FeatureWorkflow.run` | Stashed run ID for offline unit tests |
| `_run_summary` | `RunHost` | `FeatureWorkflow.run_summary`, `RunHost._retro` | `FeatureWorkflow` | Terminal `RunSummary`, built once at end of run |
| `_integration_head` | `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Current commit on integration branch |
| `_base_sha` | `FeatureWorkflow` | `FeatureWorkflow` (integration diff, `merge.step`) | `FeatureWorkflow.run` (once, at setup) | Setup head of the integration branch, pinned as the merge gate's baseline (diff-scoped gates DS2); distinct from the advancing `_integration_head` |
| `_integration_wt` | `TaskHost` (in P1) / `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Path to task integration worktree |
| `_budget_threshold` | `RoleHost` | `RoleHost._check_budget`, `FeatureWorkflow` | `RoleHost._check_budget` | Budget threshold dollar amount |
| `_budget_crossings` | `RoleHost` | `RoleHost._check_budget`, `FeatureWorkflow.run_state` | `RoleHost._check_budget` | Number of budget alert crossings |
| `_escalation_round`| *Eliminated* (Rule 2) | None (per-task local in `TaskHost._dev_task`) | None | Formerly instance counter, now local to prevent wave-mode races |
| `_codebase_map` | `FeatureWorkflow` | `FeatureWorkflow` | `FeatureWorkflow` | Brownfield codebase map cache |
| `_activation_spend` | `ReportHost` | `GraphWorkflow.graph_view` | `ReportHost._track_usage` | E-75: priced spend per graph activation id, `(sum, all_priced)`; keyed by `ACTIVATION`; empty on FeatureWorkflow |
| `_unattributed_spend` | `ReportHost` | tests (spend invariant) | `ReportHost._track_usage` | E-75: spend outside any activation (preamble, retro) |
| `_pending_activation` | `GateHost` | `GateHost._pending_facts` | `GateHost._gate`, `GateHost.submit_gate_decision`, `QuestionHost.ask_and_wait`, `QuestionHost.answer_question` (cross-host, via `getattr`) | E-75: pending key → opening activation id; joined onto `_pending`, never iterated alone |
| `_graph`, `_graph_sha`, `_dispatcher`, `_result` | `GraphWorkflow` | `GraphWorkflow.graph_view`, `GraphWorkflow.run_state` | `GraphWorkflow.run` | E-75: pinned graph, its sha, the live dispatcher, the return string (set after retro) |
| `_attrib` (on `GraphDispatcher`) | `GraphDispatcher` | `GraphWorkflow._stamp` | `GraphDispatcher._start` (the only write site, pinned by test) | E-77: per-activation attribution facts — node_id, round, node_stage, fail_reentry; memory only, no commands (FR-025) |
| `BenchmarkHost._record` override | `GraphWorkflow` (override) | — | `GraphWorkflow._record` (stamps via `_stamp`, then `super()._record`) | E-77 R-4: every record carries `GraphAttribution` before emit/schedule; base host behaviour unchanged |
| `_graph_sha` (new cross-host reader) | `GraphWorkflow` | `RunHost._retro` (cross-host, via `getattr(self, "_graph_sha", "") or None` → `build_run_summary`) | `GraphWorkflow.run` (unchanged) | E-77 R-3: summary content only — no command change (U6) |

## Grace edits while FeatureWorkflow is registered (E-74 U6)

`FeatureWorkflow` stays registered only to carry in-flight runs to terminal
state (PRD OQ-10 grace-retention). Until it is deleted, any edit that changes
the COMMAND SEQUENCE of code it executes (stage steps, hosts, `build.run_tasks`,
`run_host.py`) must be wrapped in `workflow.patched("<epic>-<slug>")`.
`tests/replay/test_feature_replay.py` is the enforcement: its histories are
never re-recorded to make an edit pass. After deletion, intentional golden
changes re-baseline from GraphWorkflow with the projection diff attached to
the review.
