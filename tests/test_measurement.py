"""FR-915: a measured value and a never-measured value must not be the same
object. The validator is the mechanism -- the illegal state is unconstructible,
not merely discouraged."""

import pytest
from pydantic import ValidationError

from sdlc.measurement import CollectionState, Measurement


def test_measured_carries_a_value():
    m = Measurement.measured(0.0)
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0


def test_measured_without_a_value_is_unconstructible():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.MEASURED)


def test_not_collected_with_a_value_is_unconstructible():
    """The whole point: a not-collected measurement cannot smuggle a zero."""
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.NOT_COLLECTED, value=0.0, reason="no artifact")


def test_unknown_with_a_value_is_unconstructible():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.UNKNOWN, value=0.0, reason="nan rate")


def test_non_measured_states_require_a_reason():
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.NOT_COLLECTED)
    with pytest.raises(ValidationError):
        Measurement(state=CollectionState.UNKNOWN, reason="   ")


def test_measured_zero_is_not_equal_to_not_collected():
    assert Measurement.measured(0.0) != Measurement.not_collected("no artifact")


def test_the_distinction_survives_a_json_round_trip():
    """These travel through Temporal history as JSON; the distinction has to
    survive serialization or it is decorative."""
    for m in (
        Measurement.measured(0.0),
        Measurement.not_collected("no artifact"),
        Measurement.unknown("non-finite rate"),
    ):
        assert Measurement.model_validate_json(m.model_dump_json()) == m


def test_constructors_set_the_state_they_name():
    assert Measurement.not_collected("r").state is CollectionState.NOT_COLLECTED
    assert Measurement.unknown("r").state is CollectionState.UNKNOWN


def test_measured_non_finite_is_unconstructible():
    """nan silently fails every comparison (nan >= threshold is False), so a
    measured nan fabricates a failure; inf does the mirror. The producer must
    not be the only line of defence -- E-41 reuses this type without knowing
    that measure_coverage guards non-finite upstream."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError):
            Measurement.measured(bad)


def test_measured_finite_value_constructs():
    assert Measurement.measured(0.0).value == 0.0
    assert Measurement.measured(80.0).value == 80.0
