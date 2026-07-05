from sdlc.models import GateConfig, GateOutcome, GatePolicy, PipelineConfig
from sdlc.workflows.feature import _auto_decision_for


def _cfg(policy: GatePolicy, threshold: float = 0.8) -> PipelineConfig:
    return PipelineConfig(gates={"architecture": GateConfig(policy=policy,
                                                            threshold=threshold)})


def test_soft_high_confidence_auto_approves():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.9)
    assert decision is not None
    assert decision.outcome is GateOutcome.APPROVE
    assert decision.decided_by == "policy"


def test_soft_confidence_at_threshold_auto_approves():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT, 0.8), 0.8)
    assert decision is not None


def test_soft_low_confidence_falls_through():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), 0.5)
    assert decision is None


def test_soft_none_confidence_falls_through():
    """Missing/legacy confidence must never auto-approve."""
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.SOFT), None)
    assert decision is None


def test_hard_policy_ignores_confidence():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.HARD), 0.99)
    assert decision is None


def test_off_policy_ignores_confidence():
    decision = _auto_decision_for("architecture", _cfg(GatePolicy.OFF), 0.0)
    assert decision is None


def test_unconfigured_gate_defaults_to_hard_and_falls_through():
    decision = _auto_decision_for("deploy", PipelineConfig(gates={}), 0.99)
    assert decision is None
