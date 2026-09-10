"""C7: the calibration statistic and its cold-start floor.

Below MIN_SAMPLES a bucket is insufficient_data -- never "calibrated by
default" and never "uncalibrated" either, because those are claims the data
cannot support (ruling OQ3). The bucket key folds the source in so benchmark
and production-proxy populations cannot be pooled by forgetting a filter
(ruling OQ6).
"""

from sdlc.calibration.models import CalibrationVerdict, LabelSource
from sdlc.calibration.verdict import (
    EPSILON,
    MIN_SAMPLES,
    THRESHOLD,
    WINDOW,
    bucket_key,
    verdict_for,
)


def test_constants_are_the_ruled_values():
    """Ruling OQ3 (floor) and OQ9(3) (inherited agreement constants). These are
    a starting position, to be re-derived from real samples -- pinned here so a
    change is a deliberate edit with a reviewer, not a drift."""
    assert MIN_SAMPLES == 20
    assert WINDOW == 200
    assert THRESHOLD == 0.75
    assert EPSILON == 0.15


def test_empty_ledger_is_insufficient_data():
    v = verdict_for([])
    assert v.verdict == "insufficient_data"
    assert v.n == 0


def test_below_the_floor_is_insufficient_data_even_when_perfectly_agreeing():
    """19 perfect samples are still 19. The floor is about evidence volume,
    not about agreement -- a bucket cannot buy its way past it with quality."""
    pairs = [(0.9, 0.9)] * (MIN_SAMPLES - 1)
    v = verdict_for(pairs)
    assert v.verdict == "insufficient_data"
    assert v.n == MIN_SAMPLES - 1


def test_at_the_floor_with_agreement_is_calibrated():
    pairs = [(0.9, 0.9)] * MIN_SAMPLES
    v = verdict_for(pairs)
    assert v.verdict == "calibrated"
    assert v.n == MIN_SAMPLES
    assert v.agreement_rate == 1.0


def test_confidently_wrong_is_uncalibrated():
    """The headline case: a proposer that always says 0.95 and always ships a
    0.10-quality outcome. Every sample is outside epsilon, so agreement is 0."""
    pairs = [(0.95, 0.10)] * MIN_SAMPLES
    v = verdict_for(pairs)
    assert v.verdict == "uncalibrated"
    assert v.agreement_rate == 0.0


def test_agreement_just_under_threshold_is_uncalibrated():
    """14 of 20 agree = 0.70 < THRESHOLD."""
    pairs = [(0.9, 0.9)] * 14 + [(0.9, 0.1)] * 6
    v = verdict_for(pairs)
    assert v.verdict == "uncalibrated"
    assert abs(v.agreement_rate - 0.70) < 1e-9


def test_agreement_at_threshold_is_calibrated():
    """15 of 20 agree = 0.75 == THRESHOLD, and compute_agreement's rule is
    `>=` (benchmarks/calibration.py:146-148)."""
    pairs = [(0.9, 0.9)] * 15 + [(0.9, 0.1)] * 5
    v = verdict_for(pairs)
    assert v.verdict == "calibrated"


def test_bucket_key_folds_the_source_in():
    a = bucket_key("anthropic/claude-x", LabelSource.BENCHMARK)
    b = bucket_key("anthropic/claude-x", LabelSource.PRODUCTION_PROXY)
    assert a != b, "ruling OQ6: the two populations must not share a bucket"
    assert "anthropic/claude-x" in a and "benchmark" in a


def test_bucket_key_for_an_unknown_model_is_still_a_distinct_bucket():
    """Pre-C7 records carry author_model=None. They get their own bucket, which
    simply never reaches the floor -- never a crash, never pooled into a real
    model's evidence."""
    k = bucket_key(None, LabelSource.PRODUCTION_PROXY)
    assert isinstance(k, str) and k
    assert k != bucket_key("some/model", LabelSource.PRODUCTION_PROXY)


def test_verdict_model_defaults_are_the_fail_safe():
    assert CalibrationVerdict(verdict="insufficient_data").n == 0
