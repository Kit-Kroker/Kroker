"""The research agent's output-retry budget is widened to 3 (T7,
sbatch-2026-10-19).

Measured live in the research-partial-salvage assessment (error string
"Exceeded maximum output retries (1)"): one malformed final brief ended
the attempt and restarted the whole sub-question from scratch, burning
its remaining request budget. pydantic_ai's default budget of 1 spends
the only retry on the first, uncorrected attempt; the retry re-prompts
with the exact validation error, the stronger correction signal the
self-correction loop needs room to use. Mirrors the planner precedent
(agents/planner/agent.py pins retries={"output": 3}, pinned by
tests/plan/test_planner_agent_retries.py) — same shape, same value.
This pin fails if a future refactor of agents/research/agent.py
silently drops the budget back to the default and reintroduces the
flake it was written to fix.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic_ai.settings import ModelSettings

AGENT_PY = Path(__file__).resolve().parents[2] / "agents" / "research" / "agent.py"


def _build():
    spec = importlib.util.spec_from_file_location("_test_research_agent", AGENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # provider "fake" skips the exa branch (no EXA key needed); no tool
    # paths, so nothing is imported from agents/research/tools/.
    return module.build("openai:gpt-5", "be a researcher", ModelSettings(), [], "fake")


def test_research_widens_the_output_retry_budget():
    agent = _build()
    assert agent._max_output_retries == 3
