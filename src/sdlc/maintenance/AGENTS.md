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

## Modules and verbs

`models.py` (wire types), `incidents.py`, `confidence.py`, `gate.py`,
`prompt.py` and `render.py` are the pure/domain modules; `cli.py` owns the
`maintain` verbs: `enable` (NFR-9: requires exactly one of
`--ack-unattended-build-probe` / `--no-build-probe`; no gate-policy flags),
`incidents [--all|--state]`, `nudge`, `disable`. Maintenance gates join the
cross-run inbox (R11), so the existing decision verbs resolve them — there
is no maintain-specific decision verb. The workflows live in
`workflows/maintenance.py` (`MaintenanceWorkflow`, `MaintenanceKickWorkflow`).
