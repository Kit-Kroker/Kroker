"""The deterministic half of the handoff (spec 2.3) plus E-43 quote
verification.

A claim may only name files the diff actually touched, and its evidence quote
must actually appear in the transcript it was drawn from. The first stops the
extractor attributing a change to a file the task never opened; the second
stops it inventing the quote that supports the claim.
"""

from sdlc.grounding import Profile, verify_quote
from sdlc.handoff import claim_survival_score, cross_check_claims
from sdlc.harness.session import session_text_from_jsonl, session_to_jsonl
from sdlc.measurement import CollectionState
from sdlc.models import HandoffClaim, HarnessKind, HarnessSession, SessionEvent


def _render(events):
    """Build the haystack the way the workflow does: store as JSONL, then
    render the plain-text view the verifier sees (code review #1). Hand-typed
    plain-text fixtures hid the JSONL/prose mismatch this test exists to catch."""
    return session_text_from_jsonl(
        session_to_jsonl(HarnessSession(harness=HarnessKind.CLAUDE_CODE, events=events))
    )


SESSION = _render(
    [
        SessionEvent(kind="file_write", target="src/app.py"),
        SessionEvent(kind="model_turn", text="I'll use cookies here"),
        SessionEvent(kind="file_write", target="src/app.py"),
    ]
)


def test_claim_naming_touched_file_survives():
    claims = [HandoffClaim(text="rewrote src/app.py routing", evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1
    assert r.dropped_paths == 0 and r.dropped_quotes == 0


def test_claim_naming_untouched_file_is_dropped():
    claims = [HandoffClaim(text="patched src/other.py too", evidence="file_write src/other.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert r.kept == []
    assert r.dropped_paths == 1


def test_claim_naming_no_file_survives():
    """Design decisions legitimately mention no path at all."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT", evidence="I'll use cookies here")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1


def test_path_in_evidence_is_checked_not_only_text():
    claims = [HandoffClaim(text="fixed the parser", evidence="file_write src/ghost.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert r.kept == [] and r.dropped_paths == 1


def test_windows_separators_normalise():
    claims = [HandoffClaim(text=r"edited src\app.py", evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"])
    assert len(r.kept) == 1


def test_evidence_present_in_the_session_survives():
    claims = [HandoffClaim(text="chose cookie sessions over JWT", evidence="I'll use cookies here")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert len(r.kept) == 1
    assert r.dropped_quotes == 0


def test_fabricated_evidence_is_dropped():
    """E-43: today this claim survives and is injected into the next task's
    prompt, carrying a quote nobody said."""
    claims = [
        HandoffClaim(
            text="chose cookie sessions over JWT",
            evidence="I decided to use JWTs after benchmarking",
        )
    ]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert r.kept == []
    assert r.dropped_quotes == 1 and r.dropped_paths == 0


def test_claim_with_no_evidence_text_survives():
    """Same rationale as the no-path rule: absence of a quote is not a
    fabricated quote."""
    claims = [HandoffClaim(text="chose cookie sessions over JWT", evidence="")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert len(r.kept) == 1


def test_missing_session_text_skips_quote_verification():
    """Absence of the haystack is not evidence against the quote. If session
    capture failed, dropping every quoted claim would silently empty the
    handoff over an infrastructure failure."""
    claims = [HandoffClaim(text="chose cookies", evidence="nothing like this was ever said")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=None)
    assert len(r.kept) == 1
    assert r.dropped_quotes == 0


def test_path_check_still_applies_when_the_quote_verifies():
    claims = [HandoffClaim(text="patched src/other.py", evidence="file_write src/app.py")]
    r = cross_check_claims(claims, ["src/app.py"], session_text=SESSION)
    assert r.kept == [] and r.dropped_paths == 1


def test_evidence_is_verified_verbatim_not_as_extracted_text():
    """VERBATIM_BYTES: a transcript is bytes we stored, not extractor output."""
    assert not verify_quote("def f(kwargs):", "def f(**kwargs):", Profile.VERBATIM_BYTES)


def test_survival_score():
    assert claim_survival_score(3, 1).value == 0.75
    assert claim_survival_score(4, 0).value == 1.0
    assert claim_survival_score(0, 2).value == 0.0
    assert claim_survival_score(0, 2).state is CollectionState.MEASURED


def test_survival_score_is_not_collected_when_no_claims():
    """No claims is not a score of zero -- nothing was measured."""
    m = claim_survival_score(0, 0)
    assert m.state is CollectionState.NOT_COLLECTED
    assert m.value is None
