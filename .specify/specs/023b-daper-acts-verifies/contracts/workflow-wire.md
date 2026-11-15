# Contract — maintenance workflow wire, 023b additions

This extends `.specify/specs/023-daper-maintenance-loop/contracts/workflow-wire.md`. Nothing in that contract is renamed. These names are recorded in Temporal histories, and **never rename** them once shipped.

## Child workflows started by `MaintenanceWorkflow` (only when `config.execute`)

| Child | Id | Start options | Input |
|---|---|---|---|
| repair `GraphWorkflow` | `maint-<project>-<run8>-inc<no>-a<attempt>` | `id_reuse_policy=REJECT_DUPLICATE`, `parent_close_policy=ABANDON`, not awaited | `build_run_input(IdeaBrief(mode=BROWNFIELD, repo_url=repo_dir, base_branch=<base_sha>), _default_fix_cfg(), SeededWork)` |
| verification `TriageWorkflow` | `maint-<project>-<run8>-inc<no>-a<attempt>-verify` | awaited, as the cycle triage is | `TriageInput` at the verification head, `gating=False` |

`<run8>` is `workflow.info().first_execution_run_id[:8]`.

## Activities (new)

| Activity | Module | Input → Output | Side effects |
|---|---|---|---|
| `probe_repair_child` | `S/maintenance/activities.py` | `child_id` → `ChildProbe` | none (Temporal client describe and query) |
| `is_ancestor` | `S/vcs/integration.py` | `(repo_path, ancestor, descendant)` → `bool` | none (read-only git) |
| `remove_verification_tree` | `S/vcs/integration.py` | `(repo_path, key)` → `None` | removes the verify worktree and the `sdlc/tidyup-verify/<key>` ref |
| (reused) `build_verification_branch` | `S/vcs/integration.py` | `VerifyBranchInput(base_sha, tidyup_id=<child_id>, branches=[1])` | existing |
| (reused) `retain` | `S/memory/activities.py` | `RetainInput(kind=INCIDENT_LESSON \| INCIDENT_EXPERIENCE, bank=project_bank)` | existing |

## Signals sent by `MaintenanceWorkflow`

| Target | Signal | Payload | When |
|---|---|---|---|
| repair child | `submit_gate_decision` | `GateDecision(gate="merge", round=<pending_merge_round>, outcome=REJECT, decided_by="policy", comments=<verdict>)` | only on a dirty or conflicted verdict while the child is `awaiting_merge`. **No other outcome is ever built** |
| repair child | (cancel request) | — | at `child_timeout_hours` before `awaiting_merge` |

## Gate names (changed semantics)

- `repair:<incident_no>` now uses `round = incident.gate_round`. It is 1 for every 023a path. A refusal (research R6) or a reopen opens the next round.

## Patch marker

`workflow.patched("maint-023b-execute")` guards every new command path (research R15).

## `maintenance_state` query (additive fields)

`execute: bool`, `starts_in_window: int`, `in_flight: int` (incidents in `executing` or `verifying`).
