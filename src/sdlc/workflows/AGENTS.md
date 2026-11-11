# `src/sdlc/workflows/` — Attribute-Ownership Table

Attributes on the MRO of `GraphWorkflow` across its service-host mixins.
(020: the legacy workflow is deleted; every row it owned below was
re-homed to `GraphWorkflow`.)

## Rules of MRO Attribute Ownership

1. **Every attribute has exactly one owning host.** Only the owning host's `__init__` may instantiate it.
2. **Only the owning host may write an attribute**, unless explicitly documented below as a cross-host mutation.
3. **Cross-host readers are permitted** through the MRO (`self.<attr>`), but must be recorded here to prevent accidental coupling.
4. **No handlers on mixins — one blessed exception.** Signal and query handlers live on the concrete workflow class (`GraphWorkflow`) or `GateHost`. `QuestionHost.answer_question` is the sanctioned exception (spec A §3.1's own design: the signal and the wait are one service). Its handler name is a wire contract; never rename it.

## Attribute Ownership

| Attribute | Owning Host | Readers | Writers | Notes |
|---|---|---|---|---|
| `_gate_decisions` | `GateHost` | `GateHost`, `GraphWorkflow.run_state`, `GraphWorkflow.run_summary` | `GateHost.submit_gate_decision` | Map of `gate_key -> GateDecision` |
| `_pending` | `GateHost` | `GateHost.pending_decisions`, `GraphWorkflow` | `GateHost._gate`, `GraphWorkflow.answer_question` (pops clarify question) | Map of `gate_key -> PendingDecision` |
| `_parent_run_id` | `GateHost` | `GateHost._gate` | `GateHost.__init__` | Optional parent run ID for hierarchy |
| `_trace` | `ReportHost` | `ReportHost`, `GraphWorkflow.run_state`, `GraphWorkflow.run_summary` | `ReportHost._emit` | Append-only event trace |
| `_seq` | `ReportHost` | `ReportHost` | `ReportHost._emit` | Monotonic event sequence counter |
| `_status` | `ReportHost` | `ReportHost._stage`, `GateHost._gate`, `QuestionHost.ask_and_wait`, `GraphWorkflow.status`, `GraphWorkflow.pending_gate`, `GraphWorkflow.run_state` | `ReportHost._stage`, `GateHost._gate` | High-level status string (`awaiting:*`, etc.). `GateHost` queries read via `getattr(..., "starting")` so GateHost-only hosts (crew, triage, assessment, tidyup) work without ReportHost. |
| `_role_usage` | `ReportHost` | `ReportHost`, `RoleHost`, `GraphWorkflow.run_state`, `GraphWorkflow.run_summary`, `RunHost._snapshot_run_state` | `ReportHost._track_usage` | Per-role accumulated token and cost usage |
| `_plan_version` | `BoardHost` | `BoardHost._board_task_status`, `BoardHost._board_evidence`, `GraphWorkflow` (plan stage) | `BoardHost._board_publish` returns it; `GraphWorkflow` stores it (plan stage) | Surrogate version ID of the published plan |
| `_question_answers` | `QuestionHost` | `QuestionHost.ask_and_wait`, `QuestionHost.answer_question`, `GraphWorkflow` (clarify flag-off branch reads it for `answered_by`) | `QuestionHost.answer_question` | Clarify Q&A map |
| `_pending_questions` | `QuestionHost` | `QuestionHost.ask_and_wait` | `QuestionHost.ask_and_wait` | List of open question IDs currently awaiting answers |
| `_memory_watermark` | `MemoryHost` | `MemoryHost._recall`, `GraphWorkflow` | `GraphWorkflow` | Watermark for memory capture |
| `_session_refs` | `TaskHost` | `TaskHost._dev_task`, `GraphWorkflow` (retro) | `TaskHost._dev_task` | Coding attempt session references |
| `_cfg` | `RunHost` | `GraphWorkflow`, `GateHost._notify`, `RunHost._snapshot_run_state` (reads `project_key`) | `GraphWorkflow.run` | Stashed pipeline config for queries/hooks. `GateHost._notify` reads `project_key` via `getattr(self, "_cfg", None)` for F4 artifact links, so GateHost-only hosts (crew, triage, assessment, tidyup) send no link. `RunHost._snapshot_run_state` reads `project_key` the same guarded way (002 G4: the run wire carries it for the board tab). |
| `_idea` | `RunHost` | `RunHost._snapshot_run_state` | `GraphWorkflow.run` | Stashed initial idea brief |
| `_started_at` | `RunHost` | `RunHost._snapshot_run_state`, `GraphWorkflow.run_summary` | `GraphWorkflow.run` | Run start timestamp |
| `_run_id` | `RunHost` | `GraphWorkflow` | `GraphWorkflow.run` | Stashed run ID for offline unit tests |
| `_run_summary` | `RunHost` | `GraphWorkflow.run_summary`, `RunHost._retro` | `GraphWorkflow` | Terminal `RunSummary`, built once at end of run |
| `_integration_head` | `GraphWorkflow` | `GraphWorkflow` (precode's setup/context nodes) | `GraphWorkflow` | Current commit on integration branch (020: re-homed from the deleted legacy workflow) |
| `_base_sha` | `GraphWorkflow` | `GraphWorkflow` (integration diff, `merge.step`) | `GraphWorkflow.run` (once, at setup) | Setup head of the integration branch, pinned as the merge gate's baseline (diff-scoped gates DS2); distinct from the advancing `_integration_head` |
| `_integration_wt` | `GraphWorkflow` | `GraphWorkflow` (precode's setup node; the merge gate reads it) | `GraphWorkflow` | Path to task integration worktree (020: re-homed) |
| `_budget_threshold` | `RoleHost` | `RoleHost._check_budget`, `GraphWorkflow`, `RunHost._snapshot_run_state` | `RoleHost._check_budget` | Budget threshold dollar amount |
| `_budget_crossings` | `RoleHost` | `RoleHost._check_budget`, `GraphWorkflow.run_state`, `RunHost._snapshot_run_state` | `RoleHost._check_budget` | Number of budget alert crossings |
| `_escalation_round`| *Eliminated* (Rule 2) | None (per-task local in `TaskHost._dev_task`) | None | Formerly instance counter, now local to prevent wave-mode races |
| `_codebase_map` | `GraphWorkflow` | `GraphWorkflow` (precode's context node sets it; the architect node reads it) | `GraphWorkflow` | Brownfield codebase map cache (020: re-homed) |
| `_activation_spend` | `ReportHost` | `GraphWorkflow.graph_view` | `ReportHost._track_usage` | E-75: priced spend per graph activation id, `(sum, all_priced)`; keyed by `ACTIVATION` |
| `_unattributed_spend` | `ReportHost` | tests (spend invariant) | `ReportHost._track_usage` | E-75: spend outside any activation (preamble, retro) |
| `_pending_activation` | `GateHost` | `GateHost._pending_facts` | `GateHost._gate`, `GateHost.submit_gate_decision`, `QuestionHost.ask_and_wait`, `QuestionHost.answer_question` (cross-host, via `getattr`) | E-75: pending key → opening activation id; joined onto `_pending`, never iterated alone |
| `_graph`, `_graph_sha`, `_dispatcher`, `_result` | `GraphWorkflow` | `GraphWorkflow.graph_view`, `GraphWorkflow.run_state` | `GraphWorkflow.run` | E-75: pinned graph, its sha, the live dispatcher, the return string (set after retro) |
| `_attrib` (on `GraphDispatcher`) | `GraphDispatcher` | `GraphWorkflow._stamp` | `GraphDispatcher._start` (the only write site, pinned by test) | E-77: per-activation attribution facts — node_id, round, node_stage, fail_reentry; memory only, no commands (FR-025) |
| `BenchmarkHost._record` override | `GraphWorkflow` (override) | — | `GraphWorkflow._record` (stamps via `_stamp`, then `super()._record`) | E-77 R-4: every record carries `GraphAttribution` before emit/schedule; base host behaviour unchanged |
| `_graph_sha` (new cross-host reader) | `GraphWorkflow` | `RunHost._retro` (cross-host, via `getattr(self, "_graph_sha", "") or None` → `build_run_summary`) | `GraphWorkflow.run` (unchanged) | E-77 R-3: summary content only — no command change (U6) |
| `_emit` (new cross-host reader) | `ReportHost` | `MemoryHost._recall` (cross-host, via `getattr(self, "_emit", None)` — a no-op when absent, so MemoryHost-only hosts: crew, triage, assessment, tidyup) | `ReportHost._emit` (unchanged) | 021 FR-011: after each stage-level recall it emits `MEMORY_RECALLED` — hash, uri, degraded/persist_failed flags, never items; pure state, no command |

## Single model egress: forwarding and the label guard (004)

`RoleHost._run_role` is the E-33 single model-egress point. Since 004 it
also FORWARDs the run's proposer override: when
`sdlc.agents.model_ids.forwarded_model(cfg, role)` is not `None`, the call
is made as `agent.run(*args, model=<forwarded>, **kwargs)` — only then. A
caller's `model` label that disagrees with what would be forwarded under an
override fails the call non-retryably before any model request (FR-002);
`model` is `_run_role`'s own positional parameter, so a caller-supplied
`model=` kwarg cannot reach `agent.run` at all. No-override and
override-equals-registry runs call exactly as before (E1), which is why
no-override replays stay byte-identical. `_cached_stage` salts the memo
key's model slot `fwd1:<model>` when the run's model differs from the
registry model (FR-003/E3); `content_key`'s signature is unchanged.

Since architect-research-surface, `_run_role` also harvests sub-run usage
reports: a tool that ran a model inside its own activity hands the usage
back as `ToolReturn` metadata under `sub_run_usage.SUB_RUN_USAGE_KEY`;
after the role's own usage is tracked, `_run_role` prices the reports once
per answering model and tracks them under role `research` (`into=None`),
then adds the spend to the caller's bag with `add_spend`, never
`merge_usage`. A run with no report schedules nothing extra, which is why
this needs no `workflow.patched` marker.

## The proposer payload guard (007)

The proposer payload guard lives in `src/sdlc/agents/payload_guard.py`
and is attached to every durable agent by the loader
(`build_agents`' durable path hands each role
`[durability, single_retry_layer(), payload_guard()]`) and to the two
clarify fan-out agents in `roles.py`; the worker refuses to boot a
durable agent without it (`worker.get_worker_activities`). It checks
each model request in workflow code BEFORE it is scheduled: over
`PROPOSER_PAYLOAD_LIMIT_BYTES` (1 MiB) it raises the non-retryable
`ApplicationError` of type `ProposerPayloadTooLarge`, so each call site
takes the failure path it already has. It is inert inside activities.
The `workflow.patched` marker (`GUARD_PATCH_ID`) is taken only on the
failing branch, so an under-limit run schedules exactly the commands it
always did and stays replay-identical; `GUARD_PATCH_ID` is a wire name
(recorded in histories) and is never renamed. Two things it does not
cover: the combined size of parallel requests in one workflow task, and
agents run inside activities.

## Recall snapshots (021)

FR-402 persists every stage-level recall as a content-addressed
`recall_snapshot` artifact. Persistence lives INSIDE the existing
`recall_snapshot` activity (`memory/activities.py::_persisted`), next to
the scrub and the hash: no activity is added or removed and no workflow
command changes, which is why there is no `workflow.patched` marker
anywhere in this round — the workflow side only reads `snapshot_hash` and
`ref` off the recorded result and passes the hash into `_cached_stage`'s
`recall_ref`.

The new `RecallSnapshot` fields (`snapshot_hash`, `ref`,
`persist_failed`) are defaulted, and a `model_validator` fills
`snapshot_hash` from the other fields: a pre-021 recorded activity
result therefore deserializes unchanged (E-1 — defaulted payload fields
do not alter the command sequence), replay takes the recorded result and
never re-queries memory, and `RecallInput.run_id` is an input field,
which Temporal does not compare on replay. The memo key's fifth slot
moving from `wm` to `wm|<hash>` changes a cache INPUT, not a command:
one-time cache misses on in-flight replays are the accepted ADR-5 cost.

`recall_snapshot/v1` (memory/query_hash.py `SNAPSHOT_TAG`) is a wire
tag recorded in persisted artifacts: it is never changed in place — any
change to the canonical form bumps the tag (contract §4).
