# AGENTS.md — requirements

Local rules for editing this slice. Repo-wide rules are in the root
[AGENTS.md](../../../AGENTS.md); the seam contract and the Temporal
rules are in [docs/framework.md](../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

- Cross-stage calls are banned. The legal imports are types and renders, not
  calls: clarify imports `Requirements` from `requirements.models` and
  `render_requirements` from `requirements.prompts` (root AGENTS.md:
  importing a type another stage produces is not a call) — clarify is the
  artifact's ONLY downstream consumer. This slice imports no other stage.
- The step signature takes `ctx: StageContext` as first argument, never the
  workflow instance (`step(ctx, *, cfg, idea, repo_path)`).
- The step never calls `ctx.gate` and never calls `ctx.record`: completion is
  a `STAGE_ENDED` emitted directly via `ctx.emit` — no benchmark row, no
  `duration_s`; cost reaches the run through the `MODEL_USAGE` event.
- `deps.mode` is consumed by the freeze (`verify.py`), never by the prompt:
  the prompt's mode line derives from the resolved workspace
  (`stage._repo_workspace`), so mode and readability can never diverge.
- The slice exports `step` and `ACTIVITIES = [draft_requirements]`; `step`
  the function stays on its submodule (a package attribute named `step` is
  shadowed by the submodule the moment anyone imports it), and the package
  re-exports `ACTIVITIES`/`draft_requirements` lazily via `__getattr__`.

## Temporal notes for this slice

- Activities: `draft_requirements` (10 min start-to-close, 3 attempts; no
  heartbeat — the run is short).
- Rule 3 passthrough set (step.py's block): `core/context.py`,
  `core/models.py`, `agents/roles.py`, `benchmarks/models.py`,
  `memory/models.py`, `observability/trace.py`, `pricing`, and the slice's
  own submodules.
- Single retry layer (004): the registry `product_agent` is built by the
  loader with `[durability, single_retry_layer(), payload_guard()]`, so every
  activity-side model request runs with provider SDK retries off — the
  activity's own attempt budget is the only retry layer. Nothing re-adds one.
- Model forwarding (004 D7a): the activity forwards `inp.model` only when it
  differs from the registry `product` model; an equal or absent override
  calls exactly as before, so no-override runs and replays are untouched.
- Usage hand-back (E-33): the activity returns its spend beside the draft as
  `RoleUsage(role="product", cost_usd=None)` — the REGISTRY name, not the
  stage name (`STAGE_ROLES` reconciles "requirements" the stage to
  "product"), because usage is priced and attributed per role; the workflow
  prices it via `price_usage` and emits `MODEL_USAGE`. A zero-token usage (a
  run refused before its first request) prices nothing and emits nothing.
- Workspace scratch root: `$SDLC_RUNS_ROOT` (default CWD-relative `runs/`),
  one scratch dir per run at `<root>/<run_id>/requirements/`, created empty
  before the draft — the same root research's budget_store/pages and
  constitution's scratch use.

## State

- `StageContext` capabilities provide access to `stage`, `emit`, and `retain`.
- No state is retained on workflow instances by this slice.

## Gotchas

- `calls=1` is hardcoded in `stage._role_usage` for a run that returned a
  draft (one completed agent run), not read from `RunUsage`; the
  refused-before-first-request degradation path returns a `calls=0`
  zero-token `RoleUsage` instead.
- `prompts._truncate` assumes `max_chars > 2` (the `"\n…"` marker's
  length): below that, `block[: max_chars - 2]` goes negative and slices
  from the END, inverting the bound. Every caller uses the 2000 default;
  keep it that way.
- Unlike constitution (whose parked whitespace-`source_ref` gotcha is
  documented in its AGENTS.md), freeze here drops whitespace refs:
  the check is `not (ref or "").strip()`, so `None`, `""` and `" "` all
  count as missing in brownfield.
- `default.graph.yaml`'s content sha is pinned (E-72 identity discipline):
  the node ships in the separate `default-requirements.graph.yaml` — never
  edit the default file to add it. `select_graph` picks that graph when
  `cfg.requirements_enabled` is set and the registry ships the role
  (research > constitution > requirements when several flags are on);
  `requirements_enabled` is overlaid from the pinned graph's own shape at
  the single `project_cfg` call site, whose `requirements_in_graph` kwarg
  is REQUIRED — a defaulted bridge fails silently instead of loudly.

## Tests

    pytest tests/requirements/ -q
