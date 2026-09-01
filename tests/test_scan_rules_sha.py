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
        lambda dotted: "edited" if dotted == naming else module_sha(dotted),
    )
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
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.SS1) != before


def test_an_unrelated_signals_module_does_not_move_the_key(monkeypatch):
    """The guard against over-invalidation: QS3 consumes nothing S3 produces."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.QS3)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.QS3) == before


def test_the_naming_module_reaches_s1_too(monkeypatch):
    """P2-D2: S1 reads the generic/layer name tables, so it declares
    scan.naming. Without the declaration, editing a layer word would change
    S1's output while its memo key stood still."""
    naming = SCAN_SIGNALS[ScanSignalId.S3].rule_modules[0]
    assert naming in SCAN_SIGNALS[ScanSignalId.S1].rule_modules
    before = rules_sha(ScanSignalId.S1)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == naming else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.S1) != before


def test_the_sources_module_reaches_both_s1_and_s3(monkeypatch):
    """Review finding 1: S3 selects its blobs with SOURCE_EXTENSIONS, which
    lives in scan.sources. If S3 did not declare sources, adding '.vue' would
    change S3's output while its memo key stood still -- the D10 hazard in the
    epic whose headline invariant is D10. S1 reads the same tuple, so both
    hash it."""
    sources = next(m for m in SCAN_SIGNALS[ScanSignalId.S1].rule_modules if m.endswith(".sources"))
    assert sources in SCAN_SIGNALS[ScanSignalId.S3].rule_modules
    assert sources == "sdlc.assessment.scan.sources"
    for sid in (ScanSignalId.S1, ScanSignalId.S3):
        before = rules_sha(sid)
        monkeypatch.setattr(
            "sdlc.assessment.scan.rules.module_sha",
            lambda dotted: "edited" if dotted == sources else module_sha(dotted),
        )
        assert rules_sha(sid) != before
        monkeypatch.setattr("sdlc.assessment.scan.rules.module_sha", module_sha)


def test_the_testpaths_module_reaches_all_four_of_its_consumers(monkeypatch):
    """P3-D9: S2, QS1, QS2 and QS3 all decide what a test file is with the
    same table, so editing a glob must move all four keys."""
    testpaths = "sdlc.assessment.scan.testpaths"
    for sid in (ScanSignalId.S2, ScanSignalId.QS1, ScanSignalId.QS2, ScanSignalId.QS3):
        assert testpaths in SCAN_SIGNALS[sid].rule_modules
        before = rules_sha(sid)
        monkeypatch.setattr(
            "sdlc.assessment.scan.rules.module_sha",
            lambda dotted: "edited" if dotted == testpaths else module_sha(dotted),
        )
        assert rules_sha(sid) != before, sid.value
        monkeypatch.setattr("sdlc.assessment.scan.rules.module_sha", module_sha)


def test_s3s_module_reaches_ss4_now_that_ss4_consumes_it(monkeypatch):
    """P3-D3: SS4 reads S3's candidates for accessed_by, so S3's bytes are
    part of SS4's key -- an undeclared read would also be an unhashed one."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.SS4)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.SS4) != before
