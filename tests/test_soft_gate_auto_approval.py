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


import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_revisable_stage_passes_auto_decision():
    src = SRC.read_text(encoding="utf-8")
    assert "_auto_decision_for(" in src, (
        "_revisable_stage must call _auto_decision_for to compute an "
        "auto_decision from the artifact's confidence (FR-301)")
    # The auto_decision must actually reach _gate(), not just be computed.
    assert "auto_decision=auto" in src, (
        "_revisable_stage must pass auto_decision=auto into self._gate()")


def test_merge_soft_path_uses_auto_decision_for():
    src = SRC.read_text(encoding="utf-8")
    # Find the merge stage's soft-path block (after the MergeVerdict call)
    # and confirm it consults _auto_decision_for rather than a bare
    # verdict.approve check alone.
    idx = src.find('"merge_verdict"')
    assert idx != -1, "merge stage no longer calls t_merge_verdict"
    tail = src[idx: idx + 700]
    assert "_auto_decision_for(" in tail, (
        "merge gate's soft path must route through _auto_decision_for so "
        "verdict.confidence is checked against cfg.gates['merge'].threshold, "
        "not just verdict.approve")
