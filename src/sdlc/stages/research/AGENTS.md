# AGENTS.md — research

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The research stage does not call other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step interacts with the human research gate through `ctx.gate("research", ...)` and does not bypass it.
- Research executes fan-out activities (`plan_research`, parallel `research_subquestion`, `synthesize_brief`).
- Grounding verification is enforced via `verify_brief_activity`; ungrounded briefs degrade the stage and are not retained.
- The slice exports `step` and `ACTIVITIES = [plan_research, research_subquestion, synthesize_brief, verify_brief_activity]`.

## Temporal notes for this slice

- Activities: `plan_research`, `research_subquestion`, `synthesize_brief`, `verify_brief_activity`.
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.

## State

- `StageContext` capabilities provide access to `stage`, `gate`, `record`, and `retain`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/research/ -q
