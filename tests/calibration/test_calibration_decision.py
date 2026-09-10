"""C7: the auto-approve rule, now AND-ed with calibration.

This is the rule audit row 8 named as UNPAIRED. The tests below are the old
truth table (which must not shift) plus the new conjunct.
"""

from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import INSUFFICIENT, CalibrationVerdict
from sdlc.core.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig

CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)
UNCALIBRATED = CalibrationVerdict(verdict="uncalibrated", n=25, agreement_rate=0.2)


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


def test_soft_high_confidence_and_calibrated_auto_approves():
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert d is not None
    assert d.outcome is GateOutcome.APPROVE
    assert d.decided_by == "policy"


def test_the_decision_records_the_calibration_evidence():
    """A synthesized approval must say what authorized it. 'decided_by=policy'
    with no numbers is exactly the unauditable short-circuit C7 exists to fix."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED)
    assert d is not None and d.comments is not None
    assert "calibrated" in d.comments
    assert "n=25" in d.comments


def test_high_confidence_but_uncalibrated_falls_through():
    """The headline change: confidence alone no longer skips the human."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, UNCALIBRATED) is None


def test_high_confidence_but_insufficient_data_falls_through():
    """Cold start. Every bucket begins here (ruling OQ3)."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, INSUFFICIENT) is None


def test_low_confidence_with_a_calibrated_bucket_still_falls_through():
    """Calibration is a second conjunct, not a replacement for the threshold."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5, CALIBRATED) is None


def test_confidence_at_threshold_and_calibrated_auto_approves():
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8, CALIBRATED) is not None
    )


def test_none_confidence_falls_through_even_when_calibrated():
    """Missing/legacy confidence must never auto-approve (role_host.py:64-65's
    guard, preserved verbatim)."""
    assert auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None, CALIBRATED) is None


def test_hard_policy_ignores_confidence_and_calibration():
    assert auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99, CALIBRATED) is None


def test_off_policy_ignores_confidence_and_calibration():
    assert auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0, CALIBRATED) is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    assert auto_decision_for("deploy", PipelineConfig(gates={}), 0.99, CALIBRATED) is None


def test_merge_gate_with_an_insufficient_verdict_never_auto_approves():
    """Ruling OQ2, and note there is no gate-name branch anywhere: merge falls
    through because its bucket is never labelled, not because it is named
    'merge'. SG-3 guards that distinction."""
    cfg = PipelineConfig(gates={"merge": GateConfig(policy=GatePolicy.SOFT, threshold=0.5)})
    assert auto_decision_for("merge", cfg, 1.0, INSUFFICIENT) is None
