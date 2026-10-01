# Data Model: 003 durability migration

No runtime data model changes. These are the entities the plan and tests introduce or rely on.

## DurableAgent (16)

| Field | Source | Rule |
|---|---|---|
| `role` | registry folder name (14) or inline name (2 fan-out) | unique |
| `name` | asset `Agent(name=...)`, `# NEVER rename` | byte-identical to today (FR-002); also the activity-name prefix; collision = `RegistryError` |
| `capabilities` | passed by loader (`[TemporalDurability]`) then the asset's own | durability first/outermost; exactly one `TemporalDurability` |
| `activity_config` | `AGENT_ACTIVITY_CONFIG` (10 min, 3 attempts) or `CLARIFY_FANOUT_ACTIVITY_CONFIG` | bounded retry (FR-013); never unbounded |
| `model_activity_config` | `{"heartbeat_timeout": None}` | keeps the command `heartbeat_timeout` = 0 (FR-019) |
| optional | present iff `agents/<role>/` ships | 6 roles; `t_*` is `None` when absent |

Relationships: `STAGE_ROLES` maps stage -> role; `ALL_TEMPORAL_AGENTS` lists present agents; worker registers `from_agent(a).temporal_activities` for each.

## PreMigrationFixture (`tests/replay/fixtures/agent_activities_pre_migration.json`, new, frozen on main 203e7dd)

```text
agents[<agent name>] = {
  toolset_ids: [str],
  registered:  [activity names],
  scheduled:   [activity names a workflow schedules],
  model_command: {start_to_close_s, heartbeat_s (0), max_attempts, non_retryable: [str], arg_count}
}
expected_registered_delta = { removed: [event_stream_handler], added: [model_compact_messages, toolset__<agent>__validate_args] }
```

Rules: dumped on unmodified main before Phase B; never generated at test time from the code under test; edits forbidden after Phase A (FR-006, FR-019).

## CapturedHistory (new, `tests/replay/histories/`)

`architect_research_tool`, `clarify_fanout`, `assessment_discover_risk`. Read-only evidence; same SG-2 rule as the existing 16.

## FR020Outcome (recorded in research.md at Phase D)

`{hypothesis a-e, status: verified-neutral | mitigated | ruled | escalated, evidence: test id, date}`.

## State transitions

None at runtime. Process order: A (capture) -> B (contract) -> C (migration) -> D (proofs) -> E (docs); Phase A artifacts must exist and be committed before Phase B changes production code.
