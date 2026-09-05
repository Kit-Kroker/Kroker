# AGENTS.md — architecture

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: architecture accepts clarified requirements, codebase map, and memory watermark, executing independently.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- Handlers live on the workflow class's MRO, never in this slice.
- The slice exports `step`, `prompt_digest`, and `ACTIVITIES = []`.
- Downstream requirements view excludes telemetry and dropped questions (`dropped`, `dimensions_probed`).
- Grounded research subqueries operate under the dedicated `scope="architect"` budget.

## Temporal notes for this slice

- `ACTIVITIES = []`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, `clarify`, `context`, `research`.
- Memoization key incorporates prompt salt via `prompt_digest(cfg)`.
- Eager exports in `__init__.py` ensure worker boot registers models without sandbox errors.

## State

- `StageContext` provides access to `revisable_stage`, `cached_stage`, `run_role`, `judge`, `record`, `retain`, `recall`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/architecture/ -q
