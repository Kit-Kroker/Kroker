"""A proposer role on a graph node with an invalid model is a validation
problem (004 T019, FR-004 third entry path).

Graph node roles copy into the run's role config (workflows/graph_nodes/
base.py:135-137), so a typo there reaches a real call exactly like a CLI
override — it must be refused at graph validation, beside the ADR-6 check.
"""

from __future__ import annotations

from sdlc.graph.validate import ProblemCode, validate
from tests.graph.fixtures.registries import GENERIC, graph, node, roles


def _report(role_model: str | None):
    if role_model is None:
        critic = node("c", "critic")
    else:
        critic = node("c", "critic", role={"kind": "proposer", "model": role_model})
    return validate(graph([node("start", "start"), critic], []), GENERIC, roles=roles())


def _codes(report) -> list[str]:
    return [p.code.value for p in report.problems]


def test_proposer_role_with_invalid_model_is_a_problem():
    report = _report("openai/gpt-5.2")
    assert "role_model_invalid" in _codes(report), (
        f"a graph node carrying proposer role 'reviewer' with the invalid "
        f"model 'openai/gpt-5.2' must be refused at validation; got "
        f"{_codes(report)}"
    )
    problem = next(p for p in report.problems if p.code is ProblemCode.ROLE_MODEL_INVALID)
    assert problem.node == "c"
    assert "openai/gpt-5.2" in problem.message
    assert "provider:model" in problem.message


def test_proposer_role_with_valid_model_is_clean():
    report = _report("openai:gpt-5.2")
    assert "role_model_invalid" not in _codes(report)


def test_registry_model_on_an_unoverridden_node_stays_clean():
    report = _report(None)
    assert "role_model_invalid" not in _codes(report)
