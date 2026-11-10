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


# ---------------------------------------------------------------------------
# 020 T006 (plan T013, R-7, C2): pin the LIVE gate path. _revisable_stage is
# the topology's old home and dies with the step() composites this round, so
# these tests read the graph node that replaces it.
# ---------------------------------------------------------------------------

GATE_NODE = pathlib.Path("src/sdlc/workflows/graph_nodes/gate.py")


def _gate_node_body() -> str:
    src = GATE_NODE.read_text(encoding="utf-8")
    idx = src.find("async def gate_node(")
    assert idx != -1, "gate.py no longer defines gate_node"
    return src[idx:]


def test_gate_node_takes_the_author_from_the_stored_payload():
    """C2/C7: the author is the producer's resolved model, carried on the
    stored payload. Reading it from the gate name would be the stage-key trap
    (resolve_role_model is keyed by role, not by gate)."""
    assert "author = stored.author_model or" in _gate_node_body()


def test_gate_node_plumbs_author_model_into_both_gate_calls():
    """The in-loop call (revise available) and the final-round call (revise
    unavailable) both hand the author to ctx.gate, so the decision row records
    who authored the artifact on either path."""
    body = _gate_node_body()
    calls = body.split("nc.ctx.gate(")[1:]
    assert len(calls) == 2, "expected one in-loop and one final ctx.gate call"
    for call in calls:
        args = call[: call.index("\n        )")]
        assert "author_model=author" in args


def test_only_the_in_loop_gate_call_carries_auto_decision_and_confidence():
    """The in-loop call (revise available) hands the calibration-conditioned
    auto decision and the confidence to ctx.gate; the final-round call reads
    nothing and passes neither (the docstring's 'final round reads nothing')."""
    body = _gate_node_body()
    in_loop, final = (call[: call.index("\n        )")] for call in body.split("nc.ctx.gate(")[1:])
    assert "auto_decision=auto" in in_loop
    assert "confidence=confidence" in in_loop
    assert "auto_decision=" not in final
    assert "confidence=" not in final


def test_gate_node_consults_calibration_through_the_host_then_the_shared_rule():
    """Pins the consult path: the host lookup (which owns the C7 INSUFFICIENT
    fallback) feeds the one shared rule.

    Note on the brief: it named a `judge_error` argument. No symbol called
    judge_error exists anywhere in src/, so nothing here asserts on it. The
    judge-failure degradation is the lookup's `except Exception -> INSUFFICIENT`,
    pinned in test_calibration_lookup_failure_is_insufficient_on_the_live_path
    below.
    """
    body = _gate_node_body()
    consult = "await nc.host._calibration_verdict(cfg, name, author)"
    rule = "auto_decision_for(name, cfg, confidence, calibration)"
    assert consult in body
    assert rule in body
    assert body.index(consult) < body.index(rule)


def test_calibration_lookup_failure_is_insufficient_on_the_live_path():
    """The live path's consult degrades to INSUFFICIENT on any lookup failure,
    never an exception, so a ledger outage cannot fail the run."""
    src = pathlib.Path("src/sdlc/workflows/role_host.py").read_text(encoding="utf-8")
    idx = src.find("async def _calibration_verdict(")
    assert idx != -1
    window = src[idx : idx + 900]
    assert "except Exception" in window
    assert "return INSUFFICIENT" in window
