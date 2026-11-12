# AGENTS.md — constitution

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The legal imports are types and renders, not
  calls: clarify/architecture/plan import `Constitution` from
  `constitution.models` and `render_constitution` from `constitution.prompts`
  (root AGENTS.md: importing a type another stage produces is not a call).
  This slice imports no other stage.
- The step signature takes `ctx: StageContext` as first argument, never the
  workflow instance (`step(ctx, *, cfg, idea, repo_path)`).
- The step never calls `ctx.gate` and never calls `ctx.record`: completion is
  a `STAGE_ENDED` emitted directly via `ctx.emit` — no benchmark row, no
  `duration_s`; cost reaches the run through the `MODEL_USAGE` event.
- `deps.mode` is consumed by the freeze (`verify.py`), never by the prompt:
  the prompt's mode line derives from the resolved workspace
  (`stage._repo_workspace`), so mode and readability can never diverge.
- The slice exports `step` and `ACTIVITIES = [draft_constitution]`; `step`
  the function stays on its submodule (a package attribute named `step` is
  shadowed by the submodule the moment anyone imports it).

## Temporal notes for this slice

- Activities: `draft_constitution` (10 min start-to-close, 3 attempts; no
  heartbeat — the run is short).
- Rule 3 passthrough set (step.py's block): `core/context.py`,
  `core/models.py`, `agents/roles.py`, `benchmarks/models.py`,
  `memory/models.py`, `observability/trace.py`, `pricing`, and the slice's
  own submodules.
- Single retry layer (004): the registry `constitution_agent` is built by the
  loader with `[durability, single_retry_layer(), payload_guard()]`, so every
  activity-side model request runs with provider SDK retries off — the
  activity's own attempt budget is the only retry layer. Nothing re-adds one.
- Model forwarding (004 D7a): the activity forwards `inp.model` only when it
  differs from the registry `constitution` model; an equal or absent override
  calls exactly as before, so no-override runs and replays are untouched.
- Usage hand-back (E-33): the activity returns its spend beside the draft as
  `RoleUsage(role="constitution", cost_usd=None)`; the workflow prices it via
  `price_usage` and emits `MODEL_USAGE`. A zero-token usage (a run refused
  before its first request) prices nothing and emits nothing.
- Workspace scratch root: `$SDLC_RUNS_ROOT` (default CWD-relative `runs/`),
  one scratch dir per run at `<root>/<run_id>/constitution/`, created empty
  before the draft — the same root research's budget_store/pages use.

## State

- `StageContext` capabilities provide access to `stage`, `emit`, and `retain`.
- No state is retained on workflow instances by this slice.

## Gotchas

- A whitespace-only `source_ref` survives brownfield freeze: verify checks
  `not item.source_ref` (None/`""`) while the whitespace check applies to the
  statement only, so a ref of `" "` is truthy and passes. Deferred minor
  (controller-ruled); documented here as a known edge, not fixed.
- `calls=1` is hardcoded in `stage._role_usage` for a run that returned a
  draft (one completed agent run), not read from `RunUsage`; the
  refused-before-first-request degradation path returns a `calls=0`
  zero-token `RoleUsage` instead.
- `default.graph.yaml`'s content sha is pinned (E-72 identity discipline):
  the node ships in the separate `default-constitution.graph.yaml` — never
  edit the default file to add it. `select_graph` picks that graph when
  `cfg.constitution_enabled` is set and the registry ships the role (research
  wins when both flags are on); a run may still pin a custom graph
  explicitly, and `constitution_enabled` is overlaid from the pinned graph's
  own shape at the single `project_cfg` call site.

## Tests

    pytest tests/constitution/ -q
