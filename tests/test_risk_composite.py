# tests/test_risk_composite.py
"""RD3/RD9: partial is derived from the factors, never stored."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.risk.models import Composite, Driver, Factor
from sdlc.measurement import CollectionState, Measurement


def _f(key: str, value: float | None, weight: float = 1.0) -> Factor:
    m = (Measurement.measured(value) if value is not None
         else Measurement.not_collected(f"{key}: no source"))
    return Factor(key=key, value=m, weight=weight)


def test_all_factors_collected_is_not_partial():
    c = Composite(
        value=Measurement.measured(0.4),
        factors=(_f("a", 0.2), _f("b", 0.6)),
        drivers=(Driver(factor_key="b", value=0.6, contribution=0.3),))
    assert c.is_partial is False


def test_some_factors_collected_is_partial_and_carries_no_value():
    c = Composite(
        value=Measurement.not_collected("b: no source"),
        factors=(_f("a", 0.2), _f("b", None)),
        drivers=(Driver(factor_key="a", value=0.2, contribution=0.1),))
    assert c.is_partial is True
    assert c.value.state is CollectionState.NOT_COLLECTED
    assert c.collected_factors == (c.factors[0],)


def test_no_factor_collected_carries_no_drivers():
    c = Composite(
        value=Measurement.not_collected("nothing collected"),
        factors=(_f("a", None), _f("b", None)))
    assert c.is_partial is False
    assert c.drivers == ()


def test_drivers_without_a_collected_factor_are_refused():
    """_unmeasured_carries_no_payload, RD9's third case."""
    with pytest.raises(ValidationError, match="no collected factor"):
        Composite(
            value=Measurement.not_collected("nothing collected"),
            factors=(_f("a", None),),
            drivers=(Driver(factor_key="a", value=0.2, contribution=0.1),))


def test_a_measured_composite_needs_every_factor_collected():
    with pytest.raises(ValidationError, match="did not collect"):
        Composite(value=Measurement.measured(0.4),
                  factors=(_f("a", 0.2), _f("b", None)))


def test_a_driver_must_name_a_factor_that_exists():
    with pytest.raises(ValidationError, match="names no factor"):
        Composite(value=Measurement.measured(0.2), factors=(_f("a", 0.2),),
                  drivers=(Driver(factor_key="zzz", value=0.1,
                                  contribution=0.1),))


def test_at_most_three_drivers():
    """FR-916: maxItems 3, here 'the three largest contributors'."""
    factors = tuple(_f(k, 0.5) for k in "abcd")
    with pytest.raises(ValidationError, match="at most three"):
        Composite(
            value=Measurement.measured(0.5), factors=factors,
            drivers=tuple(Driver(factor_key=k, value=0.5, contribution=0.1)
                          for k in "abcd"))


def test_factors_are_asserted_sorted_not_repaired():
    with pytest.raises(ValidationError, match="sorted"):
        Composite(value=Measurement.measured(0.4),
                  factors=(_f("b", 0.6), _f("a", 0.2)))


def test_is_partial_is_not_settable():
    with pytest.raises(ValidationError):
        Composite(value=Measurement.measured(0.2), factors=(_f("a", 0.2),),
                  is_partial=True)
