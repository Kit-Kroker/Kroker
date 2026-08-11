import argparse

from sdlc.cli import _needs_temporal_client


def _ns(**kw):
    return argparse.Namespace(**kw)


def test_calibrate_capture_does_not_need_client():
    assert _needs_temporal_client(_ns(cmd="calibrate", target="capture")) is False


def test_calibrate_rubric_does_not_need_client():
    assert _needs_temporal_client(_ns(cmd="calibrate", target="architect")) is False


def test_eval_never_needs_client_since_capture_retired():
    """E-82 retired `eval capture` -- it was the only eval target that needed
    a live Temporal history. Fixtures are constructed now, so every eval
    invocation is local-only."""
    assert _needs_temporal_client(_ns(cmd="eval", target="capture")) is False
    assert _needs_temporal_client(_ns(cmd="eval", target="clarify")) is False


def test_eval_rubric_does_not_need_client():
    assert _needs_temporal_client(_ns(cmd="eval", target="reviewer")) is False


def test_benchmark_never_needs_client():
    assert _needs_temporal_client(_ns(cmd="benchmark", bench_cmd="drift")) is False


def test_start_needs_client():
    assert _needs_temporal_client(_ns(cmd="start")) is True
