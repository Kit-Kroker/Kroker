"""FR-914 (E-43): one substring invariant, two normalization profiles.

The profile split is the load-bearing part. EXTRACTED_TEXT's loosenings are
justified by specific Tavily extraction bugs; applying them to code or
transcripts would weaken the check SC-7 rests on.
"""
from sdlc.grounding import (
    Profile, Violation, normalize, quote_violation, verify_quote,
)

EXTRACTED = Profile.EXTRACTED_TEXT
VERBATIM = Profile.VERBATIM_BYTES


def test_plain_substring_grounds_under_both_profiles():
    hay = "The library handles retries natively."
    assert verify_quote("handles retries natively", hay, EXTRACTED)
    assert verify_quote("handles retries natively", hay, VERBATIM)


def test_absent_quote_fails_under_both_profiles():
    hay = "Nothing about retries here."
    assert not verify_quote("handles retries natively", hay, EXTRACTED)
    assert not verify_quote("handles retries natively", hay, VERBATIM)


def test_whitespace_collapses_under_both_profiles():
    """Extractors mangle whitespace; transcripts and prompt-rendered code get
    re-wrapped and re-indented. This is the one loosening both profiles share."""
    hay = "handles    retries\n\tnatively"
    assert verify_quote("handles retries natively", hay, EXTRACTED)
    assert verify_quote("handles retries natively", hay, VERBATIM)


def test_case_is_never_normalized():
    hay = "handles retries natively"
    assert not verify_quote("HANDLES RETRIES NATIVELY", hay, EXTRACTED)
    assert not verify_quote("HANDLES RETRIES NATIVELY", hay, VERBATIM)


def test_replacement_char_apostrophe_grounds_only_under_extracted_text():
    """Tavily's PDF extractor decoded a curly apostrophe as U+FFFD
    (cat-cafe-monitoring smoke run, 2026-07-20). Justified for extractor
    output; NOT justified for code, where quote glyphs are meaningful inside
    string literals."""
    hay = "send it to owner\ufffds phone"
    assert verify_quote("send it to owner's phone", hay, EXTRACTED)
    assert not verify_quote("send it to owner's phone", hay, VERBATIM)


def test_markdown_bold_grounds_only_under_extracted_text():
    """Tavily left literal ** markers in plain prose (same smoke run). Under
    VERBATIM_BYTES this must fail: ** is meaningful Python."""
    hay = "achieve **centimeter-level precision** for robotics"
    assert verify_quote("achieve centimeter-level precision", hay, EXTRACTED)
    assert not verify_quote("achieve centimeter-level precision", hay, VERBATIM)


def test_kwargs_in_code_survives_verbatim_but_is_corrupted_by_extracted():
    """The concrete reason the profiles must never be merged."""
    hay = "def f(**kwargs):\n    return kwargs\n"
    assert verify_quote("def f(**kwargs):", hay, VERBATIM)
    # Under EXTRACTED_TEXT both sides lose the markers, so a DIFFERENT
    # signature would also match -- exactly the loosening we refuse for code.
    assert verify_quote("def f(kwargs):", hay, EXTRACTED)
    assert not verify_quote("def f(kwargs):", hay, VERBATIM)


def test_normalization_does_not_mask_a_real_word_mismatch():
    hay = "the dog's favorite spot"
    assert not verify_quote("the cat's favorite spot", hay, EXTRACTED)


def test_empty_quote_never_grounds():
    """`"" in haystack` is True, so an empty quote verified trivially before
    this check existed -- a hole in the shipped research verifier."""
    assert not verify_quote("", "anything at all", EXTRACTED)
    assert not verify_quote("   \n\t ", "anything at all", VERBATIM)


def test_quote_violation_returns_none_when_grounded():
    assert quote_violation("retries", "handles retries", VERBATIM,
                           source="src/a.py@abc") is None


def test_quote_violation_kinds():
    absent = quote_violation("missing", "haystack", VERBATIM, source="s")
    assert absent == Violation(kind="quote_not_found", source="s",
                               quote="missing")
    empty = quote_violation("  ", "haystack", VERBATIM, source="s")
    assert empty.kind == "quote_empty"


def test_normalize_is_idempotent():
    for profile in (EXTRACTED, VERBATIM):
        once = normalize("a  **b**  c", profile)
        assert normalize(once, profile) == once
