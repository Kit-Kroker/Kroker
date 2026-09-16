"""E-74 §6: the registry after M1 -- additive to E-72, plus the post-plan half."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import NODE_TYPES, check_node_types, from_yaml, validate
from tests.graph.fixtures.registries import roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _table(type_):
    return {
        (p.direction, p.name): (p.payload, p.required, p.terminal) for p in NODE_TYPES[type_].ports
    }


def test_registry_is_healthy():
    assert check_node_types() == []


def test_catalog_types():
    assert sorted(NODE_TYPES) == [
        "analyze",
        "architect",
        "clarify",
        "code",
        "context",
        "deploy",
        "gate.architecture",
        "gate.plan",
        "gate.research",
        "intake",
        "merge",
        "plan",
        "plan_check",
        "research",
        "seed.plan",
        "seed.spec",
    ]


FAIL = ("NodeFailure", True, "failed")


@pytest.mark.parametrize(
    ("type_", "expected"),
    [
        (
            "intake",
            {
                ("out", "ok"): (None, True, None),
                ("out", "brownfield"): (None, True, None),
                ("out", "reject"): (None, True, "rejected"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "context",
            {
                ("in", "trigger"): (None, True, None),
                ("out", "map"): ("CodebaseMap", True, None),
                ("out", "reject"): (None, True, "rejected"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "research",
            {
                ("in", "trigger"): (None, False, None),
                ("in", "guidance"): ("GateDecision", False, None),
                ("in", "codebase_map"): ("CodebaseMap", False, None),
                ("out", "brief"): ("ResearchBrief", True, None),
                ("out", "reject"): (None, True, "rejected"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "plan_check",
            {
                ("in", "plan"): ("ImplementationPlan", True, None),
                ("out", "ok"): ("ImplementationPlan", True, None),
                ("out", "halt"): (None, True, "failed"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "seed.spec",
            {
                ("in", "trigger"): (None, False, None),
                ("out", "spec"): ("ArchitectureSpec", True, None),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "seed.plan",
            {
                ("in", "trigger"): (None, False, None),
                ("out", "plan"): ("ImplementationPlan", True, None),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "code",
            {
                ("in", "plan"): ("ImplementationPlan", True, None),
                ("out", "results"): ("BuildResult", True, None),
                ("out", "halt"): (None, True, "failed"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "analyze",
            {
                ("in", "results"): ("BuildResult", True, None),
                ("in", "plan"): ("ImplementationPlan", True, None),
                ("out", "analysis"): ("AnalyzeResult", True, None),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "merge",
            {
                ("in", "results"): ("BuildResult", True, None),
                ("in", "plan"): ("ImplementationPlan", True, None),
                ("in", "spec"): ("ArchitectureSpec", True, None),
                ("in", "analysis"): ("AnalyzeResult", True, None),
                ("out", "pr"): ("PullRequest", True, None),
                ("out", "reject"): (None, True, "rejected"),
                ("out", "fail"): FAIL,
            },
        ),
        (
            "deploy",
            {
                ("in", "pr"): ("PullRequest", True, None),
                ("out", "done"): (None, True, None),
                ("out", "fail"): FAIL,
            },
        ),
    ],
)
def test_catalog_ports(type_, expected):
    assert _table(type_) == expected


@pytest.mark.parametrize(
    ("type_", "canonical", "budget"),
    [
        ("intake", "intake", "none"),
        ("context", "context", "none"),
        ("research", "research", "continuing"),
        ("clarify", "clarify", "continuing"),
        ("architect", "architecture", "none"),
        ("plan", "planning", "none"),
        ("gate.research", "research", "none"),
        ("gate.architecture", "architecture", "exiting"),
        ("gate.plan", "planning", "exiting"),
        ("plan_check", "planning", "none"),
        ("seed.spec", "architecture", "none"),
        ("seed.plan", "planning", "none"),
        ("code", "code", "none"),
        ("analyze", "analyze", "continuing"),
        ("merge", "quality_gate", "none"),
        ("deploy", "deploy", "none"),
    ],
)
def test_catalog_metadata(type_, canonical, budget):
    spec = NODE_TYPES[type_]
    assert (spec.canonical_stage, spec.budget_after) == (canonical, budget)


def test_stage_types_carry_fail_and_gates_do_not():
    for name, spec in sorted(NODE_TYPES.items()):
        ports = {p.name for p in spec.ports}
        assert ("fail" in ports) == (spec.kind == "stage"), name


def test_e72_fixture_still_validates_clean():
    graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    assert validate(graph, roles=roles()).problems == ()
