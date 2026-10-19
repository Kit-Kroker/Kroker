"""Edge pins around the research agent's output-retry widening
(sbatch-2026-10-19 T7; task
.workspace/tasks/2026-10-05-research-agent-output-retries-1.md).

The live failure was "Exceeded maximum output retries (1)" from the
research role's structured output — pydantic-ai's default budget of 1
spends its only attempt on the first, uncorrected response. The planned
fix mirrors the planner precedent (agents/planner/agent.py,
retries={"output": 3}, pinned by tests/plan/test_planner_agent_retries.py).
qa-happy's tests/research/test_research_agent_retries.py covers the
straight widening; this file is the edge margin around it:

- the widening must be SCOPED: the tool-result retry budget stays at the
  framework default (1) on BOTH provider branches — a bare ``retries=3``
  would also widen tool retries, which this role's evidence says nothing
  about;
- the widening must reach BOTH provider branches (fake and the
  exa/CodeMode construction path), not just the plain one;
- the edit must not disturb the rest of the construction: the Temporal
  activity name and the ResearchBrief output wiring stay as they are.

Attribute names introspected on the installed pydantic-ai 2.51.0 (not
guessed): ``_max_output_retries``, ``_max_tool_retries`` (verified: a
``retries={"output": 3}`` agent holds output=3, tool=1; a default agent
holds 1/1), and ``_output_type`` (the class itself).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic_ai.settings import ModelSettings

from sdlc.stages.research.models import ResearchBrief

AGENT_PY = Path(__file__).resolve().parents[2] / "agents" / "research" / "agent.py"

# Both construction paths the registry can route through: the plain branch
# and the exa branch (CodeMode + wrapped exa capability; EXA_API_KEY dummy
# comes from tests/conftest.py). tool_paths=[] keeps both tool-free.
_PROVIDERS = ("fake", "exa")


def _build(provider: str):
    spec = importlib.util.spec_from_file_location("_test_research_agent", AGENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(
        "openai:gpt-5",
        "be a researcher",
        ModelSettings(),
        tool_paths=[],
        provider=provider,
    )


def test_widening_stays_scoped_tool_result_retries_untouched():
    """PIN (green today — no retries kwarg exists yet, tool budget is the
    default; must stay green after the fix): retries={"output": 3} leaves
    _max_tool_retries at 1 on both provider branches. A future edit that
    widens the whole retries setting (bare int instead of the scoped dict)
    fails here — this role's live evidence is about OUTPUT validation
    only."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent._max_tool_retries == 1, (
            f"provider={provider!r}: tool-result retry budget is "
            f"{agent._max_tool_retries}, not the default 1 — the widening "
            f"leaked beyond the output path; scope it as "
            f'retries={{"output": ...}} (planner precedent)'
        )


def test_both_provider_branches_widen_the_output_retry_budget():
    """RED today (default 1 on both branches): the fix must reach the
    agent construction shared by every provider route — the live
    'Exceeded maximum output retries (1)' was on the production exa path,
    so widening only the plain branch would fix the test shape and miss
    the failure it was written for."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent._max_output_retries == 3, (
            f"provider={provider!r}: output retry budget is "
            f"{agent._max_output_retries}, expected 3 — the research "
            f"agent dies on its first uncorrected output attempt "
            f"(task 2026-10-05, planner precedent)"
        )


def test_construction_undisturbed_name_and_output_type():
    """PIN (green today; must stay green): the edit must not disturb the
    rest of the construction — the Temporal activity name (NEVER rename)
    and the ResearchBrief output wiring survive the widening on both
    provider branches."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent.name == "research_agent", (
            f"provider={provider!r}: name is {agent.name!r} — the Temporal "
            f"activity name is load-bearing"
        )
        assert agent._output_type == ResearchBrief, (
            f"provider={provider!r}: output type is {agent._output_type!r}, expected ResearchBrief"
        )
