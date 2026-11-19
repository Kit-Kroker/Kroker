# AGENTS.md — maintenance

The DAPER maintenance loop's domain package (round 023a: plans, gated,
never acts; round 023b: acts and verifies — execute, report, closure,
retention). Repo-wide rules are in the root [AGENTS.md](../../../AGENTS.md);
the wire contracts are
[.specify/specs/023-daper-maintenance-loop/contracts/workflow-wire.md](../../../.specify/specs/023-daper-maintenance-loop/contracts/workflow-wire.md)
and, for the 023b execute half,
[.specify/specs/023b-daper-acts-verifies/contracts/workflow-wire.md](../../../.specify/specs/023b-daper-acts-verifies/contracts/workflow-wire.md).
This file carries only what is true *here*.

## Invariants

- The loop makes no git mutation (B-FR-016, amending 023a's blanket
  "never writes"): no branch, commit, worktree or PR from the loop's own
  process. The REPAIR CHILDREN write (in their own sandboxed worktrees),
  and the `S/vcs/` verification activities (`setup_integration_branch`,
  `build_verification_branch`) write; read-only git from the loop is
  allowed (rev-parse, ls-tree, show, is-ancestor). Nothing in this
  package may shell out to a git mutating command.
- The loop's only child-gate decision is REJECT (023b R11): a dirty or
  regressed verification rejects the child's merge gate; the loop never
  approves its own children — approval stays with the operator through
  the inbox.
- `S/workflows/maintenance_execute.py` defines no handler and owns no
  attribute: it holds async step functions over explicit arguments
  (execute, closure, timeout, report, retain). Handlers and signals stay
  on the concrete `MaintenanceWorkflow` class.
- The repair gate is built in code, never from config. `MaintenanceConfig`
  exposes only `threshold` and `gate_timeout_hours`; there is no `gates` /
  `policy` / `on_timeout` field to misconfigure (R9, `gate.py`).
- `incidents.step`, `confidence.confidence_floor` and everything in
  `gate.py` are pure: no I/O, no Temporal, order-independent (NFR-10).
- Maintenance imports triage **types** only (`TriageFinding`, `RepoTriage`,
  `FixClass`, `finding_identity`) — never calls triage code from here; the
  triage child workflow is started by `workflows/maintenance.py`.
- Ops actions are risk-classed (`gate.risk_class`, FR-502): every ops
  action is `HUMAN_REQUIRED` today, so an ops-bearing plan's repair gate
  is HARD from birth behind the `maint-risk-class` marker — policy can
  never approve one; execution stays never (GATE 2).

## Modules and verbs

`models.py`, `incidents.py`, `confidence.py`, `gate.py`, `execution.py`,
`prompt.py` and `render.py` are the pure/domain modules (`execution.py` is
the 023b execution policy: `may_execute`, `apply_verdict` — pure, including
the `regressed` verdict — `choose_starts`, `closure_outcome`,
`classify_verification`, `merge_reject_decision`); `cli.py` owns the
`maintain` verbs: `enable` (NFR-9: requires exactly one of
`--ack-unattended-build-probe` / `--no-build-probe`; no gate-policy flags;
023b adds `--execute` with the gh/origin/branch preconditions and the four
bounded cap flags), `incidents [--all|--state]`, `nudge`, `disable`.
Maintenance gates join the cross-run inbox (R11), so the existing decision
verbs resolve them — there is no maintain-specific decision verb. The
workflows live in `workflows/maintenance.py` (`MaintenanceWorkflow`,
`MaintenanceKickWorkflow`).
