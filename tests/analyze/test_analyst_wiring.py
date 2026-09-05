"""Analyst agent is defined, prompt-hashed, and in the temporal-agent list."""

from sdlc.agents.roles import (
    ALL_TEMPORAL_AGENTS,
    PROMPT_SHAS,
    analyst_agent,
    t_analyst,
)
from sdlc.stages.analyze.models import AnalysisReport


def test_analyst_agent_named_and_typed():
    assert analyst_agent.name == "analyst_agent"
    assert analyst_agent.output_type is AnalysisReport


def test_analyze_prompt_is_hashed():
    assert "analyze" in PROMPT_SHAS
    assert len(PROMPT_SHAS["analyze"]) == 64  # sha256 hex


def test_analyst_in_all_temporal_agents():
    assert t_analyst in ALL_TEMPORAL_AGENTS


def test_measure_coverage_registered_on_worker():
    # The worker's activity list is assembled in get_worker_activities()
    # (main() consumes it); assert the callable is included (via merge.ACTIVITIES).
    import sdlc.worker as w

    names = [getattr(a, "__name__", str(a)) for a in w.get_worker_activities()]
    assert "measure_coverage" in names
