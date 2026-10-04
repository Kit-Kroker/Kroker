import inspect
from pathlib import Path

import pytest

from sdlc.grounding import Violation
from sdlc.memory.models import MemoryKind
from sdlc.stages.research import verify
from sdlc.stages.research.models import (
    GroundedFinding,
    ResearchBrief,
)
from sdlc.stages.research.retain import verified_findings_to_retain


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    return tmp_path


def _write_page(run_id, url, body):
    d = verify.pages_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / verify.page_filename(url)).write_text(body, encoding="utf-8")


def _no_read(*args, **kwargs):
    raise AssertionError("the retain path must not read page files (SC-004)")


def test_only_verified_findings_are_retained(runs_root):
    _write_page("r1", "https://x/1", "quote one is here")
    # url /2 is NEVER fetched -> a recalled lead masquerading as grounded.
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="quote one is here", claim="c1"),
            GroundedFinding(source_url="https://x/2", quote="never fetched", claim="c2"),
        ]
    )
    items = verified_findings_to_retain(brief, verify.verify_brief(brief, "r1"))
    assert len(items) == 1
    assert items[0].kind is MemoryKind.RESEARCH_FINDING
    assert items[0].metadata["stage"] == "research"
    assert items[0].metadata["source_url"] == "https://x/1"


def test_recalled_lead_in_grounded_fails_verification(runs_root):
    """Demotion needs no mechanism (finding 5): a lead that was never fetched
    this run has no page file, so it fails source-never-fetched."""
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/recalled", quote="from memory", claim="c")
        ]
    )
    vios = verify.verify_brief(brief, "r1")
    assert [v.kind for v in vios] == ["source_unavailable"]
    assert verified_findings_to_retain(brief, vios) == []


def test_a_result_naming_a_finding_drops_it_despite_its_page(runs_root):
    """The result decides, not the disk: a violation naming /2 drops it even
    though /2's page is present and its quote verifies."""
    _write_page("r1", "https://x/1", "quote one is here")
    _write_page("r1", "https://x/2", "quote two is here")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="quote one is here", claim="c1"),
            GroundedFinding(source_url="https://x/2", quote="quote two is here", claim="c2"),
        ]
    )
    result = [Violation(kind="quote_not_found", source="https://x/2", quote="quote two is here")]
    items = verified_findings_to_retain(brief, result)
    assert len(items) == 1
    assert items[0].metadata["source_url"] == "https://x/1"


def test_an_empty_result_retains_every_grounded_finding_in_order(runs_root):
    """An empty result is the caller's claim that the brief verified clean:
    every grounded finding is retained, in the brief's order, with today's
    exact item content (FR-006)."""
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="quote one is here", claim="c1"),
            GroundedFinding(source_url="https://x/2", quote="quote two is here", claim="c2"),
        ]
    )
    items = verified_findings_to_retain(brief, [])
    assert [i.kind for i in items] == [MemoryKind.RESEARCH_FINDING] * 2
    assert [i.bank for i in items] == ["project:default", "project:default"]
    assert [i.text for i in items] == ["c1 — https://x/1", "c2 — https://x/2"]
    assert items[0].metadata == {"stage": "research", "source_url": "https://x/1"}
    assert items[1].metadata == {"stage": "research", "source_url": "https://x/2"}
    banked = verified_findings_to_retain(brief, [], bank="project:other")
    assert [i.bank for i in banked] == ["project:other", "project:other"]


def test_the_retain_path_performs_no_file_read(runs_root, monkeypatch):
    """SC-004: with every filesystem read patched to raise, the same brief and
    result yield the same items — the retain path reads no file. Patching
    `verify.pages_dir` and the `Path` methods (not `verify.verify_brief`) is
    what reaches the name `retain.py` imported."""
    _write_page("r1", "https://x/1", "quote one is here")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="quote one is here", claim="c1"),
            GroundedFinding(source_url="https://x/2", quote="never fetched", claim="c2"),
        ]
    )
    result = verify.verify_brief(brief, "r1")
    items = verified_findings_to_retain(brief, result)
    with monkeypatch.context() as m:
        m.setattr(verify, "pages_dir", _no_read)
        m.setattr(Path, "is_file", _no_read)
        m.setattr(Path, "exists", _no_read)
        m.setattr(Path, "read_text", _no_read)
        m.setattr(Path, "open", _no_read)
        assert verified_findings_to_retain(brief, result) == items


def test_the_verification_result_is_a_required_argument():
    """FR-005/US2-4: `violations` is required and positional — a caller
    without a verification result cannot call the function by leaving it
    out."""
    sig = inspect.signature(verified_findings_to_retain)
    assert list(sig.parameters) == ["brief", "violations", "bank"]
    assert sig.parameters["violations"].default is inspect.Parameter.empty
    brief = ResearchBrief(grounded_findings=[])
    with pytest.raises(TypeError):
        verified_findings_to_retain(brief)


@pytest.mark.asyncio
async def test_verify_brief_activity_returns_violations(runs_root):
    """The post-run activity RETURNS the violations list (does not raise) so
    the workflow can inspect it directly — temporalio wraps activity-raised
    exceptions in ActivityError, preventing a typed catch. The workflow checks
    `if violations:` and fails the stage closed. (Task 1 finding A fallback.)
    Code-review C1: the previous raise-based form was unwrappable on the
    workflow side; this pins the return-shape contract."""
    from sdlc.stages.research.verify import verify_brief_activity

    brief = ResearchBrief(
        grounded_findings=[GroundedFinding(source_url="https://x/none", quote="x", claim="c")]
    )
    violations = await verify_brief_activity(brief, "r1")
    assert violations
    assert violations[0].source == "https://x/none"
    assert violations[0].kind == "source_unavailable"


@pytest.mark.asyncio
async def test_verify_brief_activity_passes_clean_brief(runs_root):
    """A brief whose grounded quotes are all substrings of fetched pages
    verifies cleanly — returns an empty violations list."""
    from sdlc.stages.research.verify import verify_brief_activity

    _write_page("r1", "https://x/1", "the verbatim quote is here")
    brief = ResearchBrief(
        grounded_findings=[
            GroundedFinding(source_url="https://x/1", quote="the verbatim quote is here", claim="c")
        ]
    )
    assert await verify_brief_activity(brief, "r1") == []
