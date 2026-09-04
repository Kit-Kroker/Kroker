# AGENTS.md — review

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The review stage does not call other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Clean-context: the primary reviewer and adversary lenses receive contract assertions, deterministic test output, and materialized diff patch only. They never touch harness sessions or worker narratives.
- Deep review is an advisory lens that inspects the scrubbed session transcript. It is never consulted in task pass/fail gating.
- Lenses are fail-open: safety lenses must never fail task delivery.
- The slice exports `step`, `run_adversary`, `run_deep_review`, and `ACTIVITIES = []`.

## Temporal notes for this slice

- Activities: none (`ACTIVITIES = []`). Session transcript loading uses `load_session` from `artifacts`.
- Temporal workflow execution uses `_now()` and `_workflow_id()` helpers with non-Temporal fallbacks for unit tests.

## State

- `StageContext` capabilities provide access to `run_role`, `record`, and `retain`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/review/ -q
