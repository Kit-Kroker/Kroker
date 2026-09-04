# AGENTS.md — context

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned: context maps the repository tree independently using scan activities and projects into `CodebaseMap`.
- The step signature takes `ctx: StageContext` as first argument, never the workflow instance.
- The step never calls `ctx.gate`: context is a deterministic scan/projection stage and holds no gates.
- Context does not use LLM proposer agents; `prompts.prompt_digest(cfg)` returns `""`.
- The slice exports `step`, `build_map`, and `ACTIVITIES = [classify_repo, check_brownfield_delta]`.

## Temporal notes for this slice

- `ACTIVITIES = [classify_repo, check_brownfield_delta]`.
- Rule 3 passthrough set: `core/models.py`, `workflows/models.py`, the shared `sdlc/context/` package (below), `measurement`, and `workflows/scanning.py` (`scan_tree` — the workflow-side scan fan-out, shared with `workflows/assessment.py`, hence not stage-owned).

## The shared `sdlc/context/` package (deliberately NOT moved here)

Spec A §1 moved the four half-slices whole on the premise that none has a
consumer in another stage. For context that premise is false: `classify`,
`render_for_prompt`, `map_digest`, and the `CodebaseMap`/`RepoObservation`
models are consumed by intake, clarify, architecture (via feature.py), and
the assessment domain. Moving the package into this slice would force those
consumers into banned cross-stage imports. It stays a shared horizontal;
this slice owns the step, the stage artifacts (`BrownfieldDelta`), and the
two stage activities. The lazy `__init__` export keeps `sdlc.stages.context`
importable framework-free (calibration/operator tools import only models).

## State

- `StageContext` provides access to `stage`.
- No state is retained on workflow instances by this slice.

## Tests

    pytest tests/context/ -q
