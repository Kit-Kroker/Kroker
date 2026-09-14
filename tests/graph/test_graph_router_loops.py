"""E-73 GraphRouter loop semantics (spec §6.2 step 5, §6.5, §6.7): region
invalidation, slot survival, traversal counters, issue-time unavailable-port
snapshots, ESCALATED, and the two reproduction claims (`_revisable_stage`,
the code fix loop)."""

from __future__ import annotations

from pathlib import Path

from sdlc.graph import from_yaml
from sdlc.graph.node_types import NODE_TYPES
from tests.graph.fixtures.registries import (
    FIX_LOOP,
    GENERIC,
    edge,
    fix_loop_graph,
    graph,
    node,
    roles,
)
from tests.graph.fixtures.routing import (
    Run,
    disjoint_loops_graph,
    nested_loops_graph,
    running_target_graph,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _pre_code(*, plan_revises_architect: bool = False) -> Run:
    g = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    if plan_revises_architect:
        edges = [e for e in g.edges if (e.source, e.source_port) != ("plan", "revise")]
        g = graph(list(g.nodes), [*edges, edge("plan.revise", "architect.guidance", bound=1)])
    return Run(g, NODE_TYPES, roles())


def _to_architecture_gate(run: Run) -> None:
    run.emit("intake#1", "ok")
    run.emit("researcher#1", "brief")
    run.emit("research#1", "approve")
    run.emit("clarifier#1", "requirements", "reqs")
    run.emit("architect#1", "spec", "spec1")


# ---- (2) + (10): _revisable_stage reproduction, upstream slot survival -----------


def test_architecture_revise_twice_then_final_gate():
    """max_traversals == max_gate_rounds == 2 reproduces role_host.py:237-271:
    rounds 1..2 may revise; round 3 is the final gate (revise exhausted)."""
    run = _pre_code()
    _to_architecture_gate(run)
    assert run.activation("architecture#1").unavailable_ports == {}

    step = run.emit("architecture#1", "revise", "g1")
    assert [a.activation_id for a in step.activations] == ["architect#2"]
    # Skeptic F1: clarifier's requirements survive the invalidation.
    assert run.activation("architect#2").inputs == {"guidance": "g1", "requirements": "reqs"}
    run.emit("architect#2", "spec", "spec2")
    assert run.activation("architecture#2").unavailable_ports == {}

    run.emit("architecture#2", "revise", "g2")
    assert run.activation("architect#3").inputs == {"guidance": "g2", "requirements": "reqs"}
    run.emit("architect#3", "spec", "spec3")
    assert run.activation("architecture#3").unavailable_ports == {"revise": "exhausted"}
    assert run.state.traversals == {"architecture.revise->architect.guidance": 2}

    step = run.emit("architecture#3", "approve", "spec3")
    assert run.activation("planner#1").inputs == {"requirements": "reqs", "spec": "spec3"}
    assert step.outcome == "running"


def test_emission_on_an_exhausted_port_escalates_and_late_redelivery_is_dropped():
    run = _pre_code()
    _to_architecture_gate(run)
    run.emit("architecture#1", "revise")
    run.emit("architect#2", "spec")
    run.emit("architecture#2", "revise")
    run.emit("architect#3", "spec")
    step = run.emit("architecture#3", "revise")
    assert step.outcome == "escalated"
    assert step.reason == "architecture.revise: exhausted"
    assert step.cancelled == ()  # the emitter is retired, not cancelled
    assert "architecture#3" in run.state.retired
    assert run.state.traversals == {"architecture.revise->architect.guidance": 2}  # not applied
    step = run.emit("architecture#3", "revise")
    assert step.outcome == "escalated"
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [
        ("architecture#3", "post_terminal")
    ]


# ---- (3): the code fix loop (stages/code/step.py:548-947) -------------------------


def test_fix_loop_reproduces_max_fix_attempts_and_task_gate_rounds():
    run = Run(fix_loop_graph(max_fix_attempts=2, max_gate_rounds=2), FIX_LOOP)
    run.emit("start#1", "ok", "task")

    def qa_fails(k: int) -> None:
        """The qa handler: `fail` while available, else `escalate` (spec §6.5)."""
        run.emit(f"coder#{k}", "patch", f"p{k}")
        qa = run.activation(f"qa#{k}")
        port = "escalate" if "fail" in qa.unavailable_ports else "fail"
        run.emit(qa.activation_id, port, f"issues{k}")

    # budget = max_fix_attempts + 1 = 3 attempts, then the task gate
    for k in (1, 2, 3):
        qa_fails(k)
    assert run.activation("qa#3").unavailable_ports == {"fail": "exhausted"}
    assert run.live() == ["task#1"]
    assert run.activation("coder#2").inputs == {"guidance": "issues1", "task": "task"}

    # a gate REVISE grants exactly ONE more attempt (step.py:914), twice
    for gate_round, attempt in ((1, 4), (2, 5)):
        assert run.activation(f"task#{gate_round}").unavailable_ports == {}
        run.emit(f"task#{gate_round}", "revise", f"operator{gate_round}")
        assert run.activation(f"coder#{attempt}").inputs == {
            "guidance": f"operator{gate_round}",
            "task": "task",
        }
        qa_fails(attempt)
        assert f"task#{gate_round + 1}" in run.live()

    # round 3 is past max_gate_rounds: revise is exhausted, so the handler maps
    # an operator REVISE to `reject` (spec §6.5) -- REJECTED, not ESCALATED
    assert run.activation("task#3").unavailable_ports == {"revise": "exhausted"}
    step = run.emit("task#3", "reject")
    assert step.outcome == "rejected"
    assert [a for a in run.issued() if a.startswith("coder#")] == [
        f"coder#{k}" for k in range(1, 6)
    ]


# ---- (4): an outer loop invalidates a downstream consumer --------------------------


def test_plan_revise_to_architect_invalidates_planner_but_not_clarifier_tokens():
    run = _pre_code(plan_revises_architect=True)
    _to_architecture_gate(run)
    run.emit("architecture#1", "approve", "spec1")
    run.emit("planner#1", "plan", "plan1")
    step = run.emit("plan#1", "revise", "wrong-spec")
    assert [a.activation_id for a in step.activations] == ["architect#2"]
    assert run.activation("architect#2").inputs == {
        "guidance": "wrong-spec",
        "requirements": "reqs",
    }
    slots = run.state.slots
    assert "clarifier.requirements->planner.requirements" in slots  # producer outside the region
    assert "architecture.approve->planner.spec" not in slots  # superseded artifact dropped
    assert run.state.nodes["planner"].status == "pending"
    assert run.state.nodes["planner"].round == 1  # rounds never reset


# ---- (16): the documented known limitation (spec §6.5, skeptic F4) -----------------


def test_reentered_spent_inner_loop_starts_at_its_final_gate():
    run = _pre_code(plan_revises_architect=True)
    _to_architecture_gate(run)
    for k in (1, 2):
        run.emit(f"architecture#{k}", "revise")
        run.emit(f"architect#{k + 1}", "spec")
    run.emit("architecture#3", "approve")
    run.emit("planner#1", "plan")
    run.emit("plan#1", "revise")
    run.emit("architect#4", "spec")
    assert run.activation("architecture#4").unavailable_ports == {"revise": "exhausted"}
    step = run.emit("architecture#4", "reject")  # an operator REVISE, mapped by the handler
    assert step.outcome == "rejected"
    assert step.reason == "architecture.reject"


# ---- (8): a bounded self-loop -------------------------------------------------------


def test_self_loop_emitter_is_not_cancelled_and_its_token_survives():
    run = Run(
        graph(
            [node("start", "start"), node("r", "retry")],
            [edge("start.ok", "r.trigger"), edge("r.redo", "r.again", bound=2)],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok", "t")
    step = run.emit("r#1", "redo", "x1")
    assert step.cancelled == ()
    assert run.activation("r#2").inputs == {"again": "x1", "trigger": "t"}
    run.emit("r#2", "redo", "x2")
    assert run.activation("r#3").inputs == {"again": "x2", "trigger": "t"}
    assert run.activation("r#3").unavailable_ports == {"redo": "exhausted"}
    assert run.emit("r#3", "out").outcome == "completed"


# ---- (5) + stale drop: nested concurrent loops ------------------------------------


def test_outer_loop_cancels_the_inner_loop_and_its_late_emission_is_stale():
    run = Run(nested_loops_graph(), GENERIC)
    run.emit("start#1", "ok")
    run.emit("a#1", "out", "A1")
    assert run.live() == ["ga#1", "r#1"]
    run.emit("r#1", "out", "R1")
    step = run.emit("gr#1", "revise", "fix-r")
    assert step.cancelled == ()  # ga is outside REGION(r)
    assert run.live() == ["ga#1", "r#2"]

    step = run.emit("ga#1", "revise", "fix-a")
    assert step.cancelled == ("r#2",)
    assert [a.activation_id for a in step.activations] == ["a#2"]
    assert run.state.traversals == {"ga.revise->a.guidance": 1, "gr.revise->r.guidance": 1}

    step = run.emit("r#2", "out", "late")
    assert step.activations == ()
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("r#2", "stale")]
    assert step.outcome == "running"


# ---- (15): disjoint concurrent loops (skeptic F7) ----------------------------------


def test_disjoint_loops_revise_independently():
    run = Run(disjoint_loops_graph(), GENERIC)
    run.emit("start#1", "ok")
    run.emit("a#1", "out")
    run.emit("b#1", "out")
    assert run.emit("ga#1", "revise").cancelled == ()
    step = run.emit("gb#1", "revise")
    assert step.cancelled == ()
    assert run.live() == ["a#2", "b#2"]


# ---- (13): a back token into a RUNNING target (revised T1, advisor A1) -------------


def test_back_token_into_a_running_target_retires_and_reruns_it():
    run = Run(running_target_graph(), GENERIC)
    run.emit("e#1", "ok", "go")
    assert run.live() == ["a#1", "v#1"]
    run.emit("a#1", "out")
    step = run.emit("g0#1", "reject")  # q dies -> u's optional port dies -> u ready
    assert [a.activation_id for a in step.activations] == ["u#1", "z#1"]
    assert "v#1" in run.live()  # the old T1 claimed this could not happen

    step = run.emit("u#1", "fix", "guide")
    assert step.cancelled == ("v#1",)
    assert [a.activation_id for a in step.activations] == ["u#2", "v#2"]
    assert run.activation("v#2").inputs == {"guidance": "guide", "trigger": "go"}
    assert run.state.nodes["q"].status == "dead"


# ---- (14): snapshot-available port into a target that died after issue (A2) ---------


def test_snapshot_available_port_into_a_now_dead_target_is_processed_then_reissued():
    run = Run(running_target_graph(dead_target_variant=True), GENERIC)
    run.emit("e#1", "ok")
    run.emit("a#1", "out")
    run.emit("g0#1", "reject")
    assert run.activation("u#1").unavailable_ports == {}  # v is pending, not dead, at issue
    run.emit("b#1", "out")
    run.emit("g1#1", "reject")
    assert run.state.nodes["v"].status == "dead"  # died after u#1 was issued

    step = run.emit("u#1", "fix")
    assert step.outcome == "running"  # T5: never ESCALATED on a snapshot-available port
    assert run.state.traversals == {"u.fix->v.guidance": 1}
    assert run.activation("u#2").unavailable_ports == {"fix": "target_dead"}
    assert run.state.nodes["v"].status == "dead"

    step = run.emit("u#2", "fix")
    assert step.outcome == "escalated"
    assert step.reason == "u.fix: target_dead"
    assert set(step.cancelled) == {"z#1", "z2#1"}
