import hashlib

import pytest

from sdlc.models import GroundedFinding, ResearchBrief
from sdlc.research import verify


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _write_page(run_id: str, url: str, body: str):
    d = verify.pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / verify.page_filename(url)).write_text(body, encoding="utf-8")


def test_page_filename_is_sha256_of_url():
    url = "https://example.com/a"
    assert verify.page_filename(url) == hashlib.sha256(
        url.encode()).hexdigest() + ".txt"


def test_grounded_quote_present_in_fetched_page_passes(runs_root):
    _write_page("r1", "https://x/1", "The library handles retries natively.")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="handles retries natively",
        claim="it retries")])
    assert verify.verify_brief(brief, "r1") == []


def test_quote_not_found_is_a_violation(runs_root):
    _write_page("r1", "https://x/1", "Nothing about retries here.")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="handles retries natively",
        claim="it retries")])
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["quote_not_found"]


def test_source_unavailable_is_a_violation(runs_root):
    # No page file written for this url -> recalled-lead demotion (finding 5).
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/never", quote="anything", claim="c")])
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_unavailable"]
    assert vios[0].source == "https://x/never"


def test_empty_quote_is_a_violation_not_a_free_pass(runs_root):
    """`"" in haystack` is True, so before the shared verifier an empty quote
    grounded trivially against any fetched page."""
    _write_page("r1", "https://x/1", "some content")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="   ", claim="c")])
    assert [v.kind for v in verify.verify_brief(brief, "r1")] == ["quote_empty"]


def test_whitespace_runs_collapse_but_case_is_preserved(runs_root):
    # HTML extraction mangles whitespace and nothing else (spec §5).
    _write_page("r1", "https://x/1", "handles    retries\n\tnatively")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="handles retries natively", claim="c")])
    assert verify.verify_brief(brief, "r1") == []
    # Case is NOT normalized: a case-only mismatch still fails.
    brief_case = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="HANDLES RETRIES NATIVELY", claim="c")])
    assert [v.kind for v in verify.verify_brief(brief_case, "r1")] == \
        ["quote_not_found"]


def test_replacement_char_standing_in_for_an_apostrophe_still_grounds(runs_root):
    """Regression for the cat-cafe-monitoring smoke run (2026-07-20): Tavily's
    PDF extractor decoded a source's curly apostrophe as U+FFFD (the
    REPLACEMENT CHARACTER) — the fetched page read "owner�s phone", while
    the research agent quoted the same sentence verbatim with an ordinary
    apostrophe: "owner's phone". This is a lost byte upstream of the pipeline,
    not a model error, and previously fail-closed the whole research stage
    over a single punctuation mark."""
    _write_page("r1", "https://x/1",
                "send it to owner�s phone into compatible app")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1",
        quote="send it to owner's phone into compatible app", claim="c")])
    assert verify.verify_brief(brief, "r1") == []


def test_curly_and_straight_quotes_are_interchangeable(runs_root):
    _write_page("r1", "https://x/1", "the cat’s favorite spot")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="the cat's favorite spot", claim="c")])
    assert verify.verify_brief(brief, "r1") == []


def test_apostrophe_normalization_does_not_mask_a_real_word_mismatch(runs_root):
    # Dropping apostrophes must not let genuinely different content pass.
    _write_page("r1", "https://x/1", "the dog's favorite spot")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1", quote="the cat's favorite spot", claim="c")])
    assert [v.kind for v in verify.verify_brief(brief, "r1")] == \
        ["quote_not_found"]


def test_markdown_bold_markers_in_page_text_do_not_break_grounding(runs_root):
    """Regression for the cat-cafe-monitoring smoke run (2026-07-20): Tavily's
    extractor left literal `**bold**` markdown markers inside plain-text
    Wikipedia content ("between **1-5 meters**, making them suitable"). The
    research agent quoted the same span without the markers, which is
    faithful to the source but previously failed the exact-substring check."""
    _write_page("r1", "https://x/1",
                "advanced technologies like **UWB (Ultra-Wideband)** can "
                "achieve **centimeter-level precision** for robotics")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1",
        quote="advanced technologies like UWB (Ultra-Wideband) can "
              "achieve centimeter-level precision",
        claim="c")])
    assert verify.verify_brief(brief, "r1") == []


def test_markdown_bold_normalization_does_not_mask_a_real_word_mismatch(runs_root):
    _write_page("r1", "https://x/1", "**UWB** can achieve meter-level precision")
    brief = ResearchBrief(grounded_findings=[GroundedFinding(
        source_url="https://x/1",
        quote="UWB can achieve centimeter-level precision", claim="c")])
    assert [v.kind for v in verify.verify_brief(brief, "r1")] == \
        ["quote_not_found"]


def test_brief_digest_ignores_prose_ordering_and_confidence():
    """Same (source_url, claim) facts -> same digest, regardless of order,
    summary, or confidence (spec §7)."""
    a = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="u1", quote="q1", claim="c1"),
            GroundedFinding(source_url="u2", quote="q2", claim="c2")],
        summary="one wording", confidence=0.9)
    b = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="u2", quote="DIFFERENT", claim="c2"),
            GroundedFinding(source_url="u1", quote="also different", claim="c1")],
        summary="another wording", confidence=0.1)
    assert verify.brief_digest(a) == verify.brief_digest(b)


def test_brief_digest_moves_when_a_fact_changes():
    a = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="u1", quote="q", claim="c1")])
    b = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="u1", quote="q", claim="c2")])
    assert verify.brief_digest(a) != verify.brief_digest(b)
