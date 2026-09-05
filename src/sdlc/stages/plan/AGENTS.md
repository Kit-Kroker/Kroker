# AGENTS.md — plan

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: plan accepts architecture spec and requirements, executing independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = []`.
- Downstream requirements and architecture are consumed without modifying caller state.

## Temporal notes for this slice

- `ACTIVITIES = []`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `architecture`, `clarify`.
- Memoization key incorporates prompt salt via `prompt_digest(cfg)`.
- Lazy exports in `__init__.py` break circular imports with benchmarks models.

## State

- `StageContext` provides access to `revisable_stage`, `cached_stage`, `run_role`, `judge`, `record`, `retain`, `recall`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/plan/ -q
