"""E-74 §7.1: the shipped graphs route today's stage order under E-73 readiness."""

from __future__ import annotations

from sdlc.graph import NODE_TYPES
from sdlc.workflows.graph_catalog import SHIPPED
from tests.graph.fixtures.registries import roles
from tests.graph.fixtures.routing import Run


def _run(name: str) -> Run:
    return Run(SHIPPED[name], NODE_TYPES, roles())


def _tail(run: Run) -> None:
    run.emit("plan_check#1", "ok")
    assert run.live() == ["code#1"]
    run.emit("code#1", "results")
    assert run.live() == ["analyze#1"]
    run.emit("analyze#1", "analysis")
    assert run.live() == ["merge#1"]
    run.emit("merge#1", "pr")
    assert run.live() == ["deploy#1"]
    assert run.emit("deploy#1", "done").outcome == "completed"


def test_default_greenfield_with_architecture_revise_to_final_gate():
    run = _run("default")
    run.emit("intake#1", "ok")
    assert run.live() == ["clarify#1"]
    run.emit("clarify#1", "requirements")
    assert run.live() == ["architect#1"]
    run.emit("architect#1", "spec")
    run.emit("architecture#1", "revise")
    run.emit("architect#2", "spec")
    run.emit("architecture#2", "revise")
    run.emit("architect#3", "spec")
    assert run.activation("architecture#3").unavailable_ports == {"revise": "exhausted"}
    run.emit("architecture#3", "approve")
    assert run.live() == ["planner#1"]
    run.emit("planner#1", "plan")
    run.emit("plan#1", "approve")
    assert run.live() == ["plan_check#1"]
    _tail(run)


def test_default_brownfield_maps_context_first():
    run = _run("default")
    run.emit("intake#1", "brownfield")
    assert run.live() == ["context#1"]
    run.emit("context#1", "map")
    assert run.live() == ["clarify#1"]
    run.emit("clarify#1", "requirements")
    assert run.activation("architect#1").inputs["codebase_map"] == "context#1:map"


def test_default_architecture_reject_ends_rejected():
    run = _run("default")
    run.emit("intake#1", "ok")
    run.emit("clarify#1", "requirements")
    run.emit("architect#1", "spec")
    step = run.emit("architecture#1", "reject")
    assert (step.outcome, step.reason) == ("rejected", "architecture.reject")


def test_research_brownfield_orders_context_research_clarify():
    run = _run("default-research")
    run.emit("intake#1", "brownfield")
    assert run.live() == ["context#1"]
    run.emit("context#1", "map")
    assert run.live() == ["research#1"]
    run.emit("research#1", "brief")
    assert run.live() == ["clarify#1"]


def test_research_greenfield_runs_research_first():
    run = _run("default-research")
    run.emit("intake#1", "ok")
    assert run.live() == ["research#1"]


def test_seeded_skips_pre_code_and_joins_at_merge():
    run = _run("seeded")
    run.emit("intake#1", "ok")
    assert run.live() == ["seed_plan#1", "seed_spec#1"]
    run.emit("seed_plan#1", "plan")
    assert run.live() == ["code#1", "seed_spec#1"]
    run.emit("seed_spec#1", "spec")
    run.emit("code#1", "results")
    run.emit("analyze#1", "analysis")
    run.emit("merge#1", "pr")
    assert run.emit("deploy#1", "done").outcome == "completed"
