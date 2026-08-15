"""FR-913 (E-48): the activity that reads the tree for discover."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import DiscoverContextInput, discover_context
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, CandidateMember, Confidence, MemberKind,
    ScanCandidate, ScanResult, ScanSignalResult, SignalSource,
    SourceCandidate, family_of,
)
from sdlc.measurement import CollectionState, Measurement


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pay").mkdir()
    (tmp_path / "pay" / "api.py").write_text("from pay.core import charge\n")
    (tmp_path / "pay" / "core.py").write_text("def charge(): pass\n")
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = _git(["rev-parse", "HEAD"], tmp_path).strip()
    return str(tmp_path), sha


def _signals() -> list[ScanSignalResult]:
    """All thirteen rows, MEASURED -- ScanResult requires the whole set in
    order, and a payload may only be carried by a signal that collected."""
    val = Measurement.measured(0.0)
    return [ScanSignalResult(signal=s, family=family_of(s), version=1,
                             source=SignalSource.COMPUTED, collected=val,
                             categories={k: val for k in CATEGORIES[s]})
            for s in SCAN_ORDER]


SCAN = ScanResult(
    signals=_signals(),
    sources=[SourceCandidate(
        signal="S3", local_id="S3-payments", name="payments",
        rule="s3_http_route", detail="",
        confidence_contribution=Confidence.HIGH,
        members=[CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="POST /pay", path="pay/api.py")])],
    candidates=[ScanCandidate(
        candidate_id="C-01", name="payments", sources=["S3-payments"],
        confidence=Confidence.LOW,
        members=[CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="POST /pay", path="pay/api.py"),
                 CandidateMember(kind=MemberKind.FILE_PATH,
                                 value="pay/core.py", path="pay/core.py")])])


@pytest.mark.asyncio
async def test_the_activity_reads_the_tree_and_builds_the_packet(repo):
    repo_dir, sha = repo
    ctx = await discover_context(DiscoverContextInput(
        repo_dir=repo_dir, commit_sha=sha, tree_hash="t", scan=SCAN))
    assert ctx.collected.state is CollectionState.MEASURED
    assert len(ctx.candidates) == 1
    assert ctx.candidates[0].cohesion.value == 1.0
    assert ctx.file_count == 2


@pytest.mark.asyncio
async def test_an_unreadable_tree_degrades_rather_than_raising(repo):
    """scan_packages' rule: one activity that cannot read the tree must
    report not_collected, not take the phase down with a traceback."""
    repo_dir, _ = repo
    ctx = await discover_context(DiscoverContextInput(
        repo_dir=repo_dir, commit_sha="0" * 40, tree_hash="t", scan=SCAN))
    assert ctx.collected.state is CollectionState.NOT_COLLECTED
    assert "could not read the tree" in ctx.collected.reason
    assert ctx.candidates == ()


@pytest.mark.asyncio
async def test_build_failure_degrades_with_distinct_reason(repo, monkeypatch):
    """Finding 5: 'could not build context' is distinct from 'could not read tree'."""
    repo_dir, sha = repo
    def _boom(*a, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr("sdlc.assessment.activities.build_context", _boom)
    ctx = await discover_context(DiscoverContextInput(
        repo_dir=repo_dir, commit_sha=sha, tree_hash="t", scan=SCAN))
    assert ctx.collected.state is CollectionState.NOT_COLLECTED
    assert "could not build context" in ctx.collected.reason
    assert ctx.candidates == ()
