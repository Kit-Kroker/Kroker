from sdlc.benchmarks.calibration import compute_agreement


def test_perfect_agreement():
    s = compute_agreement([(0.2, 0.2), (0.8, 0.8), (0.5, 0.5)])
    assert s.agreement_rate == 1.0
    assert s.mae == 0.0
    assert s.spearman == 1.0
    assert s.verdict == "calibrated"


def test_epsilon_boundary_counts_as_agree():
    # exactly epsilon apart -> within tolerance
    s = compute_agreement([(0.5, 0.65)], epsilon=0.15)
    assert s.agreement_rate == 1.0


def test_beyond_epsilon_is_disagree_and_uncalibrated():
    s = compute_agreement([(0.1, 0.9), (0.2, 0.8)], epsilon=0.15, threshold=0.75)
    assert s.agreement_rate == 0.0
    assert round(s.mae, 3) == 0.7
    assert s.verdict == "uncalibrated"


def test_anti_correlation_spearman_negative():
    s = compute_agreement([(0.1, 0.9), (0.5, 0.5), (0.9, 0.1)])
    assert round(s.spearman, 3) == -1.0


def test_tied_human_scores_do_not_crash_spearman():
    s = compute_agreement([(0.5, 0.4), (0.5, 0.6), (0.5, 0.5)])
    assert s.spearman == 0.0  # zero variance in human ranks -> defined as 0


def test_empty_pairs_safe():
    s = compute_agreement([])
    assert s.n == 0 and s.agreement_rate == 0.0 and s.verdict == "uncalibrated"


def test_single_pair_spearman_zero():
    s = compute_agreement([(0.5, 0.5)])
    assert s.spearman == 0.0  # n<2 undefined -> 0.0
    assert s.agreement_rate == 1.0
