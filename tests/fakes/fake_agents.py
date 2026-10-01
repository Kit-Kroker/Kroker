"""Deterministic, offline stand-ins for the proposer agents.

Each fake reuses the PRODUCTION agent name so its generated Temporal
activity names match — the workflow's `t_<role>.run(...)` then dispatches
to the fake when only these activities are registered on the test worker.

The model is Pydantic AI's TestModel forced to emit a canned typed output.

003: fakes use the SAME durability mechanism as production (the
TemporalDurability capability attached at construction, same activity
config including the heartbeat-none override; FR-008) so replay proof
exercises the real registration surface.

004 (T006): every resolver RECORDS `(agent name, model id)` into the
module list ``MODEL_RESOLUTIONS`` — which model id each fake was asked to
be — and the TestModel fakes answer as ``TestModel(..., model_name=<that
id>)``, so usage/label surfaces name the model that was requested. The
list is cleared between tests by the autouse reset in tests/conftest.py;
``tests/test_model_forwarding.py`` (T025) reads it. Canned outputs are
byte-identical to the previous shared-instance behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.models.test import TestModel

from sdlc.agents.roles import AGENT_ACTIVITY_CONFIG

#: (agent name, model id) for every fake resolver call, in call order.
#: FR-006's recording surface: a test reads this to assert which model id
#: served a proposer request. Autouse-cleared per test (tests/conftest.py).
MODEL_RESOLUTIONS: list[tuple[str, str | None]] = []


def _requested_name(model_id: str | None) -> str:
    """TestModel's model_name: the requested id when one crossed the wire
    (004 R2: for no-override runs it is the registry string), else the
    historical default 'test' so a None id keeps byte-identical outputs."""
    return model_id if isinstance(model_id, str) and model_id else "test"


def fake_durable_agent(name: str, output_type: type, value: BaseModel) -> Agent:
    """A durable agent whose model always returns `value` as `output_type`.

    `call_tools=[]` disables TestModel's default behaviour of auto-calling
    every tool in `function_tools` before emitting its canned output. With
    Task 9 the production architect agent registers a `research` tool, so
    the workflow-side `t_architect` advertises that tool to the model; the
    fake architect has no tools locally and would otherwise raise
    `Tool 'research' not found in toolset`.

    The ResolveModelId is 003 load-bearing: the workflow-side agent is the
    REAL registry agent, whose model is a provider STRING — under the
    capability that string crosses the wire as params.model_id and the
    activity rebuilds it with infer_model, which would make a REAL provider
    call. The old wrapper sent None and answered with the wrapped agent's
    own model (this TestModel). The resolver restores exactly that: any
    arriving model id resolves to this fake's TestModel — since T006 a
    fresh one per call that ANSWERS AS the requested id (model_name) and
    records the request in MODEL_RESOLUTIONS."""

    def _resolve(ctx, model_id: str | None) -> TestModel:
        MODEL_RESOLUTIONS.append((name, model_id))
        return TestModel(
            custom_output_args=value.model_dump(mode="json"),
            call_tools=[],
            model_name=_requested_name(model_id),
        )

    agent = Agent(
        TestModel(custom_output_args=value.model_dump(mode="json"), call_tools=[]),
        name=name,
        output_type=output_type,
        capabilities=[
            TemporalDurability(
                activity_config=AGENT_ACTIVITY_CONFIG,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(_resolve),
        ],
    )
    return agent


def fake_agent_activities(specs: list[tuple[str, type, BaseModel]]) -> list:
    """Flatten the Temporal activities for a list of (name, type, value).

    Activities come from the BOUND capability (`from_agent`) — the
    constructed instance's own `temporal_activities` is empty until the
    agent binds it (research.md R1)."""
    activities: list = []
    for name, output_type, value in specs:
        agent = fake_durable_agent(name, output_type, value)
        bound = TemporalDurability.from_agent(agent)
        assert bound is not None, name  # attached two lines above
        activities.extend(bound.temporal_activities)
    return activities


def failing_durable_agent(name: str, output_type: type, model, activity_config) -> Agent:
    """A durable agent whose MODEL is supplied by the caller (typically a
    FunctionModel raising a deliberate failure).

    Same capability shape as fake_durable_agent, with the caller's activity
    config (a test may deliberately opt out of the shared bound — e.g. the
    assessment discover-exception test's 1-attempt config) and the same
    ResolveModelId pin: without it the activity rebuilds the workflow-side
    REAL agent's model string via infer_model and calls a real provider
    instead of running the caller's failing model (research.md R9). T006:
    the resolver records `(name, model_id)` like the TestModel fakes, but
    still returns the caller's failing model unchanged."""

    def _resolve(ctx, model_id: str | None):
        MODEL_RESOLUTIONS.append((name, model_id))
        return model

    agent = Agent(
        model,
        name=name,
        output_type=output_type,
        capabilities=[
            TemporalDurability(
                activity_config=activity_config,
                model_activity_config={"heartbeat_timeout": None},
            ),
            ResolveModelId(_resolve),
        ],
    )
    return agent
