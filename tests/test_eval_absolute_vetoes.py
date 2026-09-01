"""Vetoes gate at Layer 2: a veto failure is an ABSOLUTE failure.

Zero model calls -- the veto engine is pure and get_assert takes the output
as a string."""

import json

from sdlc.eval.promptfoo.absolute import get_assert, load_vetoes

_GOOD = {
    "summary": "Detect sleeping, eating, drinking, litter box, playing and "
    "fighting; risk analysis marks at-risk cats red; 24 hours of "
    "history.",
    "functional_requirements": ["detect all six activities"],
    "non_functional_requirements": ["5s telemetry cadence"],
    "out_of_scope": ["no real collar hardware"],
    "open_questions": [],
}


def _ctx(cases_root, agents_dir, case="cat-cafe-monitoring", role="clarify"):
    return {
        "vars": {
            "role": role,
            "case": case,
            "agents_dir": str(agents_dir),
            "cases_root": str(cases_root),
        }
    }


def test_load_vetoes_reads_the_registered_file(repo_cases_root):
    vetoes = load_vetoes("cat-cafe-monitoring", "clarify", repo_cases_root)
    assert {v.id for v in vetoes} == {"scope_preserved", "scope_discipline_declared"}


def test_load_vetoes_returns_empty_for_an_unregistered_case_role(repo_cases_root):
    """No vetoes registered is NOT an error -- vetoes are opt-in per case."""
    assert load_vetoes("add-login-greenfield", "clarify", repo_cases_root) == []


def test_complete_artifact_passes(repo_cases_root, repo_agents_dir):
    r = get_assert(json.dumps(_GOOD), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is True


def test_dropped_activity_fails_absolutely(repo_cases_root, repo_agents_dir):
    """The scope_dropped mutation's target: an artifact that validates as
    ClarifiedRequirements but silently lost three activities."""
    bad = dict(_GOOD)
    bad["summary"] = "Detect sleeping, eating and drinking. 24h history, risk, red."
    bad["functional_requirements"] = ["detect three activities"]
    r = get_assert(json.dumps(bad), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert r["score"] == 0.0
    assert "scope_preserved" in r["reason"]
    assert "fighting" in r["reason"]


def test_empty_out_of_scope_fails_absolutely(repo_cases_root, repo_agents_dir):
    bad = dict(_GOOD, out_of_scope=[])
    r = get_assert(json.dumps(bad), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert "scope_discipline_declared" in r["reason"]


def test_output_type_failure_still_wins_over_vetoes(repo_cases_root, repo_agents_dir):
    """An output that does not parse is broken whatever a veto says, and the
    reason must name the type failure -- not a confusing veto message about
    fields that were never populated."""
    r = get_assert("not json at all", _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert "does not validate" in r["reason"]
