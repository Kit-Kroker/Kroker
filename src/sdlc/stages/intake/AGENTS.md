# AGENTS.md — intake

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned, with this slice's sanctioned exception recorded: intake imports and executes `stages.context.activities.classify_repo` — the repo probe — per Task 20.1's prescribed interface (`classify_repo` is context-owned per the archaeology activity map; an activity import is not an orchestrator-level stage call).
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step never calls `ctx.gate`: intake is a deterministic repo probe and holds no gates.
- Intake does not use LLM proposer agents; `prompts.prompt_digest(cfg)` returns `""`.
- The slice exports `step` and `ACTIVITIES = []`.

## Temporal notes for this slice

- `ACTIVITIES = []`.
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.

## State

- `StageContext` capabilities provide access to `stage` and `emit`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/intake/ -q
