"""E-73 validate.py T3 node configuration (spec §7.2-§7.4): role/gate
placement, loader-owned fields, kind consistency (the `role: {}` traps),
registry presence, ADR-6 over graphs, reserved gate names."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.core.models import HarnessKind, RoleConfig
from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.graph.validate import (
    ADR6_COMBINATION_CAP,
    RESERVED_GATE_NAMES,
    ProblemCode,
    ValidationReport,
    validate,
)
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"
C = ProblemCode


def _problems(report: ValidationReport, code: ProblemCode) -> list[tuple[str | None, str]]:
    return [(p.node, p.message) for p in report.problems if p.code is code]


def _nodes(report: ValidationReport, code: ProblemCode) -> list[str | None]:
    return [p.node for p in report.problems if p.code is code]


def _generic(*nodes, **role_overrides) -> ValidationReport:
    return validate(
        graph([node("start", "start"), *nodes], []), GENERIC, roles=roles(**role_overrides)
    )


def _seed(*nodes, **role_overrides) -> ValidationReport:
    return validate(
        graph([node("intake", "intake"), *nodes], []), NODE_TYPES, roles=roles(**role_overrides)
    )


def test_role_on_roleless_type():
    assert _nodes(
        _generic(node("w", "work", role={"kind": "proposer"})), C.ROLE_ON_ROLELESS_TYPE
    ) == ["w"]


def test_gate_on_non_gate():
    assert _nodes(_generic(node("w", "work", gate={})), C.GATE_ON_NON_GATE) == ["w"]
    assert _nodes(_generic(node("g", "gate.art", gate={})), C.GATE_ON_NON_GATE) == []


@pytest.mark.parametrize(
    "role",
    [
        {"kind": "harness", "harness": "opencode", "instructions": "you are dev"},
        {"kind": "harness", "harness": "opencode", "tool_files": ["tools/x.py"]},
    ],
)
def test_loader_owned_field(role):
    assert _nodes(_generic(node("b", "builder", role=role)), C.LOADER_OWNED_FIELD) == ["b"]


def test_role_not_in_registry_with_and_without_override():
    """E-72 §5's OPTIONAL_ROLES clause: `research` on a tree without
    agents/research/ -- a problem, never a KeyError."""
    report = _seed(
        node("plain", "research"),
        node("tuned", "research", role={"kind": "research", "provider": "fake"}),
        research=None,
    )
    assert _nodes(report, C.ROLE_NOT_IN_REGISTRY) == ["plain", "tuned"]
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == []


@pytest.mark.parametrize("type_", ["architect", "clarify", "plan", "research"])
def test_empty_role_on_proposer_or_research_type_is_a_kind_mismatch(type_):
    report = _seed(node("n", type_, role={}))
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == ["n"]
    assert _nodes(report, C.ROLE_HARNESS_MISSING) == []


def test_empty_role_on_harness_type_is_harness_missing():
    report = _generic(node("b", "builder", role={}))
    assert _nodes(report, C.ROLE_HARNESS_MISSING) == ["b"]
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == []


def test_research_override_without_provider():
    report = _seed(node("r", "research", role={"kind": "research"}))
    assert _nodes(report, C.RESEARCH_PROVIDER_MISSING) == ["r"]


def _wired(*builders) -> ValidationReport:
    """start fans out to each builder: a CLEAN graph apart from T3."""
    g = graph(
        [node("start", "start"), *builders],
        [edge("start.ok", f"{b.id}.trigger") for b in builders],
    )
    return validate(g, GENERIC, roles=roles())


def test_well_formed_overrides_are_clean():
    b = node(
        "b",
        "builder",
        role={"kind": "harness", "harness": "claude_code", "model": "zai-coding-plan/x"},
    )
    assert _wired(b).problems == ()


def test_reserved_gate_names_are_exactly_the_verified_handler_gates():
    assert RESERVED_GATE_NAMES == {
        "budget",
        "clarify",
        "crew_question",
        "deploy",
        "deploy_failed",
        "merge",
        "readiness",
        "risk",
        "tidy_up",
        "tool_approval",
    }
    assert not RESERVED_GATE_NAMES & {"research", "architecture", "plan"}


def test_reserved_gate_name_applies_to_gate_nodes_only():
    report = _generic(node("clarify", "gate.art"), node("merge", "work"))
    assert _nodes(report, C.RESERVED_GATE_NAME) == ["clarify"]


# ---- ADR-6 over graphs (spec U4, §7.4) ---------------------------------------


def _builder(id_: str, model: str):
    return node(id_, "builder", role={"kind": "harness", "harness": "opencode", "model": model})


def _critic(id_: str, model: str):
    return node(id_, "critic", role={"kind": "proposer", "model": model})


def test_adr6_same_family_override_is_a_violation():
    report = _generic(_builder("b", "anthropic:claude-x"))  # registry reviewer is anthropic
    [(_, message)] = _problems(report, C.ADR6_VIOLATION)
    assert "ADR-6 violation" in message


def test_adr6_cross_product_catches_one_divergent_dev_model():
    report = _generic(
        _builder("b1", "zai-coding-plan/glm-5.2"), _builder("b2", "anthropic:claude-x")
    )
    assert len(_problems(report, C.ADR6_VIOLATION)) == 1


def test_adr6_reports_each_distinct_breach_once():
    report = _generic(
        _builder("b1", "zai-coding-plan/glm-5.2"),
        _builder("b2", "anthropic:claude-x"),
        _critic("c1", "zai-coding-plan/other"),
        _critic("c2", "anthropic:other"),
    )
    messages = [m for _, m in _problems(report, C.ADR6_VIOLATION)]
    assert len(messages) == 2
    assert messages == sorted(messages)
    assert all(n is None for n, _ in _problems(report, C.ADR6_VIOLATION))


def test_adr6_divergence_that_respects_the_rule_is_legal():
    report = _wired(_builder("b1", "zai-coding-plan/glm-5.2"), _builder("b2", "openai:gpt-x"))
    assert report.problems == ()


def test_adr6_cap_fails_closed():
    builders = [_builder(f"b{i}", f"fam{i}:m") for i in range(17)]
    critics = [_critic(f"c{i}", f"other{i}:m") for i in range(16)]
    assert 17 * 16 > ADR6_COMBINATION_CAP
    report = _generic(*builders, *critics)
    assert _nodes(report, C.ADR6_COMBINATIONS_EXCEEDED) == [None]
    assert _problems(report, C.ADR6_VIOLATION) == []


def test_adr6_missing_reviewer_is_a_problem_not_a_crash():
    report = _generic(reviewer=None)
    [(_, message)] = _problems(report, C.ADR6_VIOLATION)
    assert "requires both" in message


def test_adr6_unused_roles_keep_their_registry_model():
    """A graph with no builder still checks the registry dev against a
    critic override (mirrors cli_roles)."""
    report = _generic(_critic("c", "zai-coding-plan/other"))
    assert len(_problems(report, C.ADR6_VIOLATION)) == 1


def test_seed_fixture_stays_clean_with_node_config_checks():
    report = validate(from_yaml(FIXTURE.read_text(encoding="utf-8")), roles=roles())
    assert report.problems == ()


def test_harness_kind_role_config_is_the_default_trap():
    """Pins the premise of role_harness_missing: RoleConfig() is harness-kind
    with no harness (core/models.py), so `role: {}` is not `role` absent."""
    empty = RoleConfig()
    assert empty.kind == "harness"
    assert empty.harness is None
    assert HarnessKind.OPENCODE.value == "opencode"
