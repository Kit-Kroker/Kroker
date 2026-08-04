"""The deterministic half of the handoff (spec 2.3).

A claim may only name files the diff actually touched. This is what stops
the extractor attributing a change to a file the task never opened.
"""
from sdlc.handoff import claim_survival_score, cross_check_claims
from sdlc.models import HandoffClaim


def test_claim_naming_touched_file_survives():
    claims = [HandoffClaim(text="rewrote src/app.py routing",
                           evidence="file_write src/app.py")]
    kept, dropped = cross_check_claims(claims, ["src/app.py"])
    assert len(kept) == 1
    assert dropped == 0


def test_claim_naming_untouched_file_is_dropped():
    claims = [HandoffClaim(text="patched src/other.py too",
                           evidence="file_write src/other.py")]
    kept, dropped = cross_check_claims(claims, ["src/app.py"])
    assert kept == []
    assert dropped == 1


def test_claim_naming_no_file_survives():
    """Design decisions legitimately mention no path at all."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT",
                           evidence="I'll use cookies here")]
    kept, dropped = cross_check_claims(claims, ["src/app.py"])
    assert len(kept) == 1
    assert dropped == 0


def test_path_in_evidence_is_checked_not_only_text():
    claims = [HandoffClaim(text="fixed the parser",
                           evidence="file_write src/ghost.py")]
    kept, dropped = cross_check_claims(claims, ["src/app.py"])
    assert kept == []
    assert dropped == 1


def test_windows_separators_normalise():
    claims = [HandoffClaim(text=r"edited src\app.py",
                           evidence="file_write src/app.py")]
    kept, dropped = cross_check_claims(claims, ["src/app.py"])
    assert len(kept) == 1
    assert dropped == 0


def test_survival_score():
    assert claim_survival_score(3, 1) == 0.75
    assert claim_survival_score(4, 0) == 1.0
    assert claim_survival_score(0, 2) == 0.0


def test_survival_score_is_none_when_no_claims():
    """No claims is not a score of zero -- nothing was measured."""
    assert claim_survival_score(0, 0) is None
