"""FR-301 D2/D3: the plan validators feed the plan gate; failures revise the planner.

Router-level wiring over the shipped graphs (E-73 readiness drives the
order; E-74's dispatch rides it) plus the pre-reorder characterization
that pins in-flight runs: the graph is pinned in the workflow INPUT, so a
run started before the reorder keeps executing the frozen literal in
tests/graph/fixtures/pre_reorder.py -- gate first, halt on a validator
failure -- under the post-reorder registry and handlers.
"""

from __future__ import annotations

import pytest

from sdlc.core.models import RoleConfig
from sdlc.graph import NODE_TYPES, validate
from sdlc.workflows.graph_catalog import SHIPPED
from tests.graph.fixtures.pre_reorder import pre_reorder_default
from tests.graph.fixtures.registries import roles
from tests.graph.fixtures.routing import Run

# Every shipped graph with plan stages; seeded has none (seed.plan feeds
# code directly, no gate.plan and no plan_check) and stays untouched.
REORDERED = ("default", "default-requirements", "default-research", "default-constitution")


@pytest.mark.parametrize("name", REORDERED)
def test_every_reordered_graph_wires_ok_into_the_gate_and_revise_back(name):
    """planner -> plan_check; plan_check.ok is the gate's ONLY artifact
    feed; plan_check.revise loops the planner's guidance port at bound 2;
    plan.approve (not plan_check.ok) feeds code/analyze/merge."""
    extra = {"product": RoleConfig(kind="proposer", model="anthropic:glm-5.2")}
    report = validate(SHIPPED[name], NODE_TYPES, roles=roles(**extra))
    assert report.topology is not None, [p.message for p in report.problems]
    t = report.topology
    ok = t.out_ports["plan_check"]["ok"]
    assert len(ok) == 1 and t.edges[ok[0]] == ("plan_check", "ok", "plan", "artifact")
    gate_feed = t.in_ports["plan"]["artifact"]
    assert {t.edges[e][:2] for e in gate_feed.forward_edges} == {("plan_check", "ok")}
    revise = t.out_ports["plan_check"]["revise"]
    assert len(revise) == 1 and t.edges[revise[0]] == (
        "plan_check",
        "revise",
        "planner",
        "guidance",
    )
    assert t.bounds[revise[0]] == 2
    planner_feed = t.in_ports["planner"]["guidance"]
    assert sorted(t.edges[e][:2] for e in planner_feed.back_edges) == [
        ("plan", "revise"),
        ("plan_check", "revise"),
    ]
    approve = t.out_ports["plan"]["approve"]
    assert sorted(t.edges[e][2:] for e in approve) == [
        ("analyze", "plan"),
        ("code", "plan"),
        ("merge", "plan"),
    ]


def test_the_ok_port_feeds_the_plan_gate_and_approve_feeds_code():
    run = Run(SHIPPED["default"], NODE_TYPES, roles())
    _drive_to_plan_check(run)
    run.emit("plan_check#1", "ok")
    assert run.live() == ["plan#1"]
    assert run.activation("plan#1").inputs == {"artifact": "plan_check#1:ok"}
    run.emit("plan#1", "approve")
    assert run.live() == ["code#1"]


def test_a_validator_failure_revises_the_planner_and_increments_its_round():
    run = Run(SHIPPED["default"], NODE_TYPES, roles())
    _drive_to_plan_check(run)
    run.emit("plan_check#1", "revise")
    assert run.live() == ["planner#2"]
    planner2 = run.activation("planner#2")
    assert planner2.round == 2
    assert planner2.inputs["guidance"] == "plan_check#1:revise"


def test_two_revise_rounds_exhaust_the_loop_then_a_third_failure_halts():
    """max_traversals: 2 buys two revise rounds; the third invalid plan
    activates plan_check with revise exhausted, and its failure keeps
    today's terminal halt (no escalation on an unavailable port)."""
    run = Run(SHIPPED["default"], NODE_TYPES, roles())
    _drive_to_plan_check(run)
    run.emit("plan_check#1", "revise")
    run.emit("planner#2", "plan")
    run.emit("plan_check#2", "revise")
    run.emit("planner#3", "plan")
    assert run.live() == ["plan_check#3"]
    assert run.activation("plan_check#3").unavailable_ports == {"revise": "exhausted"}
    step = run.emit("plan_check#3", "halt")
    assert (step.outcome, step.reason) == ("failed", "plan_check.halt")


def test_the_gates_own_revise_loop_survives_the_reorder():
    run = Run(SHIPPED["default"], NODE_TYPES, roles())
    _drive_to_plan_check(run)
    run.emit("plan_check#1", "ok")
    run.emit("plan#1", "revise")
    assert run.live() == ["planner#2"]
    run.emit("planner#2", "plan")
    run.emit("plan_check#2", "ok")
    run.emit("plan#2", "approve")
    assert run.live() == ["code#1"]


def test_pre_reorder_graph_keeps_the_gate_first_and_halts_on_validation_failure():
    """The in-flight-run pin: the frozen pre-reorder literal, validated
    against the POST-reorder registry, still gates before validating and
    still ends failed through the edgeless halt port."""
    run = Run(pre_reorder_default(), NODE_TYPES, roles())
    _drive_to_plan_check_pre_reorder(run)
    assert run.live() == ["plan#1"]
    run.emit("plan#1", "approve")
    assert run.live() == ["plan_check#1"]
    assert run.activation("plan_check#1").unavailable_ports == {}
    step = run.emit("plan_check#1", "halt")
    assert (step.outcome, step.reason) == ("failed", "plan_check.halt")


def _drive_to_plan_check(run: Run) -> None:
    run.emit("intake#1", "ok")
    assert run.live() == ["clarify#1"]
    run.emit("clarify#1", "requirements")
    run.emit("architect#1", "spec")
    run.emit("architecture#1", "approve")
    assert run.live() == ["planner#1"]
    run.emit("planner#1", "plan")
    assert run.live() == ["plan_check#1"]


def _drive_to_plan_check_pre_reorder(run: Run) -> None:
    run.emit("intake#1", "ok")
    run.emit("clarify#1", "requirements")
    run.emit("architect#1", "spec")
    run.emit("architecture#1", "approve")
    run.emit("planner#1", "plan")
