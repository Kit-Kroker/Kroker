# tests/test_gates_models.py
"""FR-917 (E-50): RiskGateReport's structural rules, and RiskGateOverride
mirrors ReadinessOverride field-for-field (GD5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sdlc.assessment.gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict
from sdlc.gate import CheckClass, CheckResult


def _check(name: str, passed: bool = True) -> CheckResult:
    return CheckResult(name=name, passed=passed, classification=CheckClass.ABSOLUTE)


def test_a_pass_report_may_carry_no_checks_or_deferrals():
    r = RiskGateReport(verdict=RiskGateVerdict.PASS)
    assert r.checks == ()
    assert r.deferred == ()
    assert r.reasons == ()


def test_checks_must_be_sorted_by_name():
    with pytest.raises(ValidationError, match="sorted"):
        RiskGateReport(
            verdict=RiskGateVerdict.BLOCK,
            checks=(
                _check("risk_no_unaccepted_confirmed_vuln"),
                _check("risk_composite_below_threshold"),
            ),
        )


def test_duplicate_check_names_are_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        RiskGateReport(
            verdict=RiskGateVerdict.BLOCK,
            checks=(
                _check("risk_no_unaccepted_confirmed_vuln"),
                _check("risk_no_unaccepted_confirmed_vuln"),
            ),
        )


def test_deferred_must_be_sorted():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.PASS, deferred=("z", "a"))


def test_deferred_must_be_deduped():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.PASS, deferred=("a", "a"))


def test_reasons_must_be_sorted_and_deduped():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.BLOCK, reasons=("z", "a"))


def test_a_risk_gate_override_round_trips():
    o = RiskGateOverride(
        approved_by="human",
        reviewer="alice",
        reason="reviewed and accepted",
        decided_at=datetime.now(UTC),
        gate_round=1,
    )
    assert o.approved_by == "human"
    assert o.gate_round == 1


def test_a_risk_gate_override_rejects_an_unknown_approver_class():
    with pytest.raises(ValidationError):
        RiskGateOverride(
            approved_by="robot", reason="x", decided_at=datetime.now(UTC), gate_round=1
        )
