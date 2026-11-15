"""C7: the auto-approve rule, now AND-ed with calibration.

This is the rule audit row 8 named as UNPAIRED. The tests below are the old
truth table (which must not shift) plus the new conjunct.

FR-301/ADR-24 add the fourth conjunct: the deterministic verdict. The old
calls pass `VACUOUS` so every pre-existing assertion keeps meaning what it
meant; the new tests are the conjunct's own truth table.
"""

import inspect
from inspect import Parameter

from sdlc.calibration.decision import auto_decision_for
from sdlc.calibration.models import INSUFFICIENT, CalibrationVerdict
from sdlc.core.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig
from sdlc.validators import Verdict

CALIBRATED = CalibrationVerdict(verdict="calibrated", n=25, agreement_rate=0.9)
UNCALIBRATED = CalibrationVerdict(verdict="uncalibrated", n=25, agreement_rate=0.2)

# The deterministic conjunct's three shapes (D1). VACUOUS is what a gate
# with no provider resolves to -- architecture today, until AP-4.4.
VACUOUS = Verdict.vacuous()
RAN_CLEAN = Verdict(checks_run=True, ok=True)
RAN_FAILED = Verdict(checks_run=True, ok=False)


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy, threshold=threshold)})


def test_soft_high_confidence_and_calibrated_auto_approves():
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, VACUOUS)
    assert d is not None
    assert d.outcome is GateOutcome.APPROVE
    assert d.decided_by == "policy"


def test_the_decision_records_the_calibration_evidence():
    """A synthesized approval must say what authorized it. 'decided_by=policy'
    with no numbers is exactly the unauditable short-circuit C7 exists to fix."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, VACUOUS)
    assert d is not None and d.comments is not None
    assert "calibrated" in d.comments
    assert "n=25" in d.comments


def test_high_confidence_but_uncalibrated_falls_through():
    """The headline change: confidence alone no longer skips the human."""
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, UNCALIBRATED, VACUOUS)
        is None
    )


def test_high_confidence_but_insufficient_data_falls_through():
    """Cold start. Every bucket begins here (ruling OQ3)."""
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, INSUFFICIENT, VACUOUS)
        is None
    )


def test_low_confidence_with_a_calibrated_bucket_still_falls_through():
    """Calibration is a second conjunct, not a replacement for the threshold."""
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5, CALIBRATED, VACUOUS) is None
    )


def test_confidence_at_threshold_and_calibrated_auto_approves():
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8, CALIBRATED, VACUOUS)
        is not None
    )


def test_none_confidence_falls_through_even_when_calibrated():
    """Missing/legacy confidence must never auto-approve (role_host.py:64-65's
    guard, preserved verbatim)."""
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None, CALIBRATED, VACUOUS) is None
    )


def test_hard_policy_ignores_confidence_and_calibration():
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99, CALIBRATED, VACUOUS) is None
    )


def test_off_policy_ignores_confidence_and_calibration():
    assert auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0, CALIBRATED, VACUOUS) is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    assert auto_decision_for("deploy", PipelineConfig(gates={}), 0.99, CALIBRATED, VACUOUS) is None


def test_merge_gate_with_an_insufficient_verdict_never_auto_approves():
    """Ruling OQ2, and note there is no gate-name branch anywhere: merge falls
    through because its bucket is never labelled, not because it is named
    'merge'. SG-3 guards that distinction."""
    cfg = PipelineConfig(gates={"merge": GateConfig(policy=GatePolicy.SOFT, threshold=0.5)})
    assert auto_decision_for("merge", cfg, 1.0, INSUFFICIENT, VACUOUS) is None


# ---------------------------------------------------------------------------
# The deterministic conjunct (FR-301, ADR-24)
# ---------------------------------------------------------------------------


def test_verdict_parameter_is_required_and_has_no_default():
    """The no-default discipline extends to the deterministic conjunct: a
    default would let a caller skip the evidence -- the same defect the
    calibration parameter's rule names, one layer down."""
    params = inspect.signature(auto_decision_for).parameters
    assert list(params) == ["name", "cfg", "confidence", "calibration", "verdict"]
    assert params["verdict"].default is Parameter.empty
    assert params["calibration"].default is Parameter.empty


def test_failed_deterministic_verdict_blocks_auto_approve():
    """The fourth conjunct: a provider that ran and failed never yields an
    auto-approve, however confident and however calibrated the bucket."""
    assert (
        auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.99, CALIBRATED, RAN_FAILED)
        is None
    )


def test_a_blocked_conjunct_returns_none_so_the_human_wait_happens():
    """None is the whole contract: no synthesized decision exists -- no
    comments, no outcome -- so _gate() falls through to the human wait."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, RAN_FAILED)
    assert d is None


def test_vacuous_verdict_passes_the_conjunct():
    """D1: a gate with no deterministic provider (architecture today, until
    AP-4.4) passes vacuously -- the gate stays confidence+calibration-only."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, VACUOUS)
    assert d is not None and d.outcome is GateOutcome.APPROVE


def test_architecture_shaped_auto_approve_comment_is_byte_identical():
    """Characterization: the conjunct blocks or passes; a passing conjunct
    leaves no trace. The architecture-shaped call's comments are exactly what
    they were before the conjunct existed."""
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, VACUOUS)
    assert d is not None
    assert d.comments == (
        "auto-approved: confidence=0.90 >= threshold=0.80; "
        "calibration=calibrated (n=25, agreement=0.90)"
    )


def test_ran_and_passed_verdict_auto_approves():
    d = auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9, CALIBRATED, RAN_CLEAN)
    assert d is not None and d.outcome is GateOutcome.APPROVE
