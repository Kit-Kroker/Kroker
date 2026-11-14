# Contract — maintenance workflow wire (023a)

These names are recorded in Temporal histories and live Schedules. **Never rename** them once shipped.

## Workflows

| Class | Id | Input | Returns |
|---|---|---|---|
| `MaintenanceWorkflow` | `maint-<project>` | `MaintenanceState` | `str`: `disabled:<project>` |
| `MaintenanceKickWorkflow` | `sched-<asset-id>` (+ server time suffix) | `MaintenanceKickInput{project: str}` | `str`: `nudged:<project>` \| `not-enabled:<project>` |
| child `TriageWorkflow` | `maint-<project>-c<cycle>-triage` | `TriageInput` (existing, unchanged) | `RepoTriage` |

Both new classes are registered in `worker.py`'s `workflows=[...]`.

Starting `maint-<project>` while it is running is refused (`WorkflowAlreadyStartedError`), and the CLI renders this as "already enabled".

## Signals on `MaintenanceWorkflow`

| Name | Payload | Effect |
|---|---|---|
| `nudge` | none | sets `_nudged` (R2) |
| `disable` | none | sets `_disabling` (R15) |
| `submit_gate_decision` | `GateDecision` | inherited from `GateHost`; unchanged |

## Queries

| Name | Returns |
|---|---|
| `incidents` | `list[Incident]` |
| `maintenance_state` | `MaintenanceSummary{project, cycle, baseline_recorded: bool, running_cycle: bool, open_gates: int, not_collected_streak, ack_unattended_build_probe}` |
| `pending_decisions` | inherited from `GateHost` (inbox) |

## Gate names

- `repair:<incident_no>`: SOFT, built by `repair_gate_settings`.
- `detect_escalation:<signal>:<incident_no>`: HARD, on timeout REJECT.

Round is always 1. There is no REVISE path in 023a: a REVISE outcome is treated as reject and the guidance is recorded in `note`.

## Schedule asset (`schedules/<id>.yaml`)

```yaml
spec:
  cron: "0 4 * * *"      # minute field must be a single integer (>= hourly)
  timezone: UTC
action:
  workflow: MaintenanceKickWorkflow
  project: <project>
```

`ReflectWorkflow` assets are unchanged (`workflow: ReflectWorkflow`, `banks`, `backend`, `base_url`).

## Determinism notes (for `src/sdlc/workflows/AGENTS.md` rows)

- `MaintenanceWorkflow` owns these new attributes: `_state`, `_nudged`, `_disabling`, `_running`, `_gate_tasks`.
- It is a GateHost-only host, like crew, triage, assessment and tidyup. It has no `ReportHost` and no `_cfg`, so `_notify` sends no artifact link.
- The `t_maintainer.run(...)` call is the durable agent's activity, so the payload guard (007) applies.
