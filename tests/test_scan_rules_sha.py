"""D10: the memo key hashes the rules, not just a version number. This is the
test that would have caught E-3 -- and its second half is the one the spec's
first draft got wrong."""
from __future__ import annotations

from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.assessment.scan.rules import module_sha, rules_sha


def test_every_signal_has_a_hashable_module():
    for sid in SCAN_SIGNALS:
        assert len(rules_sha(sid)) == 64


def test_rules_sha_is_stable_across_calls():
    assert rules_sha(ScanSignalId.S3) == rules_sha(ScanSignalId.S3)


def test_two_signals_have_different_shas():
    assert rules_sha(ScanSignalId.S1) != rules_sha(ScanSignalId.S3)


def test_a_shared_rule_module_reaches_both_its_consumers(monkeypatch):
    """S3 and S5 both declare scan.naming. Editing it must move both keys."""
    naming = SCAN_SIGNALS[ScanSignalId.S3].rule_modules[0]
    before_s3, before_s5 = rules_sha(ScanSignalId.S3), rules_sha(ScanSignalId.S5)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == naming else module_sha(dotted))
    assert rules_sha(ScanSignalId.S3) != before_s3
    assert rules_sha(ScanSignalId.S5) != before_s5


def test_an_upstream_signals_module_reaches_its_consumer(monkeypatch):
    """The transitive half. SS1 consumes S3, so editing S3's pattern table
    must move SS1's key -- otherwise the cache serves SS1's stale records
    against S3's fresh ones."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.SS1)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted))
    assert rules_sha(ScanSignalId.SS1) != before


def test_an_unrelated_signals_module_does_not_move_the_key(monkeypatch):
    """The guard against over-invalidation: QS3 consumes nothing S3 produces."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.QS3)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted))
    assert rules_sha(ScanSignalId.QS3) == before
