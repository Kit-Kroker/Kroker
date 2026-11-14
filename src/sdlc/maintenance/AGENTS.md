# AGENTS.md — maintenance

The DAPER maintenance loop's domain package (round 023a: plans, gated,
never acts). Repo-wide rules are in the root [AGENTS.md](../../../AGENTS.md);
the wire contract is
[.specify/specs/023-daper-maintenance-loop/contracts/workflow-wire.md](../../../.specify/specs/023-daper-maintenance-loop/contracts/workflow-wire.md).
This file carries only what is true *here*.

## Invariants

- The loop never writes to a repository: no branch, commit, worktree or PR
  (FR-016). Nothing in this package may shell out to git mutating commands.
- The repair gate is built in code, never from config. `MaintenanceConfig`
  exposes only `threshold` and `gate_timeout_hours`; there is no `gates` /
  `policy` / `on_timeout` field to misconfigure (R9, `gate.py`).
- `incidents.step`, `confidence.confidence_floor` and everything in
  `gate.py` are pure: no I/O, no Temporal, order-independent (NFR-10).
- Maintenance imports triage **types** only (`TriageFinding`, `RepoTriage`,
  `FixClass`, `finding_identity`) — never calls triage code from here; the
  triage child workflow is started by `workflows/maintenance.py`.
