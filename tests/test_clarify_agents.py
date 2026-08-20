"""The two extra clarify agents. They are NOT new registry roles: they reuse
the clarify role's model, so agents/ stays at 15 roles."""
from sdlc.agents.roles import (AGENT_ACTIVITY_CONFIG, ALL_TEMPORAL_AGENTS,
                               CLARIFY_FANOUT_ACTIVITY_CONFIG,
                               CLARIFY_FANOUT_MAX_ATTEMPTS, REGISTRY,
                               clarify_agent, clarify_probe_agent,
                               clarify_route_agent, t_clarify, t_clarify_probe,
                               t_clarify_route)
from sdlc.clarify.models import ClarifyRoute, ProbeResult
from sdlc.clarify.prompts import PROBE_SYSTEM, ROUTE_SCOPE


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
    assert "clarify_route" not in REGISTRY
    assert "clarify_probe" not in REGISTRY


# ---- one role per system prompt ---------------------------------------
# `_system_prompts` is the tuple pydantic-ai stores the constructor's
# `system_prompt=` into; `Agent.system_prompt` is the decorator, not the
# text. These assertions are the reason the attribute is read directly.

def _system_prompt(agent) -> str:
    return "\n\n".join(agent._system_prompts)


CLARIFY_INSTRUCTIONS = REGISTRY["clarify"].instructions


def test_the_route_agent_composes_with_the_clarify_preamble():
    """ROUTE_SCOPE opens with "You are ALSO the ROUTER" -- it presupposes
    the preamble and adds to it. The route agent IS the requirements
    analyst instructions.md describes: it authors the body."""
    prompt = _system_prompt(clarify_route_agent)
    assert CLARIFY_INSTRUCTIONS in prompt
    assert ROUTE_SCOPE in prompt


def test_the_probe_agent_is_not_also_told_it_is_a_requirements_analyst():
    """Two role assignments in one system prompt is a coin flip.
    instructions.md says "extract functional and non-functional
    requirements, define what is out of scope"; PROBE_SYSTEM says "You own
    exactly one dimension... Depth on your own dimension is the entire
    job" -- over a ProbeResult with no field for either."""
    prompt = _system_prompt(clarify_probe_agent)
    assert prompt == PROBE_SYSTEM
    assert CLARIFY_INSTRUCTIONS not in prompt


def test_the_probe_prompt_says_who_owns_the_requirements_body():
    # Dropping the preamble must not drop the boundary it implied.
    assert "not the requirements analyst" in PROBE_SYSTEM


def test_the_flag_off_agents_prompt_is_still_the_registry_prompt():
    # instructions.md is SHA-pinned and is the flag-off prompt. Neither
    # E-85 fix may touch it.
    assert _system_prompt(clarify_agent) == CLARIFY_INSTRUCTIONS


# ---- bounded retries, or "probes fail open" is not true ---------------

def test_the_fanout_agents_bound_their_retries():
    """AGENT_ACTIVITY_CONFIG sets no retry_policy, so Temporal's default --
    UNLIMITED attempts -- applies. Under the old single clarify call that
    was one call retrying forever. Under the fan-out it is worse: a probe
    that never exhausts never raises, asyncio.gather never returns, and the
    stage HANGS instead of degrading (spec §8, D10)."""
    assert 1 <= CLARIFY_FANOUT_MAX_ATTEMPTS < 10
    assert (CLARIFY_FANOUT_ACTIVITY_CONFIG["retry_policy"].maximum_attempts
            == CLARIFY_FANOUT_MAX_ATTEMPTS)
    # ...and it is the config the two agents are actually built with.
    for agent in (t_clarify_route, t_clarify_probe):
        assert (agent.activity_config["retry_policy"].maximum_attempts
                == CLARIFY_FANOUT_MAX_ATTEMPTS)


def test_no_other_agents_retry_behaviour_changed():
    """The fan-out config is SEPARATE precisely so it cannot reach any
    other role. Mutating the shared one would silently bound every agent.

    maximum_attempts == 0 is Temporal's encoding of UNLIMITED, and it is
    what every agent on the shared config still gets -- including the
    flag-off clarify agent, whose behaviour E-85 must not change."""
    assert CLARIFY_FANOUT_ACTIVITY_CONFIG is not AGENT_ACTIVITY_CONFIG
    assert "retry_policy" not in AGENT_ACTIVITY_CONFIG
    assert t_clarify.activity_config["retry_policy"].maximum_attempts == 0
