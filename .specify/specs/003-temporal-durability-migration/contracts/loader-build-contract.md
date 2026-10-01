# Contract: registry `build()` and `build_agents()` (003)

Consumers: `src/sdlc/agents/loader.py`, the 14 `agents/<role>/agent.py`, `src/sdlc/agents/roles.py`, test fakes.

## `build()` in every asset

```python
def build(
    model: str,
    instructions: str,
    model_settings: ModelSettings,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent: ...
# research only, existing extra positionals kept:
def build(
    model,
    instructions,
    model_settings,
    tool_paths,
    provider,
    *,
    capabilities: Sequence[AbstractCapability] = (),
) -> Agent: ...
```

- The asset MUST forward `capabilities` to `Agent(..., capabilities=[*capabilities, *own_capabilities])` (durability outermost).
- The asset MUST keep `name="<x>_agent"` with the `# NEVER rename` comment; it MUST NOT construct its own `TemporalDurability`.

## `build_agents()`

```python
def build_agents(roles, model_settings, durability_factory: Callable[[], Any] | None = None,
                 agents_dir=None) -> dict[str, Agent]
```

- Per role: `dur = durability_factory()` (fresh instance) then `build(..., capabilities=[dur])`. `None` factory = no capabilities (loader-only tests, eval path).
- Fail closed with `RegistryError(role=...)` when: `build` rejects `capabilities` (`TypeError`); `TemporalDurability.from_agent(agent)` is `None`; more than one is attached; the bound `activity_config` has a weaker `start_to_close_timeout` or `maximum_attempts` than the factory's; `heartbeat_timeout` is not none; `bound.name != agent.name`; two roles share an agent name (existing).
- `loader.py` imports `TemporalDurability` lazily inside the function (no module-level temporal import).

## `roles.py`

- `AGENTS = build_agents(REGISTRY, MODEL_SETTINGS, durability_factory=<shared factory>)`.
- Fan-out agents: `Agent(..., capabilities=[TemporalDurability(activity_config=CLARIFY_FANOUT_ACTIVITY_CONFIG, model_activity_config={"heartbeat_timeout": None})])`.
- `t_<x> = <x>_agent` (aliases; optional ones `None`-able). `ALL_TEMPORAL_AGENTS` = list of agents.

## Worker

`agent_activities = [act for a in ALL_TEMPORAL_AGENTS for act in TemporalDurability.from_agent(a).temporal_activities]`, asserted exactly-once by name.

## Frozen values

Agent names, toolset ids, `AGENT_ACTIVITY_CONFIG` (600 s, 3), `CLARIFY_FANOUT_ACTIVITY_CONFIG` (600 s, 3). Any change is a defect of this feature.
