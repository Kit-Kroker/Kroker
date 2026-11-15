# Data model — round 023b

These are additive changes to `S/maintenance/models.py` (023a, `.specify/specs/023-daper-maintenance-loop/data-model.md`). Every new field has a default, so a 023a `MaintenanceState` payload validates unchanged (research R7, pinned by a captured fixture).

## `MaintenanceConfig` (additions, R10/R14)

| Field | Type | Constraint | Default |
|---|---|---|---|
| `execute` | `bool` | — | `False` |
| `max_starts_per_cycle` | `int` | `ge=1, le=3` | `1` |
| `max_starts_per_window` | `int` | `ge=1, le=10` | `3` (rolling 7 days) |
| `max_reopens` | `int` | `ge=0, le=2` (code ceiling, GATE 1 Q3) | `2` |
| `child_timeout_hours` | `int` | `ge=1, le=168` | `24` |

Model validator: `execute=True` requires `ack_unattended_build_probe=True` and `build_probe=True` (R14).

There is still **no** gate, policy or on-timeout field (023a R9, B-FR-019).

## `IncidentState` (additions, R7)

| State | Terminal | Meaning |
|---|---|---|
| `approved` | no | The gate approved, and execution is enabled. It waits for Execute |
| `queued` | no | Approved, held by a cap or a path overlap. It keeps its approval |
| `executing` | no | A child has started, with an execution record |
| `verifying` | no | The child is at its merge gate, and Report is running or waiting on a collected re-detect |
| `verified` | no | A collected re-detect on the verification branch read `RESOLVED` |
| `reopened` | no | A dirty verdict under the bound. It is re-planned next cycle |
| `closed` | **yes** | Verified, the identity is absent on a collected default-branch Detect, and the child head is reachable from it |

The 023a states keep their meaning:
- `approved_not_executed` is terminal and is used only when `execute=False`.
- `deferred` keeps its 023a meaning, which is not the capped state.
- `TERMINAL_INCIDENT_STATES` gains only `closed`.

## `Incident` (additions)

| Field | Type | Default | Notes |
|---|---|---|---|
| `consecutive_seen` | `int` | `1` | Collected PERSISTED → +1. NEW → 1. Not-collected for its signal → 0. Tracked only when `execute` is on. Used only by the Execute guard (R6, R9) |
| `attempt` | `int` | `0` | Incremented in the same step as a child start (R1) |
| `reopens` | `int` | `0` | Moved only by `apply_verdict` (R11). Passed to `confidence_floor` |
| `gate_round` | `int` | `1` | The round of the next `repair:<n>` gate. It increments when a refusal (R6) or a reopen needs a new decision. In 023a it is always 1 |
| `execution` | `ExecutionRecord \| None` | `None` | The current attempt. History is kept in `executions` |
| `executions` | `list[ExecutionRecord]` | `[]` | Bounded by `max_reopens + 1` |
| `verification` | `VerificationResult \| None` | `None` | The latest attempt's verdict |
| `retained` | `bool` | `False` | Set in the same step as the retention activity (R13) |

`plan_attempts` keeps its 023a meaning: analysis failures, not executions.

## `ExecutionRecord` (NEW)

| Field | Type | Notes |
|---|---|---|
| `attempt` | `int` | 1-based |
| `child_id` | `str` | `maint-{project}-{run8}-inc{no}-a{attempt}` (R1) |
| `base_sha` | `str` | `incident.commit_sha` at start. Passed as `IdeaBrief.base_branch` (R3) |
| `started_at` | `datetime` | `workflow.now()` |
| `integration_branch` | `str \| None` | From the probe (R2) |
| `integration_head` | `str \| None` | From the probe, when the child is `awaiting_merge`. Used for closure (R8) |
| `outcome` | `Literal["running","awaiting_merge","failed","config_failed","timed_out","empty_diff","rejected_by_loop","completed"]` | |
| `detail` | `str` | Bounded at 300 chars |

## `VerificationResult` (NEW)

| Field | Type | Notes |
|---|---|---|
| `child_id` | `str` | Also the verify ref key: `sdlc/tidyup-verify/<child_id>` |
| `base_sha` / `verify_head` | `str` | |
| `collected` | `bool` | The identity's signal was collected on both base and verify |
| `verdict` | `Literal["resolved","persisted","new","unverifiable","conflicted","absent_at_base"]` | |
| `delta_note` | `str` | |

## `ChildProbe` (NEW, activity result, R2)

`phase`, `pending_merge_round: int | None`, `integration_branch: str | None`, `integration_head: str | None`, `result: str | None`, `failure: str | None`, `non_retryable: bool`.

## `MaintenanceState` (additions)

| Field | Type | Default | Notes |
|---|---|---|---|
| `exec_starts` | `list[datetime]` | `[]` | Pruned to 7 days at Execute (R10) |

The validator is unchanged. Non-terminal key uniqueness now also covers the new live states.

## `MemoryKind` (additions, R13)

`INCIDENT_LESSON = "incident_lesson"` (only for `closed`) and `INCIDENT_EXPERIENCE = "incident_experience"` (every other terminal state).

## Transitions (execute enabled; R7, R8, R11)

| From | Event | To |
|---|---|---|
| `awaiting_decision` | gate APPROVE (human, or policy per 023a) | `approved` |
| `approved` / `queued` | Detect: identity RESOLVED on the default branch | `resolved_externally` |
| `approved` / `queued` | Execute: `may_execute` refuses | `awaiting_decision` (`gate_round += 1`; this round is human-only, with no auto-decision; the operator is notified) |
| `approved` / `queued` | Execute: a cap or overlap | `queued` |
| `approved` / `queued` | Execute: start (or already attached) | `executing` (`attempt += 1`, `exec_starts += now`) |
| `executing` | probe `awaiting_merge` | `verifying` |
| `executing` | probe failed / empty diff / timed out | dirty → `reopened` or `escalated` |
| `executing` | probe failed, non-retryable | `escalated` |
| `verifying` | verdict `resolved`, collected | `verified` |
| `verifying` | verdict `unverifiable`, or not collected | `verifying` (retried next cycle; bounded by `child_timeout_hours`, then dirty) |
| `verifying` | verdict persisted / new / conflicted | the loop REJECTs the child's merge → dirty |
| `verifying` | verdict `absent_at_base` | `resolved_externally` |
| `verified` | collected default-branch Detect, identity absent, `is_ancestor` true | `closed` |
| `verified` | collected default-branch Detect, identity absent, `is_ancestor` false | `resolved_externally` |
| `verified` | collected default-branch Detect, identity present, `is_ancestor` true (the fix is on the default branch and did not hold) | dirty |
| `reopened` | next cycle | re-plan → `awaiting_decision` (the gate at `gate_round`, human-only) |
| `verified` | collected default-branch Detect, identity present, `is_ancestor` false | `verified` (hint: "fix not on default branch"; residual) |
| any live | `disable` | the loop's own open gates are withdrawn (023a). Incidents in `executing`/`verifying` → `withdrawn`. Children are not cancelled |

**Dirty** is `reopens < max_reopens` → `reopened` (`reopens += 1`, plan cleared), and otherwise `escalated`.

**Present while not yet merged.** A child that "completed" (`merged-not-deployed:<pr>`) has only *opened* its PR. The identity stays present on the default branch until a human merges that PR. This is expected and is **not** dirty. Only an identity that is present at a commit containing the child head counts. A `verified` incident whose PR is never merged stays `verified`, visible in `sdlc maintain incidents`. That is recorded as a residual: no stale-PR handling (out of scope).

Retention fires on entry to `closed` (lesson) or any other terminal state (experience), once (`retained`).
