# tests/graph/test_run_view_models.py
"""E-75 spec §4.1: the raw facts GraphWorkflow's graph_view query returns."""

from __future__ import annotations

import contextvars
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from sdlc.core.models import DotState, RunState
from sdlc.graph import (
    ACTIVATION,
    ActivationFacts,
    GraphRunView,
    PendingFact,
    RouterState,
    UnroutedFailure,
    pending_kind,
)
from sdlc.graph.router import NodeState
from sdlc.pending import PendingDecision

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def _state() -> RouterState:
    return RouterState(nodes={"a": NodeState(round=1, status="running")})


def test_dot_state_is_the_stage_dots_vocabulary():
    # interfaces/ui/src/components/stage_dots/StageDots.vue:4
    assert set(get_args(DotState)) == {"pending", "active", "done", "blocked", "failed", "skipped"}


def test_run_state_stage_marks_defaults_to_none():
    s = RunState(run_id="r", title="t", mode="greenfield", status="running", started_at=AT)
    assert s.stage_marks is None
    assert RunState.model_validate(
        {**s.model_dump(mode="json"), "stage_marks": {"intake": "done"}}
    ).stage_marks == {"intake": "done"}


def test_view_round_trips_through_json_and_sorts_its_collections():
    view = GraphRunView(
        graph_sha="s",
        state=_state(),
        activations={
            "b#1": ActivationFacts(started_at=AT),
            "a#1": ActivationFacts(started_at=AT, ended_at=AT, cost_usd=1.5),
        },
        pending=(
            PendingFact(key="z#1", activation_id=None, kind="gate"),
            PendingFact(key="Q1", activation_id="a#1", kind="clarify"),
        ),
        unrouted_failure=UnroutedFailure(activation_id="a#1", error_type="ApplicationError"),
    )
    assert list(view.activations) == ["a#1", "b#1"]
    assert [p.key for p in view.pending] == ["Q1", "z#1"]
    assert GraphRunView.model_validate_json(view.model_dump_json()) == view


def test_view_is_frozen_and_forbids_extra_fields():
    view = GraphRunView(graph_sha="s", state=_state())
    with pytest.raises(ValidationError):
        view.graph_sha = "t"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        GraphRunView.model_validate({"graph_sha": "s", "state": _state(), "payloads": {}})


def test_pending_kind_covers_every_pending_decision_variant():
    union = get_args(get_args(PendingDecision)[0])
    kinds = {get_args(cls.model_fields["kind"].annotation)[0] for cls in union}
    assert {k: pending_kind(k) for k in sorted(kinds)} == {
        "clarify": "clarify",
        "merge_gate": "gate",
        "stage_gate": "gate",
        "task_escalation": "escalation",
    }
    with pytest.raises(KeyError):
        pending_kind("unknown")


def test_activation_defaults_to_none_and_a_set_never_leaks_out_of_its_context():
    assert ACTIVATION.get() is None

    def inner() -> str | None:
        ACTIVATION.set("a#1")
        return ACTIVATION.get()

    assert contextvars.copy_context().run(inner) == "a#1"
    assert ACTIVATION.get() is None
