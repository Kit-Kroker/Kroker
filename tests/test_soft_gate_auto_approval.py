from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import CalibrationVerdict
from sdlc.core.models import (
    GateConfig,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
)


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


# C7: the rule now takes a calibration verdict, with no default. These tests
# predate C7 and assert the confidence-vs-threshold half of the rule, so they
# supply a calibrated bucket and keep asserting exactly what they always did.
# The new conjunct has its own truth table in
# tests/calibration/test_calibration_decision.py.
CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)


def test_soft_high_confidence_auto_approves():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert decision is not None
    assert decision.outcome is GateOutcome.APPROVE
    assert decision.decided_by == "policy"


def test_soft_confidence_at_threshold_auto_approves():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8, CALIBRATED)
    assert decision is not None


def test_soft_low_confidence_falls_through():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5, CALIBRATED)
    assert decision is None


def test_soft_none_confidence_falls_through():
    """Missing/legacy confidence must never auto-approve."""
    decision = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None, CALIBRATED)
    assert decision is None


def test_hard_policy_ignores_confidence():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99, CALIBRATED)
    assert decision is None


def test_off_policy_ignores_confidence():
    decision = auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0, CALIBRATED)
    assert decision is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    decision = auto_decision_for("deploy", PipelineConfig(gates={}), 0.99, CALIBRATED)
    assert decision is None


import pathlib

# _revisable_stage lives on RoleHost (spec A Task 7); the merge soft path
# lives in src/sdlc/stages/merge/step.py (Task 20.7).
SRC = pathlib.Path("src/sdlc/workflows/role_host.py")
MERGE_SRC = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_revisable_stage_passes_auto_decision():
    """C7 moved the rule to sdlc/calibration/decision.py and dropped the
    leading underscore (it is a shared module API now, not a file-private
    helper). What this pins is unchanged: _revisable_stage must COMPUTE the
    auto-decision and PASS it to _gate, not just call the rule."""
    src = SRC.read_text(encoding="utf-8")
    assert "auto_decision_for(" in src, (
        "_revisable_stage must call auto_decision_for to compute an "
        "auto_decision from the artifact's confidence (FR-301)"
    )
    assert "auto_decision=auto" in src, (
        "_revisable_stage must pass auto_decision=auto into self._gate()"
    )


def test_merge_soft_path_uses_auto_decision_for():
    """C7: same needle without the underscore, and a wider window -- the soft
    path now fetches a calibration verdict between the MergeVerdict call and
    the decision, so the two are further apart than 700 characters."""
    src = MERGE_SRC.read_text(encoding="utf-8")
    idx = src.rfind('"merge_verdict"')
    assert idx != -1, "merge stage no longer calls merge_verdict"
    tail = src[idx : idx + 1400]
    assert "auto_decision_for(" in tail, (
        "merge gate's soft path must route through auto_decision_for so "
        "verdict.confidence is checked against cfg.gates['merge'].threshold "
        "and against the bucket's calibration, not just verdict.approve"
    )
