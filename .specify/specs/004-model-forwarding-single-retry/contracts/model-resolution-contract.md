# Contract: model resolution and the single retry layer

Module: `src/sdlc/agents/model_ids.py` (new). Provider SDK imports are lazy, inside functions.

## `forwarded_model(cfg, role) -> str | None`

- `role` is a registry role name (the key space of `cfg.roles`).
- Returns the override string iff `cfg.roles[role].model` is set and differs from the registry model for that role. Otherwise `None`.
- Pure over its arguments; safe in workflow code.

## `RoleHost._run_role(cfg, role, model, agent, *args, into=None, **kwargs)`

Signature unchanged. Behaviour:

| Condition | Call made | Otherwise |
|---|---|---|
| `forwarded_model` is `None` | `agent.run(*args, **kwargs)` exactly as today | |
| not `None` and equals `model` | `agent.run(*args, model=<forwarded>, **kwargs)` | |
| not `None` and differs from `model` | none | non-retryable error naming role, label, override |
| `kwargs` contains `model` | none | non-retryable error |

Pricing, usage tracking and the return value are unchanged.

## `single_retry_layer()` capability factory

- Returns a fresh model-id resolver capability per call (one instance per agent).
- The resolver builds the model for any model-id string through the framework's normal provider constructor and sets the provider client's SDK retry count to 0 when the client exposes one.
- Must not: construct an HTTP client, change base URL, credentials or timeouts, import anything at module import time, or alter any scheduled activity name or input.
- Attached to: every agent built by `build_agents` when a durability factory is supplied; `clarify_route_agent`; `clarify_probe_agent`; the planner and synthesis agents constructed in `stages/research/stage.py`.

## Guarantees tested

1. Registry-model agent against an always-429 stub: HTTP requests <= that agent's attempt budget.
2. Fail-once stub: exactly 2 requests, call succeeds.
3. Overridden role against a second provider's stub: same bound.
4. Every agent in `ALL_TEMPORAL_AGENTS` and both plain research-stage agents carry the capability.
5. No-override run: wire fixture (activity names, order, model ids) equals the Phase A baseline.
6. A non-retryable provider error (400) produces exactly 1 request (E7).
7. Research sub-question under a `research` override: the recording fake sees the override id and the usage label equals it.
