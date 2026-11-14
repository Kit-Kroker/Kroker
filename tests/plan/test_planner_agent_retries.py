"""ImplementationPlan.tasks is a long array of near-identical DevTask
objects; a live run (2026-09, the pre-005 route anthropic:glm-5.2) showed
the model filling the first task's `description` correctly and then
dropping it on every task after -- pydantic_ai's default output-retry
budget (1) spends its only attempt on that first, uncorrected response.
Since FR-202 the widened budget lives in the registry
(agents/planner/agent.yaml) and is forwarded per call at the single
model-egress point (RoleHost._run_role); construction stays at the
default. Pins both halves so a future refactor of
agents/planner/agent.py can't silently re-pin the budget in code and the
registry value can't silently drop back to the default."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from pydantic_ai.settings import ModelSettings

from sdlc.agents.roles import OUTPUT_RETRIES

AGENT_PY = Path(__file__).resolve().parents[2] / "agents" / "planner" / "agent.py"


def _build():
    spec = importlib.util.spec_from_file_location("_test_planner_agent", AGENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build("openai:gpt-5", "be a planner", ModelSettings())


def test_planner_builds_at_the_default_output_retry_budget():
    agent = _build()
    assert agent._max_output_retries == 1


def test_planner_budget_lives_in_the_registry():
    assert OUTPUT_RETRIES["planner"] == 3
