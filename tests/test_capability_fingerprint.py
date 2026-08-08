"""FR-913 similarity scoring (E-47a)."""
import pytest

from sdlc.capability.fingerprint import jaccard, score
from sdlc.capability.models import (
    CapabilityFingerprint, DEFAULT_TIER_WEIGHTS, SignalTier,
)
from sdlc.measurement import Measurement


def _fp(collected=True, **tiers) -> CapabilityFingerprint:
    m = (Measurement.measured(1.0) if collected
         else Measurement.not_collected("parse failure"))
    return CapabilityFingerprint(
        tiers={SignalTier(k): v for k, v in tiers.items()}, collected=m)


def test_jaccard_identical_sets_is_one():
    assert jaccard(["a", "b"], ["b", "a"]) == 1.0


def test_jaccard_disjoint_sets_is_zero():
    assert jaccard(["a"], ["b"]) == 0.0


def test_jaccard_partial_overlap():
    assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)


def test_jaccard_two_empty_sets_is_zero_not_a_division_error():
    assert jaccard([], []) == 0.0


def test_identical_fingerprints_score_one():
    fp = _fp(contract=["POST /login"], structural=["Auth"])
    total, contrib = score(fp, fp, DEFAULT_TIER_WEIGHTS)
    assert total == pytest.approx(1.0)
    assert contrib[SignalTier.CONTRACT] == pytest.approx(1.0)


def test_absent_tier_is_renormalized_away_not_scored_zero():
    # Both sides have ONLY structural members. If the absent contract tier
    # counted as zero the score would be 0.15; renormalized it is 1.0.
    a = _fp(structural=["Auth", "Token"])
    b = _fp(structural=["Auth", "Token"])
    total, contrib = score(a, b, DEFAULT_TIER_WEIGHTS)
    assert total == pytest.approx(1.0)
    assert SignalTier.CONTRACT not in contrib


def test_locational_only_overlap_is_not_comparable():
    # Evidence floor (review #3): Locational is the cheapest signal to change
    # in a repo, so a pair sharing nothing but a file path must not score.
    # Renormalization would otherwise give that lone tier full weight (1.0)
    # and hand a stored id to an unrelated co-located capability. This is the
    # mirror of test_absent_tier_is_renormalized_away_not_scored_zero: there,
    # renorm helps (a strong tier is absent); here, the same rule hurts.
    a = _fp(contract=["POST /a"], locational=["src/core/x.py"])
    b = _fp(locational=["src/core/x.py"])      # shares only the path
    assert score(a, b, DEFAULT_TIER_WEIGHTS) is None


def test_locational_shared_alongside_a_stronger_tier_is_comparable():
    # The floor blocks only Locational-sole overlap, not any pair that also
    # shares a non-Locational tier.
    a = _fp(structural=["Auth"], locational=["src/x.py"])
    b = _fp(structural=["Auth"], locational=["src/x.py"])
    assert score(a, b, DEFAULT_TIER_WEIGHTS) is not None


def test_contract_tier_dominates_a_full_structural_rename():
    # Every symbol and path renamed; routes and tables untouched.
    a = _fp(contract=["POST /login"], structural=["OldAuth"],
            locational=["old/auth.py"])
    b = _fp(contract=["POST /login"], structural=["NewIdentity"],
            locational=["new/identity.py"])
    total, _ = score(a, b, DEFAULT_TIER_WEIGHTS)
    assert total > 0.55


def test_changing_the_contract_costs_more_than_changing_symbols():
    base = _fp(contract=["POST /login"], structural=["Auth"])
    renamed_symbol = _fp(contract=["POST /login"], structural=["Identity"])
    changed_route = _fp(contract=["POST /signin"], structural=["Auth"])
    symbol_score, _ = score(base, renamed_symbol, DEFAULT_TIER_WEIGHTS)
    route_score, _ = score(base, changed_route, DEFAULT_TIER_WEIGHTS)
    assert symbol_score > route_score


def test_uncollected_fingerprint_is_not_comparable():
    assert score(_fp(collected=False, contract=["a"]),
                 _fp(contract=["a"]), DEFAULT_TIER_WEIGHTS) is None
    assert score(_fp(contract=["a"]),
                 _fp(collected=False, contract=["a"]),
                 DEFAULT_TIER_WEIGHTS) is None


def test_no_mutually_present_tier_is_not_comparable_not_zero():
    a = _fp(contract=["POST /a"])
    b = _fp(structural=["Thing"])
    assert score(a, b, DEFAULT_TIER_WEIGHTS) is None


def test_score_is_symmetric():
    a = _fp(contract=["POST /a", "POST /b"], structural=["X"])
    b = _fp(contract=["POST /b"], structural=["X", "Y"])
    assert score(a, b, DEFAULT_TIER_WEIGHTS)[0] == pytest.approx(
        score(b, a, DEFAULT_TIER_WEIGHTS)[0])
