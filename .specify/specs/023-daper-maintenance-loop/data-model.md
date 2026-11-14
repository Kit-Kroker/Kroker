# Data model — round 023a

All models are pydantic v2 with `extra="forbid"`, living in `src/sdlc/maintenance/models.py`. The producer owns its artifacts (root `AGENTS.md`): maintenance is a non-pipeline domain package beside `triage/` and `tidyup/`, and imports triage types (`TriageFinding`, `RepoTriage`, `FixClass`, `finding_identity`) without calling triage code.

## MaintenanceConfig — the registration (FR-001/002/011)

| Field | Type | Rule |
|---|---|---|
| `project` | `str` | `^[a-z0-9][a-z0-9-]{0,62}$`; the workflow id is `maint-<project>` |
| `repo_dir` | `str` | absolute path; checked to be a git work tree by the CLI at enable time (edge case) |
| `default_branch` | `str` | default `"main"` |
| `build_probe` | `bool` | default `True` |
| `ack_unattended_build_probe` | `bool` | must be `True` when `build_probe` is `True` (R14) |
| `advisory_source` | `Literal["none","osv"]` | default `"none"`, which renders as *not configured* (spec assumption) |
| `threshold` | `float` | `ge=0.5, le=1.0`, default `0.8` (R9) |
| `gate_timeout_hours` | `int` | `ge=1, le=168`, default `48` |
| `max_plan_attempts` | `int` | `ge=1, le=3`, default `2` (R8) |
| `max_new_incidents_per_cycle` | `int` | `ge=1, le=50`, default `10`; any excess is recorded `deferred` and picked up next cycle |
| `max_cycles_per_history` | `int` | `ge=1`, default `50` (R4) |

There is deliberately **no** `gates` / `policy` / `on_timeout` field (R9).

## MaintenanceState — the workflow input and the `continue_as_new` carry (R4)

| Field | Type | Notes |
|---|---|---|
| `config` | `MaintenanceConfig` | |
| `cycle` | `int` | monotonic across histories |
| `baseline` | `Baseline \| None` | `None` until cycle 1 completes |
| `prev` | `RepoTriage \| None` | filtered to `DETECT_SIGNALS`; findings capped at `MAX_PREV_FINDINGS` (R6) |
| `incidents` | `list[Incident]` | validator: keys are unique among non-terminal incidents (R7) |
| `not_collected_streak` | `dict[str, int]` | per signal id |
| `next_incident_no` | `int` | code-assigned incident numbers, never reused |
| `nudged` | `bool` | carried so a nudge that lands at the boundary is not lost |

## MaintenanceKickInput

`project: str` (same regex as `MaintenanceConfig.project`). It lives here rather than in the workflow module, so the schedules package depends on the domain package only.

## Baseline

`identities: frozenset[str]`, `signal_versions: dict[str, int]`, `recorded_cycle: int`, `commit_sha: str`.

## Incident

| Field | Type |
|---|---|
| `no` | `int` (`INC-<no>` when rendered) |
| `key` | `str`: a `finding_identity`, or `<signal>:not_collected::` |
| `kind` | `Literal["finding","detect_escalation"]` |
| `finding` | `TriageFinding \| None` |
| `commit_sha` | `str` (the commit pinned at the detecting cycle) |
| `first_seen_cycle` / `last_seen_cycle` | `int` |
| `seen_count` | `int` |
| `state` | `IncidentState` |
| `plan` | `RepairPlan \| None` |
| `plan_attempts` | `int` |
| `decision` | `GateDecision \| None` (carries `decided_by`) |
| `note` | `str` (reason text for `analysis_failed`, `withdrawn`, `deferred`, `detect_truncated`) |

### IncidentState and transitions

```
open ──plan ok──▶ awaiting_decision ──approve(human|policy)──▶ approved_not_executed   (terminal in 023a)
  │                     │──reject(human)──▶ rejected                                    (terminal)
  │                     │──timeout──▶ timed_out                                         (terminal)
  │                     └──disable──▶ withdrawn                                         (terminal)
  ├──plan failed (attempts < max)──▶ open (note=analysis_failed; retried next cycle)
  ├──plan failed (attempts = max)──▶ escalated                                          (terminal)
  ├──plan has zero actions──▶ awaiting_decision (plan.actions == [], rendered "no action proposed")
  ├──collected Detect no longer reports key──▶ resolved_externally                      (terminal)
  └──deferred (per-cycle cap)──▶ open on the next cycle

detect_escalation: open(awaiting ack gate) ──any decision or timeout──▶ escalated       (terminal)
```

Terminal incidents stay in `incidents` for the query. A later `NEW` of the same key opens a fresh incident with a fresh `no`. "Reopen" in the 023b sense is not modelled yet.

## RepairPlan (FR-009/010)

| Field | Type |
|---|---|
| `analysis` | `str` (≤ 4000 chars) |
| `actions` | `list[RepairAction]` (≤ 5) |
| `self_confidence` | `float` (0..1, from the proposer) |
| `floor` | `float` (code) |
| `effective` | `float` (`min(self_confidence, floor)`) |
| `author_model` | `str` |

`RepairAction`: `kind: Literal["code_fix","ops"]`, `summary: str`, `target_paths: list[str]` (code_fix), `ops_action: Literal["rollback","restart","scale"] | None`. In 023a nothing executes, so actions are recorded as proposed.

`RepairProposal` is the proposer's `output_type`: `analysis`, `actions`, `self_confidence`. Field order is evidence first (AP-1.4 / ADR-24): `analysis` comes before `actions`, which come before `self_confidence`. The workflow builds `RepairPlan` from it.

## Pure functions (no I/O, order-independent, NFR-10 style)

- `maintenance/incidents.py::step(state, curr: RepoTriage) -> tuple[MaintenanceState, CycleEvents]`: baseline, delta classification, opens, attaches, external resolutions, not-collected streaks, the per-cycle cap.
- `maintenance/confidence.py::confidence_floor(finding, *, reproduced: bool, reopens: int, n_actions: int) -> float`: the R8 table.
- `maintenance/gate.py::repair_gate_settings(cfg, name) -> GateSettings` and `escalation_gate_settings(cfg, name) -> GateSettings` (R9).
- `maintenance/prompt.py::render_repair_prompt(incident, triage_context) -> str`: bounded (≤ 16 KiB).
- `maintenance/render.py`: CLI table and the gate `GateContext` text.
