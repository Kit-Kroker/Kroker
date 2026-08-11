from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.eval.fixtures import FixtureError, build_fixture

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
AGENTS = Path(__file__).resolve().parents[1] / "agents"


def test_clarify_fixture_is_deterministic():
    a = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    b = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    assert a.prompt == b.prompt


def test_clarify_prompt_matches_what_the_workflow_sends():
    """The fixture must equal clarify_prompt(IdeaBrief.model_dump_json(), [])
    built the same way BenchmarkWorkflow builds its IdeaBrief
    (benchmarks/workflow.py:157-158)."""
    import yaml
    from sdlc.models import IdeaBrief, ProjectMode
    from sdlc.prompts import clarify_prompt

    spec = yaml.safe_load(
        (CASES / "add-login-greenfield" / "case.yaml").read_text(
            encoding="utf-8"))
    idea = IdeaBrief(title=spec["case_id"], description=spec["description"],
                     mode=ProjectMode(spec["mode"]),
                     repo_url=spec.get("repo_url"))
    expected = clarify_prompt(idea.model_dump_json(), [])

    assert build_fixture("clarify", "add-login-greenfield",
                         CASES, AGENTS).prompt == expected


def test_fixture_carries_the_role_registry_model():
    fx = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    assert fx.model == "anthropic:glm-5.2"
    assert fx.source_run_id == "_built"
    assert fx.role == "clarify"
    assert fx.case == "add-login-greenfield"


def test_unknown_case_raises_with_the_path():
    with pytest.raises(FixtureError) as e:
        build_fixture("clarify", "no-such-case", CASES, AGENTS)
    assert "no-such-case" in str(e.value)


def test_deps_role_is_refused():
    with pytest.raises(FixtureError) as e:
        build_fixture("architect", "add-login-greenfield", CASES, AGENTS)
    assert "deps" in str(e.value).lower()
