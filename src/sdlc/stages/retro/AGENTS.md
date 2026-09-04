# AGENTS.md — retro

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The retro stage does not call other stages.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step never calls `ctx.gate`: retro is best-effort terminal reporting and holds no gates.
- Retro does not use LLM proposer agents; `prompts.prompt_digest(cfg)` returns `""`.
- The slice exports `step` and `ACTIVITIES = []`.
- Best-effort execution guarantee: any exception inside `step` is swallowed so the workflow return string is preserved.

## Temporal notes for this slice

- `ACTIVITIES = []`.
- Rule 3 passthrough set: this slice passes through `core/models.py`, `workflows/models.py`, and upstream artifact models.

## State

- `StageContext` capabilities provide access to `emit` and `retain`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/retro/ -q
