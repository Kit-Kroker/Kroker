# tests/test_risk_composites.py
"""RD3/RD9: the weighted sum, and what a partial composite may still say."""
from __future__ import annotations

import random

from sdlc.assessment.risk.composites import compose, unified
from sdlc.assessment.risk.models import Factor
from sdlc.assessment.risk.rules import (
    F_COVERAGE_GAP, F_EXPOSURE, F_IMPACT, F_LIKELIHOOD, SECURITY_WEIGHTS,
)
from sdlc.measurement import CollectionState, Measurement


def _f(key, value, weight=1.0):
    m = (Measurement.measured(value) if value is not None
         else Measurement.not_collected(f"{key} has no source"))
    return Factor(key=key, value=m, weight=weight)


def _sec(likelihood, impact, exposure):
    return tuple(sorted(
        (_f(F_LIKELIHOOD, likelihood, SECURITY_WEIGHTS[F_LIKELIHOOD]),
         _f(F_IMPACT, impact, SECURITY_WEIGHTS[F_IMPACT]),
         _f(F_EXPOSURE, exposure, SECURITY_WEIGHTS[F_EXPOSURE])),
        key=lambda f: f.key))


def test_all_collected_is_the_weighted_sum():
    c = compose(_sec(1.0, 1.0, 1.0), label="security")
    assert c.value.state is CollectionState.MEASURED
    assert abs(c.value.value - 1.0) < 1e-9


def test_the_score_is_in_the_unit_interval():
    c = compose(_sec(0.3, 0.7, 0.1), label="security")
    assert 0.0 <= c.value.value <= 1.0


def test_one_missing_factor_makes_it_partial_and_valueless():
    c = compose(_sec(0.4, None, 0.2), label="security")
    assert c.is_partial is True
    assert c.value.state is CollectionState.NOT_COLLECTED
    assert F_IMPACT in c.value.reason


def test_a_partial_composite_still_carries_drivers():
    """RD9's middle case -- the factors underneath are real, and are exactly
    what a customer needs to see."""
    c = compose(_sec(0.4, None, 0.2), label="security")
    assert {d.factor_key for d in c.drivers} == {F_LIKELIHOOD, F_EXPOSURE}


def test_nothing_collected_carries_no_drivers():
    c = compose(_sec(None, None, None), label="security")
    assert c.drivers == ()
    assert c.is_partial is False


def test_drivers_are_the_three_largest_contributors():
    factors = tuple(sorted(
        (_f("a", 0.1, 0.1), _f("b", 0.9, 0.4), _f("c", 0.5, 0.3),
         _f("d", 0.8, 0.2)),
        key=lambda f: f.key))
    c = compose(factors, label="x")
    assert [d.factor_key for d in c.drivers] == ["b", "d", "c"]


def test_drivers_are_ordered_by_contribution_then_key():
    factors = tuple(sorted((_f("a", 0.5, 0.5), _f("b", 0.5, 0.5)),
                           key=lambda f: f.key))
    c = compose(factors, label="x")
    assert [d.factor_key for d in c.drivers] == ["a", "b"]


def test_unified_propagates_partial_from_the_qa_half():
    """RD3's headline consequence."""
    sec = compose(_sec(0.5, 0.5, 0.5), label="security")
    qa = compose(tuple(sorted((_f(F_COVERAGE_GAP, 0.3), _f("z", None)),
                              key=lambda f: f.key)), label="qa")
    u = unified(sec, qa)
    assert u.value.state is CollectionState.NOT_COLLECTED
    assert u.is_partial is True
    assert "qa" in u.value.reason


def test_unified_is_measured_when_both_halves_are():
    sec = compose(_sec(0.5, 0.5, 0.5), label="security")
    qa = compose((_f(F_COVERAGE_GAP, 0.3),), label="qa")
    u = unified(sec, qa)
    assert u.value.state is CollectionState.MEASURED


def test_compose_is_order_independent():
    """NFR-10. The input tuple is asserted sorted, so this shuffles the
    construction order and compares the serialized output."""
    values = [(F_LIKELIHOOD, 0.2), (F_IMPACT, 0.6), (F_EXPOSURE, 0.4)]
    first = None
    for _ in range(5):
        random.shuffle(values)
        factors = tuple(sorted(
            (_f(k, v, SECURITY_WEIGHTS[k]) for k, v in values),
            key=lambda f: f.key))
        out = compose(factors, label="security").model_dump_json()
        first = first if first is not None else out
        assert out == first
