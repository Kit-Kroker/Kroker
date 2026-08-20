"""The two extra clarify agents. They are NOT new registry roles: they reuse
the clarify role's model and prompt preamble, so agents/ stays at 15 roles."""
from sdlc.agents.roles import (ALL_TEMPORAL_AGENTS, clarify_agent,
                               clarify_probe_agent, clarify_route_agent,
                               t_clarify_probe, t_clarify_route)
from sdlc.clarify.models import ClarifyRoute, ProbeResult


def test_the_route_agent_outputs_a_clarify_route():
    assert clarify_route_agent.output_type is ClarifyRoute


def test_the_probe_agent_outputs_a_probe_result():
    assert clarify_probe_agent.output_type is ProbeResult


def test_the_original_clarify_agent_is_untouched():
    # The flag-off path must stay byte-identical.
    assert clarify_agent.name == "clarify_agent"


def test_activity_names_are_distinct_and_stable():
    # These are Temporal activity names. Renaming one strands in-flight runs.
    assert clarify_route_agent.name == "clarify_route_agent"
    assert clarify_probe_agent.name == "clarify_probe_agent"


def test_both_are_registered_so_the_worker_hosts_their_activities():
    assert t_clarify_route in ALL_TEMPORAL_AGENTS
    assert t_clarify_probe in ALL_TEMPORAL_AGENTS


def test_the_registry_did_not_grow_a_role():
    from sdlc.agents.roles import REGISTRY
    assert "clarify_route" not in REGISTRY
    assert "clarify_probe" not in REGISTRY
