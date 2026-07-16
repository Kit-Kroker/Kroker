"""Analyst agent is defined, prompt-hashed, and in the temporal-agent list."""
from sdlc.agents.roles import (
    ALL_TEMPORAL_AGENTS, PROMPT_SHAS, analyst_agent, t_analyst,
)
from sdlc.models import AnalysisReport


def test_analyst_agent_named_and_typed():
    assert analyst_agent.name == "analyst_agent"
    assert analyst_agent.output_type is AnalysisReport


def test_analyze_prompt_is_hashed():
    assert "analyze" in PROMPT_SHAS
    assert len(PROMPT_SHAS["analyze"]) == 64  # sha256 hex


def test_analyst_in_all_temporal_agents():
    assert t_analyst in ALL_TEMPORAL_AGENTS
