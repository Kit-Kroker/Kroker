# AGENTS.md — code

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: code stage accepts task, contract, and worktree, executing independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = [run_coding_task, load_drift_globs]`.
- `freeze.py` holds the C2 freeze/thaw decision rules as pure functions (no `ctx`, no I/O, table-testable); `step.py` re-exports them, so existing `from ...code.step import _next_anchor` sites keep working. Audit recorders (`_record_escalation`, `_record_thaw`) stay in `step.py`.
- All tool escalations and approvals are recorded to benchmarks and trace events.
- QA and review stages are invoked clean-context, validating against the frozen contract.

## Temporal notes for this slice

- `ACTIVITIES = [run_coding_task, load_drift_globs]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `harness`, `crew`.
- Long-running harness activities use heartbeat timeouts and retry policies.
- Eager exports in `__init__.py` ensure worker boot registers activities and models without sandbox errors.

## State

- `StageContext` provides access to `gate`, `record`, `retain`, `emit`, `judge`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/code/ -q
