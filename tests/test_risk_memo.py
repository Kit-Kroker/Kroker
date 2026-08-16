# tests/test_risk_memo.py
"""The assess memo. Never serve a failure forever (scan/memo.py's rule)."""
from __future__ import annotations

import pytest

from sdlc.assessment.risk import memo
from sdlc.assessment.risk.build import map_digest, no_risk
from sdlc.assessment.risk.models import SystemRisk, UnifiedRiskMap
from sdlc.assessment.discover.map import CapabilityMap
from sdlc.measurement import Measurement
from sdlc.memoization import cache


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


KW = dict(project="p", tree_hash="t", map_digest="d", rules_sha="r")


def _measured() -> UnifiedRiskMap:
    return UnifiedRiskMap(system=SystemRisk(),
                          collected=Measurement.measured(1.0))


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
    cache.put(cache.risk_key("p", "t", "d", "r"), "{not json")
    assert memo.load(**KW) is None


def test_the_key_moves_with_every_term():
    base = cache.risk_key("p", "t", "d", "r")
    assert cache.risk_key("p2", "t", "d", "r") != base
    assert cache.risk_key("p", "t2", "d", "r") != base
    assert cache.risk_key("p", "t", "d2", "r") != base
    assert cache.risk_key("p", "t", "d", "r2") != base


def test_map_digest_is_stable_and_content_addressed():
    a = CapabilityMap(collected=Measurement.measured(1.0))
    b = CapabilityMap(collected=Measurement.measured(1.0))
    assert map_digest(a) == map_digest(b)
    c = CapabilityMap(collected=Measurement.not_collected("x"))
    assert map_digest(c) != map_digest(a)
