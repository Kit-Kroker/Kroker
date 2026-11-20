# AGENTS.md — analyze

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The analyze stage does not call other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step never calls `ctx.gate`: analyze is proposer-only and runs prior to the merge gate.
- The clean-context Analyst role proposes criterion traces; workflow-side `enforce_traces` (and legacy `untraced_criteria`) enforces them.
- The integration diff is a `CodeArtifact` (FR-702, E-92): `step` takes `diff: CodeArtifact | None` — inline metadata only; when absent and a worktree is available, the step fetches the artifact once under the `integration` label with ONE `load_diff` read-back for the prompt. The patch text never rides the artifact.
- The slice exports `step` and `ACTIVITIES = [build_trace_inventory]`.

## Temporal notes for this slice

- `ACTIVITIES = [build_trace_inventory]`.
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.

## State

- `StageContext` capabilities provide access to `run_role`, `record`, and `retain`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/analyze/ -q
