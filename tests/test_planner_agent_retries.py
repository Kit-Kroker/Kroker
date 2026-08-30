"""ImplementationPlan.tasks is a long array of near-identical DevTask
objects; a live run against anthropic:glm-5.2 showed the model filling the
first task's `description` correctly and then dropping it on every task
after -- pydantic_ai's default output-retry budget (1) spends its only
attempt on that first, uncorrected response. Pins the widened budget so a
future refactor of agents/planner/agent.py can't silently drop it back to
the default and reintroduce the flake this was written to fix."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic_ai.settings import ModelSettings

AGENT_PY = (Path(__file__).resolve().parents[1]
            / "agents" / "planner" / "agent.py")


def _build():
    spec = importlib.util.spec_from_file_location(
        "_test_planner_agent", AGENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build("openai:gpt-5", "be a planner", ModelSettings())


def test_planner_widens_the_output_retry_budget():
    agent = _build()
    assert agent._max_output_retries == 3
