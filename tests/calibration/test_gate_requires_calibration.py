"""C7: the gate paths consult the ledger before honouring a confidence.

This is audit row 8's fix at the two call sites. The tests are source-level
where they pin wiring and behavioural where they pin the decision, because
the decision itself is already covered by test_calibration_decision.py.
"""

import pathlib

ROLE_HOST = pathlib.Path("src/sdlc/workflows/role_host.py")
MERGE = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_the_rule_has_exactly_one_home():
    """Before C7 this rule existed twice, logically identical. Plumbing a new
    conjunct through two copies is how they drift apart again."""
    assert "def auto_decision_for(" not in ROLE_HOST.read_text(encoding="utf-8")
    assert "def _auto_decision_for(" not in ROLE_HOST.read_text(encoding="utf-8")
    assert "def _auto_decision_for(" not in MERGE.read_text(encoding="utf-8")


def test_both_call_sites_import_the_shared_rule():
    for path in (ROLE_HOST, MERGE):
        src = path.read_text(encoding="utf-8")
        assert "auto_decision_for" in src, path
        assert "calibration" in src, path


def test_revisable_stage_conditions_the_lookup_on_soft_with_confidence():
    """SG-4: HARD, OFF and None-confidence rounds must not pay for an
    activity call, and must not gain a dependency on the ledger being up."""
    src = ROLE_HOST.read_text(encoding="utf-8")
    idx = src.find("async def _revisable_stage")
    assert idx != -1
    body = src[idx:]
    assert "confidence is not None" in body
    assert "GatePolicy.SOFT" in body


def test_revisable_stage_still_passes_the_auto_decision_into_the_gate():
    src = ROLE_HOST.read_text(encoding="utf-8")
    assert "auto_decision=auto" in src


def test_no_gate_name_is_special_cased():
    """SG-3, ruling OQ2. Merge stops auto-approving because it is never
    labelled, not because the code knows its name."""
    for path in (ROLE_HOST, MERGE, pathlib.Path("src/sdlc/calibration/decision.py")):
        src = path.read_text(encoding="utf-8")
        assert '== "merge"' not in src, path


def test_a_lookup_failure_degrades_to_insufficient_not_an_exception():
    src = ROLE_HOST.read_text(encoding="utf-8")
    idx = src.find("_calibration_verdict")
    assert idx != -1
    assert "INSUFFICIENT" in src[idx : idx + 900]
    assert "except Exception" in src[idx : idx + 900]
