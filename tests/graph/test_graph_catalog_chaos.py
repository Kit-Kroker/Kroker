"""Chaos + edge-case characterization for the E-74 Task 10 catalog additions.

RED until the post-plan half of the registry lands: ``code`` / ``analyze`` /
``merge`` / ``deploy`` do not exist in ``NODE_TYPES`` yet, no stage carries a
``fail`` port, and no type sets a non-default ``budget_after``. Membership is
pre-asserted in each test so every RED is a clean assertion failure, not a
KeyError. ``test_no_duplicate_port_names_on_any_node_type`` is an invariant
that already holds and stays green by design.

Pins the edge behaviour the task specifies:
- post-plan port tables: direction, payload, required, multiplicity (all
  "one" -- the post-plan half introduces no collect ports) and terminal
- every kind="stage" type carries exactly one out-port ``fail`` with
  payload "NodeFailure" and terminal "failed"; gate types carry none
- exactly five types budget after their emission (continuing: research,
  clarify, analyze; exiting: gate.architecture, gate.plan), all others "none"
- no node type declares a port name twice
- the post-plan chain plan->code->analyze->merge->deploy is
  ports_compatible end to end, while mismatches stay incompatible
"""

from __future__ import annotations

import pytest

from sdlc.graph.node_types import NODE_TYPES, ports_compatible

POST_PLAN = ("code", "analyze", "merge", "deploy")

# (direction, name, payload, required, multiplicity, terminal)
EXPECTED_PORTS = {
    "code": (
        ("in", "plan", "ImplementationPlan", True, "one", None),
        ("out", "results", "BuildResult", True, "one", None),
        ("out", "halt", None, True, "one", "failed"),
        ("out", "fail", "NodeFailure", True, "one", "failed"),
    ),
    "analyze": (
        ("in", "results", "BuildResult", True, "one", None),
        ("in", "plan", "ImplementationPlan", True, "one", None),
        ("out", "analysis", "AnalyzeResult", True, "one", None),
        ("out", "fail", "NodeFailure", True, "one", "failed"),
    ),
    "merge": (
        ("in", "results", "BuildResult", True, "one", None),
        ("in", "plan", "ImplementationPlan", True, "one", None),
        ("in", "spec", "ArchitectureSpec", True, "one", None),
        ("in", "analysis", "AnalyzeResult", True, "one", None),
        ("out", "pr", "PullRequest", True, "one", None),
        ("out", "reject", None, True, "one", "rejected"),
        ("out", "fail", "NodeFailure", True, "one", "failed"),
    ),
    "deploy": (
        ("in", "pr", "PullRequest", True, "one", None),
        ("out", "done", None, True, "one", None),
        ("out", "fail", "NodeFailure", True, "one", "failed"),
    ),
}

BUDGETED = {
    "research": "continuing",
    "clarify": "continuing",
    "analyze": "continuing",
    "gate.architecture": "exiting",
    "gate.plan": "exiting",
}


def _require_types(*type_: str) -> None:
    missing = sorted(set(type_) - set(NODE_TYPES))
    assert missing == [], f"not in NODE_TYPES yet: {missing}"


def _port(type_: str, name: str):
    return next(p for p in NODE_TYPES[type_].ports if p.name == name)


# ---- post-plan port tables ---------------------------------------------------


@pytest.mark.parametrize("type_", POST_PLAN)
def test_post_plan_port_directions_and_multiplicities(type_):
    _require_types(type_)

    actual = {
        (p.direction, p.name): (p.payload, p.required, p.multiplicity, p.terminal)
        for p in NODE_TYPES[type_].ports
    }
    expected = {
        (direction, name): (payload, required, multiplicity, terminal)
        for direction, name, payload, required, multiplicity, terminal in EXPECTED_PORTS[type_]
    }
    assert actual == expected


# ---- the fail port on every stage --------------------------------------------


def test_every_stage_has_exactly_one_nodefailure_fail_port_and_gates_do_not():
    problems = []
    for name, spec in sorted(NODE_TYPES.items()):
        fail = [p for p in spec.ports if p.name == "fail"]
        if spec.kind == "stage":
            if (
                len(fail) != 1
                or fail[0].direction != "out"
                or fail[0].payload != "NodeFailure"
                or fail[0].terminal != "failed"
            ):
                problems.append(name)
        elif fail:
            problems.append(name)
    assert problems == []


# ---- the budget_after partition -----------------------------------------------


def test_exactly_five_types_carry_a_budget_and_the_rest_do_not():
    budgets = {name: spec.budget_after for name, spec in NODE_TYPES.items()}
    assert budgets == {**{name: "none" for name in NODE_TYPES}, **BUDGETED}


# ---- port-name uniqueness ------------------------------------------------------


def test_no_duplicate_port_names_on_any_node_type():
    offenders = {}
    for name, spec in NODE_TYPES.items():
        seen = [p.name for p in spec.ports]
        dupes = sorted({n for n in seen if seen.count(n) > 1})
        if dupes:
            offenders[name] = dupes
    assert offenders == {}


# ---- ports_compatible across the post-plan chain -------------------------------


def test_post_plan_chain_is_port_compatible_end_to_end():
    _require_types(*POST_PLAN)

    chain = [
        ("plan", "plan", "code", "plan"),
        ("plan", "plan", "analyze", "plan"),
        ("plan", "plan", "merge", "plan"),
        ("architect", "spec", "merge", "spec"),
        ("code", "results", "analyze", "results"),
        ("code", "results", "merge", "results"),
        ("analyze", "analysis", "merge", "analysis"),
        ("merge", "pr", "deploy", "pr"),
    ]
    broken = [
        (src, src_port, dst, dst_port)
        for src, src_port, dst, dst_port in chain
        if not ports_compatible(_port(src, src_port), _port(dst, dst_port))
    ]
    assert broken == []


def test_port_compatibility_still_rejects_mismatches():
    _require_types("code", "analyze", "deploy")

    results = _port("code", "results")
    assert not ports_compatible(results, _port("analyze", "plan"))  # payload mismatch
    assert not ports_compatible(results, results)  # out -> out is not a connection
    assert not ports_compatible(
        _port("deploy", "done"), _port("analyze", "plan")
    )  # signal -> named
