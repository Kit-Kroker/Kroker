"""Edge pins around the research role's output-retry budget after the
FR-202 cutover. The straight pins (construction default, registry value)
and the four run-site forwarding tests live in
tests/research/test_research_agent_retries.py; this file is the edge
margin around the construction:

- construction must stay at the DEFAULT on both provider branches (fake
  and the exa/CodeMode construction path) — the budget lives in
  agents/research/agent.yaml, and a retries kwarg re-pinned here would be
  a second source that shadows the knob;
- the widening must stay SCOPED to output: the tool-result retry budget
  stays at the framework default (1) on BOTH branches — the forwarded
  budget is always retries={"output": n}, never a bare int, which this
  role's live evidence ("Exceeded maximum output retries (1)" — output
  validation only) says nothing about widening;
- the cutover must not disturb the rest of the construction: the
  Temporal activity name and the ResearchBrief output wiring stay as
  they are.

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


def test_construction_stays_at_the_default_on_both_provider_branches():
    """The budget's one source is agents/research/agent.yaml (FR-202); the
    live 'Exceeded maximum output retries (1)' was on the production exa
    path, so a kwarg re-pinned on EITHER branch — not just the plain one —
    would reintroduce a second budget that silently wins or loses against
    the registry knob."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent._max_output_retries == 1, (
            f"provider={provider!r}: construction pins the output retry "
            f"budget at {agent._max_output_retries}, not the default 1 — "
            f"the budget lives in agents/research/agent.yaml and is "
            f"forwarded per call; construction must not re-pin it"
        )


def test_tool_result_retries_stay_untouched_on_both_branches():
    """The registry budget is forwarded as retries={{"output": n}}, never a
    bare int, and construction stays kwarg-free — so the tool-result retry
    budget keeps the framework default on both branches. This role's live
    evidence is about OUTPUT validation only."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent._max_tool_retries == 1, (
            f"provider={provider!r}: tool-result retry budget is "
            f"{agent._max_tool_retries}, not the default 1 — the widening "
            f"leaked beyond the output path; keep it scoped as "
            f'retries={{"output": ...}}'
        )


def test_construction_undisturbed_name_and_output_type():
    """PIN (green before and after the cutover): the edit must not disturb
    the rest of the construction — the Temporal activity name (NEVER
    rename) and the ResearchBrief output wiring survive on both provider
    branches."""
    for provider in _PROVIDERS:
        agent = _build(provider)
        assert agent.name == "research_agent", (
            f"provider={provider!r}: name is {agent.name!r} — the Temporal "
            f"activity name is load-bearing"
        )
        assert agent._output_type == ResearchBrief, (
            f"provider={provider!r}: output type is {agent._output_type!r}, expected ResearchBrief"
        )
