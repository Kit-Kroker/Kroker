"""Bounded-retry regression guard over every durable agent (T035, FR-013).

Bug e2e-proposer-hang was an UNBOUNDED retry policy stacking under Temporal
attempts. Every agent roles.py ships must carry a bounded retry policy and a
finite start-to-close timeout on its bound durability, and the model
activities must keep the heartbeat disabled (FR-019's strict-neutrality
override). GREEN on the migrated tree; red means a durability budget
regressed.
"""

from datetime import timedelta

from pydantic_ai.durable_exec.temporal import TemporalDurability

from sdlc.agents.roles import ALL_TEMPORAL_AGENTS, CLARIFY_FANOUT_ACTIVITY_CONFIG

_FANOUT = ("clarify_route_agent", "clarify_probe_agent")


def test_every_durable_agent_has_bounded_retries_and_finite_timeouts():
    for agent in ALL_TEMPORAL_AGENTS:
        bound = TemporalDurability.from_agent(agent)
        assert bound is not None, f"{agent.name}: durability missing"
        retry = bound.activity_config.get("retry_policy")
        assert retry is not None, f"{agent.name}: unbounded (no retry policy)"
        assert retry.maximum_attempts == 3, agent.name
        start_to_close = bound.activity_config.get("start_to_close_timeout")
        assert start_to_close is not None, f"{agent.name}: no start_to_close"
        assert start_to_close < timedelta(days=1), agent.name
        # _model_activity_config is private on installed pydantic_ai 2.51 and
        # is the ONLY surface carrying the effective MERGED model activity
        # config — same justification as the loader's heartbeat check in
        # build_agents.
        assert bound._model_activity_config.get("heartbeat_timeout") is None, agent.name


def test_fanout_agents_use_the_fanout_config_by_value():
    """The clarify fan-out pair keeps its OWN bounded config: the bound
    values equal roles.CLARIFY_FANOUT_ACTIVITY_CONFIG's values (value
    equality — the SDK's bind normalizes the retry policy in place, so the
    frozen fields are compared by value, not object identity)."""
    names = {agent.name for agent in ALL_TEMPORAL_AGENTS}
    assert set(_FANOUT) <= names
    for agent in ALL_TEMPORAL_AGENTS:
        if agent.name not in _FANOUT:
            continue
        bound = TemporalDurability.from_agent(agent)
        assert bound is not None, agent.name
        cfg = bound.activity_config
        assert cfg.get("start_to_close_timeout") == (
            CLARIFY_FANOUT_ACTIVITY_CONFIG.get("start_to_close_timeout")
        ), agent.name
        retry = cfg.get("retry_policy")
        assert retry is not None, agent.name
        assert retry.maximum_attempts == (
            CLARIFY_FANOUT_ACTIVITY_CONFIG.get("retry_policy").maximum_attempts
        ), agent.name
