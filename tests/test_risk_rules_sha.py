# tests/test_risk_rules_sha.py
"""RD-memo: the weights are an input, so they belong in the memo key.

E-46 learned this at plan-3 cost -- a hand-maintained version int misses a
real input, which is why its key carries rules_sha over the module bytes.
"""
from __future__ import annotations

from sdlc.assessment.risk import rules
from sdlc.assessment.risk.models import (
    ControlFamily, Criticality, Severity,
)


def test_rules_sha_is_stable_across_calls():
    assert rules.rules_sha() == rules.rules_sha()


def test_rules_sha_covers_every_module_that_can_move_output():
    """A module carrying a table or a cap must be declared, or editing it
    would move output without moving the key."""
    assert set(rules.RULE_MODULES) == {
        "sdlc.assessment.risk.rules",
        "sdlc.assessment.risk.severity",
        "sdlc.assessment.risk.controls",
        "sdlc.assessment.risk.factors",
        "sdlc.assessment.risk.composites",
        "sdlc.assessment.risk.build",
    }


def test_severity_table_covers_every_hint_and_criticality_pair():
    hints = ("info", "low", "medium", "high", "critical")
    for hint in hints:
        for crit in Criticality:
            assert isinstance(rules.SEVERITY_TABLE[(hint, crit)], Severity)


def test_a_high_hint_on_a_high_criticality_capability_is_critical():
    assert (rules.SEVERITY_TABLE[("high", Criticality.HIGH)]
            is Severity.CRITICAL)


def test_a_high_hint_on_a_low_criticality_capability_is_not_critical():
    assert (rules.SEVERITY_TABLE[("high", Criticality.LOW)]
            is not Severity.CRITICAL)


def test_control_sources_declare_all_five_families():
    """RD5: two families have no source, and that must be stated in the table
    rather than left absent."""
    assert set(rules.CONTROL_SOURCES) == set(ControlFamily)
    assert rules.CONTROL_SOURCES[ControlFamily.AUTHORIZATION] == ()
    assert rules.CONTROL_SOURCES[ControlFamily.MONITORING] == ()


def test_weights_sum_to_one_per_composite():
    for table in (rules.SECURITY_WEIGHTS, rules.QA_WEIGHTS,
                  rules.UNIFIED_WEIGHTS):
        assert abs(sum(table.values()) - 1.0) < 1e-9
