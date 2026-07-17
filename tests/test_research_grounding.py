from pathlib import Path

import pytest

from sdlc.models import GroundedFinding, MemoryKind, ResearchBrief
from sdlc.research import verify
from sdlc.research.retain import verified_findings_to_retain


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _write_page(run_id, url, body):
    d = verify.pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / verify.page_filename(url)).write_text(body, encoding="utf-8")


def test_only_verified_findings_are_retained(runs_root):
    _write_page("r1", "https://x/1", "quote one is here")
    # url /2 is NEVER fetched -> a recalled lead masquerading as grounded.
    brief = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="https://x/1", quote="quote one is here",
                        claim="c1"),
        GroundedFinding(source_url="https://x/2", quote="never fetched",
                        claim="c2"),
    ])
    items = verified_findings_to_retain(brief, "r1")
    assert len(items) == 1
    assert items[0].kind is MemoryKind.RESEARCH_FINDING
    assert items[0].metadata["stage"] == "research"
    assert items[0].metadata["source_url"] == "https://x/1"


def test_recalled_lead_in_grounded_fails_verification(runs_root):
    """Demotion needs no mechanism (finding 5): a lead that was never fetched
    this run has no page file, so it fails source-never-fetched."""
    brief = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="https://x/recalled", quote="from memory",
                        claim="c")])
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_never_fetched"]
    assert verified_findings_to_retain(brief, "r1") == []


@pytest.mark.asyncio
async def test_verify_brief_activity_raises_on_violation(runs_root):
    """The post-run activity turns a violation into a GroundingViolation
    (NOT ModelRetry) — the research stage fails closed. (Task 1 finding A: the
    original @agent.output_validator design was silently dropped by
    TemporalAgent; this activity is the authorized fallback.)"""
    from sdlc.research.verify import GroundingViolation, verify_brief_activity
    brief = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="https://x/none", quote="x", claim="c")])
    with pytest.raises(GroundingViolation) as exc_info:
        await verify_brief_activity(brief, "r1")
    # The exception carries the violations so the workflow can surface them.
    assert exc_info.value.violations
    assert exc_info.value.violations[0].source_url == "https://x/none"


@pytest.mark.asyncio
async def test_verify_brief_activity_passes_clean_brief(runs_root):
    """A brief whose grounded quotes are all substrings of fetched pages
    verifies cleanly — no raise."""
    from sdlc.research.verify import verify_brief_activity
    _write_page("r1", "https://x/1", "the verbatim quote is here")
    brief = ResearchBrief(grounded_findings=[
        GroundedFinding(source_url="https://x/1", quote="the verbatim quote is here",
                        claim="c")])
    await verify_brief_activity(brief, "r1")  # no raise
