"""D10: cache the row with its payload, and never cache a result that is not
MEASURED."""
from __future__ import annotations

import pytest

from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import (
    CATEGORIES, ScanSignalId, ScanSignalResult, SignalOutput, SignalSource,
    family_of,
)
from sdlc.measurement import Measurement
from sdlc.memoization.cache import signal_key


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _out(sid: ScanSignalId, measured: bool) -> SignalOutput:
    val = (Measurement.measured(3.0) if measured
           else Measurement.not_collected("activity timed out"))
    return SignalOutput(row=ScanSignalResult(
        signal=sid, family=family_of(sid), version=1,
        source=SignalSource.COMPUTED, collected=val,
        categories={k: val for k in CATEGORIES[sid]}))


def test_key_changes_with_every_term():
    base = signal_key("S3", 1, "aaa", "bbb")
    assert base != signal_key("S1", 1, "aaa", "bbb")
    assert base != signal_key("S3", 2, "aaa", "bbb")
    assert base != signal_key("S3", 1, "zzz", "bbb")
    assert base != signal_key("S3", 1, "aaa", "zzz")


def test_key_is_stable_and_hex():
    k = signal_key("S3", 1, "aaa", "bbb")
    assert k == signal_key("S3", 1, "aaa", "bbb")
    assert len(k) == 64


def test_store_then_load_round_trips_row_and_payload():
    out = _out(ScanSignalId.QS3, measured=True)
    assert memo.store(ScanSignalId.QS3, "tree1", out) is True
    got = memo.load(ScanSignalId.QS3, "tree1")
    assert got is not None
    assert got.row.collected.value == 3.0
    assert got.row.signal is ScanSignalId.QS3


def test_a_not_measured_result_is_never_stored():
    """Memoizing a timeout returns that timeout as a cache hit forever."""
    out = _out(ScanSignalId.QS3, measured=False)
    assert memo.store(ScanSignalId.QS3, "tree1", out) is False
    assert memo.load(ScanSignalId.QS3, "tree1") is None


def test_a_different_tree_misses():
    memo.store(ScanSignalId.QS3, "tree1", _out(ScanSignalId.QS3, True))
    assert memo.load(ScanSignalId.QS3, "tree2") is None


def test_corrupt_cache_content_is_a_miss_not_a_crash():
    from sdlc.memoization import cache
    from sdlc.assessment.scan.rules import rules_sha
    key = signal_key(ScanSignalId.QS3.value, 1,
                     rules_sha(ScanSignalId.QS3), "tree1")
    cache.put(key, "{not json")
    assert memo.load(ScanSignalId.QS3, "tree1") is None
