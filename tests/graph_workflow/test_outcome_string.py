"""E-74 §5.6 wire contract and the D8 FAILURE_TYPES pin (fast tier)."""

from __future__ import annotations

import pytest
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import FailureError
from temporalio.worker import Replayer

from sdlc.graph import validate
from sdlc.graph.router import NodeState, RouterState
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.graph_catalog import SHIPPED
from sdlc.workflows.graph_dispatch import FAILURE_TYPES, DispatchOutcome, outcome_string
from tests.graph.fixtures.registries import roles

TOPOLOGY = validate(SHIPPED["default"], roles=roles()).topology


def test_failure_types_cover_temporal_and_the_plugin():
    config = Replayer(
        workflows=[FeatureWorkflow],
        data_converter=pydantic_data_converter,
        plugins=[PydanticAIPlugin()],
    ).config(active_config=True)
    assert set(config["workflow_failure_exception_types"]) <= set(FAILURE_TYPES)
    assert FailureError in FAILURE_TYPES


def _state(outcome, reason=None, nodes=None) -> RouterState:
    return RouterState(nodes=nodes or {"intake": NodeState()}, outcome=outcome, reason=reason)


def _o(state, *, terminal=None, sink=None, budget=False) -> DispatchOutcome:
    return DispatchOutcome(
        state=state,
        terminal_result=terminal,
        last_sink_result=sink,
        budget_halted=budget,
        stored_failure=None,
    )


DONE = NodeState(round=1, status="done", taken_port="done")
MERGED = NodeState(round=1, status="done", taken_port="pr")


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (_o(_state("rejected", "budget"), budget=True), "rejected:budget"),
        (_o(_state("rejected", "architecture.reject"), budget=True), "rejected:budget"),
        (
            _o(
                _state("rejected", "intake.reject"),
                terminal="rejected:intake (not a git repository)",
            ),
            "rejected:intake (not a git repository)",
        ),
        (
            _o(_state("rejected", "merge.reject"), terminal="rejected:merge:advisory"),
            "rejected:merge:advisory",
        ),
        (_o(_state("rejected", "architecture.reject")), "rejected:architecture"),
        (_o(_state("rejected", "plan.reject")), "rejected:plan"),
        (
            _o(
                _state("failed", "plan_check.halt"),
                terminal="failed:plan-validation:dependency cycle: a -> b -> a",
            ),
            "failed:plan-validation:dependency cycle: a -> b -> a",
        ),
        (
            _o(_state("failed", "code.halt"), terminal="failed:dependency-cycle"),
            "failed:dependency-cycle",
        ),
        (
            _o(_state("failed", "code.halt"), terminal="failed:integration-conflict:t1"),
            "failed:integration-conflict:t1",
        ),
        (
            _o(_state("failed", "code.halt"), terminal="failed:quarantined-tasks"),
            "failed:quarantined-tasks",
        ),
        (
            _o(_state("escalated", "architecture.revise: exhausted")),
            "escalated:architecture.revise: exhausted",
        ),
        (
            _o(_state("completed"), sink="deployed:https://example.test/pr/1"),
            "deployed:https://example.test/pr/1",
        ),
        (
            _o(_state("completed"), sink="merged-not-deployed:https://example.test/pr/1"),
            "merged-not-deployed:https://example.test/pr/1",
        ),
        (_o(_state("completed", nodes={"deploy": DONE, "merge": MERGED})), "completed:deploy"),
    ],
)
def test_outcome_string_table(outcome, expected):
    assert outcome_string(outcome, TOPOLOGY) == expected
