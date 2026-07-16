"""Deterministic, offline stand-ins for the proposer TemporalAgents.

Each fake reuses the PRODUCTION agent name so its generated Temporal
activity names match — the workflow's `t_<role>.run(...)` then dispatches
to the fake when only these activities are registered on the test worker.
The model is Pydantic AI's TestModel forced to emit a canned typed output.
"""
from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.durable_exec.temporal import TemporalAgent
from pydantic_ai.models.test import TestModel

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG


def fake_temporal_agent(name: str, output_type: type,
                        value: BaseModel) -> TemporalAgent:
    """A TemporalAgent whose model always returns `value` as `output_type`."""
    agent = Agent(
        TestModel(custom_output_args=value.model_dump(mode="json")),
        name=name,
        output_type=output_type,
    )
    return TemporalAgent(agent, activity_config=AGENT_ACTIVITY_CONFIG)


def fake_agent_activities(
        specs: list[tuple[str, type, BaseModel]]) -> list:
    """Flatten the Temporal activities for a list of (name, type, value)."""
    activities: list = []
    for name, output_type, value in specs:
        ta = fake_temporal_agent(name, output_type, value)
        activities.extend(ta.temporal_activities)
    return activities
