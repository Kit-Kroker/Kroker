# tests/test_risk_memo.py
"""The assess memo. Never serve a failure forever (scan/memo.py's rule)."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.risk import memo
from sdlc.assessment.risk.build import map_digest, no_risk
from sdlc.assessment.risk.models import SystemRisk, UnifiedRiskMap
from sdlc.measurement import CollectionState, Measurement
from sdlc.memoization import cache
from sdlc.memoization.cache import NO_PROPOSER, risk_key


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


KW = dict(
    project="p",
    tree_hash="t",
    map_digest="d",
    rules_sha="r",
    prompt_sha=NO_PROPOSER,
    model=NO_PROPOSER,
)


def _measured() -> UnifiedRiskMap:
    return UnifiedRiskMap(system=SystemRisk(), collected=Measurement.measured(1.0))


def test_a_miss_returns_none():
    assert memo.load(**KW) is None


def test_a_measured_map_round_trips():
    assert memo.store(**KW, out=_measured()) is True
    assert memo.load(**KW) is not None


def test_an_uncollected_map_is_never_stored():
    """Rule 1: only a MEASURED map is stored, or a transient failure freezes
    into the cache."""
    assert memo.store(**KW, out=no_risk("discover did not collect")) is False
    assert memo.load(**KW) is None


def test_corrupt_content_is_a_miss_not_a_crash():
    cache.put(cache.risk_key("p", "t", "d", "r", NO_PROPOSER, NO_PROPOSER), "{not json")
    assert memo.load(**KW) is None


def test_the_key_moves_with_every_term():
    base = cache.risk_key("p", "t", "d", "r", NO_PROPOSER, NO_PROPOSER)
    assert cache.risk_key("p2", "t", "d", "r", NO_PROPOSER, NO_PROPOSER) != base
    assert cache.risk_key("p", "t2", "d", "r", NO_PROPOSER, NO_PROPOSER) != base
    assert cache.risk_key("p", "t", "d2", "r", NO_PROPOSER, NO_PROPOSER) != base
    assert cache.risk_key("p", "t", "d", "r2", NO_PROPOSER, NO_PROPOSER) != base
    assert cache.risk_key("p", "t", "d", "r", "prompt2", NO_PROPOSER) != base
    assert cache.risk_key("p", "t", "d", "r", NO_PROPOSER, "model2") != base


def test_map_digest_is_stable_and_content_addressed():
    a = CapabilityMap(collected=Measurement.measured(1.0))
    b = CapabilityMap(collected=Measurement.measured(1.0))
    assert map_digest(a) == map_digest(b)
    c = CapabilityMap(collected=Measurement.not_collected("x"))
    assert map_digest(c) != map_digest(a)


def test_the_proposer_terms_are_part_of_the_key():
    """A baseline-only map and a judged map must never share a key."""
    baseline = risk_key("p", "t", "d", "s", NO_PROPOSER, NO_PROPOSER)
    judged = risk_key("p", "t", "d", "s", "abc", "anthropic:x")
    assert baseline != judged


def test_a_degraded_judgment_is_not_stored_under_a_proposer_key(tmp_path, monkeypatch):
    """P2-D3: a transient model failure must cost one recompute, never a
    permanently judgment-free map served from cache."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))
    from sdlc.assessment.risk import memo
    from sdlc.assessment.risk.models import UnifiedRiskMap
    from sdlc.measurement import Measurement

    m = UnifiedRiskMap(
        collected=Measurement.measured(1.0), judgment=Measurement.not_collected("proposer failed")
    )
    assert (
        memo.store(
            project="p",
            tree_hash="t",
            map_digest="d",
            rules_sha="s",
            prompt_sha="abc",
            model="m",
            out=m,
        )
        is False
    )


def test_a_degraded_judgment_IS_stored_under_the_no_proposer_key(tmp_path, monkeypatch):
    """With no proposer configured the degradation is permanent, not
    transient, so caching it is correct."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))
    from sdlc.assessment.risk import memo
    from sdlc.assessment.risk.models import UnifiedRiskMap
    from sdlc.measurement import Measurement

    m = UnifiedRiskMap(
        collected=Measurement.measured(1.0), judgment=Measurement.not_collected("no proposer")
    )
    assert (
        memo.store(
            project="p",
            tree_hash="t",
            map_digest="d",
            rules_sha="s",
            prompt_sha=NO_PROPOSER,
            model=NO_PROPOSER,
            out=m,
        )
        is True
    )


def test_all_refused_proposal_degrades_and_is_refused_by_memo_store(tmp_path, monkeypatch):
    """Finding 1: a proposal whose rows were all refused degrades judgment,
    and P2-D3 refuses to store it under the proposer key."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))
    from sdlc.assessment.risk.apply import apply_judgment
    from sdlc.assessment.risk.models import (
        ProposedThreat,
        RiskProposal,
        StrideCategory,
    )

    b = UnifiedRiskMap(collected=Measurement.measured(1.0))
    # No rows survive
    out = apply_judgment(
        b,
        RiskProposal(
            threats=[
                ProposedThreat(
                    bc_id="BC-999", category=StrideCategory.SPOOFING, applicable=True, rationale="r"
                )
            ]
        ),
    )
    assert out.judgment.state is CollectionState.NOT_COLLECTED
    assert (
        memo.store(
            project="p",
            tree_hash="t",
            map_digest="d",
            rules_sha="s",
            prompt_sha="abc",
            model="m",
            out=out,
        )
        is False
    )
