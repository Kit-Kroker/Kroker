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
- Single retry layer (004): the planner and synthesis agents constructed in
  `stage.py` are built through `sdlc.agents.model_ids.single_retry_layer()`
  (a fresh `ResolveModelId` per construction), so every activity-side model
  request runs with the provider SDK's retries off — the activity's own
  attempt budget is the only retry layer. The registry `research_agent`
  (sub-question fan-out, architect tool) gets the same capability via
  `build_agents`.
- Model forwarding (004): the sub-question fan-out passes `model=inp.model`
  when it differs from the registry `research` model (D7a; `inp.model` is
  already an activity input, so the wire is unchanged). The architect's
  research tool receives the run's forwarded `research` override on
  `ResearchDeps.research_model` (populated by the architecture slice only
  under an override; omitted from serialization while None) and passes it
  as `model=` — no-override deps and calls are byte-identical to before.

## State

- `StageContext` capabilities provide access to `stage`, `gate`, `record`, and `retain`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/research/ -q
