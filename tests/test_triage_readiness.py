"""D4: an unmeasured dimension is never READY. The truth table is the point."""
import pytest

from sdlc.measurement import Measurement
from sdlc.triage.models import (
    M_BUILDABLE, M_RUNNABLE, M_STRUCTURE, M_TESTS_PRESENT,
    SignalResult, Verdict, compute_readiness,
)


def _sig(name, **metrics):
    return SignalResult(signal=name, version=1,
                        collected=Measurement.measured(0.0), metrics=metrics)


def _all_good():
    return [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(1.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(4.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]


def test_all_measured_and_positive_is_ready():
    assert compute_readiness(_all_good()).verdict is Verdict.READY


def test_a_measured_zero_is_not_ready():
    sigs = [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(0.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(4.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]
    assert compute_readiness(sigs).verdict is Verdict.NOT_READY


def test_zero_tests_is_not_ready_not_indeterminate():
    sigs = [
        _sig("build_probe", **{M_BUILDABLE: Measurement.measured(1.0),
                               M_RUNNABLE: Measurement.measured(1.0)}),
        _sig("baseline", **{M_TESTS_PRESENT: Measurement.measured(0.0),
                            M_STRUCTURE: Measurement.measured(1.0)}),
    ]
    assert compute_readiness(sigs).verdict is Verdict.NOT_READY


@pytest.mark.parametrize("key", [M_BUILDABLE, M_RUNNABLE,
                                 M_TESTS_PRESENT, M_STRUCTURE])
def test_any_not_collected_dimension_forces_indeterminate(key):
    sigs = _all_good()
    for s in sigs:
        if key in s.metrics:
            s.metrics[key] = Measurement.not_collected("timed out")
    assert compute_readiness(sigs).verdict is Verdict.INDETERMINATE


@pytest.mark.parametrize("key", [M_BUILDABLE, M_RUNNABLE,
                                 M_TESTS_PRESENT, M_STRUCTURE])
def test_a_dimension_no_signal_reported_forces_indeterminate(key):
    sigs = _all_good()
    for s in sigs:
        s.metrics.pop(key, None)
    r = compute_readiness(sigs)
    assert r.verdict is Verdict.INDETERMINATE
    assert "no signal reported" in getattr(r, key).reason


def test_no_signals_at_all_is_indeterminate():
    assert compute_readiness([]).verdict is Verdict.INDETERMINATE


def test_unknown_dimension_forces_indeterminate():
    sigs = _all_good()
    sigs[0].metrics[M_BUILDABLE] = Measurement.unknown("garbled output")
    assert compute_readiness(sigs).verdict is Verdict.INDETERMINATE


def test_two_signals_reporting_the_same_key_is_an_error():
    sigs = _all_good()
    sigs[1].metrics[M_BUILDABLE] = Measurement.measured(1.0)
    with pytest.raises(ValueError) as exc:
        compute_readiness(sigs)
    assert "buildable" in str(exc.value)


def test_non_readiness_metric_keys_are_ignored():
    sigs = _all_good()
    sigs[0].metrics["install_seconds"] = Measurement.measured(12.0)
    assert compute_readiness(sigs).verdict is Verdict.READY
