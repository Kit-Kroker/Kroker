from __future__ import annotations

import json
from pathlib import Path

from sdlc.eval.promptfoo.absolute import (output_type_for,
                                          validates_as_output_type)

AGENTS = Path(__file__).resolve().parents[1] / "agents"

# Every required field of ClarifiedRequirements. open_questions=[] is a
# legitimate outcome (the clarifier had nothing to ask), so an empty LIST is
# never a failure -- see test_empty_required_list_is_allowed below.
GOOD = json.dumps({
    "summary": "Add a login page with email and password.",
    "functional_requirements": ["User can submit email + password"],
    "non_functional_requirements": ["Passwords are hashed at rest"],
    "out_of_scope": ["OAuth providers"],
    "open_questions": [],
})


def test_output_type_for_clarify():
    from sdlc.models import ClarifiedRequirements
    assert output_type_for("clarify", AGENTS) is ClarifiedRequirements


def test_valid_artifact_passes():
    res = validates_as_output_type(GOOD, "clarify", AGENTS)
    assert res["pass"] is True, res["reason"]


def test_non_json_fails_with_the_type_name():
    res = validates_as_output_type("not json", "clarify", AGENTS)
    assert res["pass"] is False
    assert "ClarifiedRequirements" in res["reason"]


def test_empty_output_fails():
    # A provider error surfaces as "" -- it must NOT read as a valid artifact.
    res = validates_as_output_type("", "clarify", AGENTS)
    assert res["pass"] is False


def test_wrong_shape_fails():
    res = validates_as_output_type('{"unexpected": 1}', "clarify", AGENTS)
    assert res["pass"] is False


def test_blank_required_string_fails():
    """Spec 4.5 "required fields non-empty": a schema-valid artifact whose
    summary is whitespace is still a broken proposer."""
    bad = json.loads(GOOD)
    bad["summary"] = "   "
    res = validates_as_output_type(json.dumps(bad), "clarify", AGENTS)
    assert res["pass"] is False
    assert "summary" in res["reason"]


def test_empty_required_list_is_allowed():
    """Deliberate non-check: open_questions=[] means "nothing to ask", not a
    failure. Only required STRING fields are checked for emptiness, so the
    gate never invents a regression."""
    res = validates_as_output_type(GOOD, "clarify", AGENTS)
    assert res["pass"] is True
