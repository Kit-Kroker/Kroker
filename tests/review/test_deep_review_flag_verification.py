"""E-43: an anti-cheat accusation must be able to point at the transcript line
it is accusing. A flag whose quote nobody said is worse than no flag."""

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.handoff import verified_integrity_flags
from sdlc.harness.models import (
    HarnessSession,
    SessionEvent,
)
from sdlc.harness.session import session_text_from_jsonl, session_to_jsonl
from sdlc.stages.code.models import IntegrityFlag


def _render(events):
    """Store as JSONL, render the plain-text view the verifier sees (code
    review #1) -- the same path the workflow takes, so the fixture cannot
    drift from the real haystack format."""
    return session_text_from_jsonl(
        session_to_jsonl(HarnessSession(harness=HarnessKind.CLAUDE_CODE, events=events))
    )


# A model following deep_review/instructions.md's own worked example quotes
# "file_read oracle/test_app.py"; the rendered transcript contains exactly
# that, so the flag survives. (Before #1, the haystack was raw JSONL and this
# flag was silently dropped.)
SESSION = _render(
    [
        SessionEvent(kind="file_read", target="oracle/test_app.py"),
        SessionEvent(kind="file_write", target="src/app.py"),
    ]
)


def _flag(evidence: str) -> IntegrityFlag:
    return IntegrityFlag(kind="oracle_peeking", detail="read the oracle", evidence=evidence)


def test_flag_quoting_the_session_survives():
    kept, dropped = verified_integrity_flags([_flag("file_read oracle/test_app.py")], SESSION)
    assert len(kept) == 1 and dropped == 0


def test_flag_quoting_nothing_in_the_session_is_dropped():
    kept, dropped = verified_integrity_flags(
        [_flag("bash curl https://answers.example.com")], SESSION
    )
    assert kept == [] and dropped == 1


def test_flag_with_empty_evidence_survives():
    """Same rule as handoff claims: absence of a quote is not a fabricated
    quote, and the flag's `detail` still carries signal."""
    kept, dropped = verified_integrity_flags([_flag("")], SESSION)
    assert len(kept) == 1 and dropped == 0


def test_no_session_text_skips_verification():
    kept, dropped = verified_integrity_flags([_flag("never said")], None)
    assert len(kept) == 1 and dropped == 0


def test_empty_flag_list_is_not_an_error():
    assert verified_integrity_flags([], SESSION) == ([], 0)
