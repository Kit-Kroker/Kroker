"""E-43: an anti-cheat accusation must be able to point at the transcript line
it is accusing. A flag whose quote nobody said is worse than no flag."""
from sdlc.handoff import verified_integrity_flags
from sdlc.models import IntegrityFlag

SESSION = "bash cat oracle/test_app.py\nfile_write src/app.py\n"


def _flag(evidence: str) -> IntegrityFlag:
    return IntegrityFlag(kind="oracle_peeking", detail="read the oracle",
                         evidence=evidence)


def test_flag_quoting_the_session_survives():
    kept, dropped = verified_integrity_flags(
        [_flag("bash cat oracle/test_app.py")], SESSION)
    assert len(kept) == 1 and dropped == 0


def test_flag_quoting_nothing_in_the_session_is_dropped():
    kept, dropped = verified_integrity_flags(
        [_flag("bash curl https://answers.example.com")], SESSION)
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
