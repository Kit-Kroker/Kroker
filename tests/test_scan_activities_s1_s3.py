"""Plan 2 gives the scan memo its FIRST production caller. Plan 1 built
memo.load/store and shipped eleven stubs, none of which could ever store --
memo.store refuses anything not MEASURED."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment import activities as acts
from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.measurement import CollectionState

TREE = 40 * "ab"        # any stable 40-hex-shaped string


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Each test gets a clean memo cache. The activities store MEASURED
    results keyed on tree_hash, and several tests share TREE -- without
    isolation a stored result from one test is served as a cache hit to the
    next (test_scan_memo.py applies the same discipline)."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _repo(tmp_path):
    """A real git repo, because these activities read blobs at a commit."""
    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    src = tmp_path / "src" / "payments"
    src.mkdir(parents=True)
    (src / "api.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create():\n    ...\n")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, text=True).stdout.strip()
    return str(tmp_path), sha


def _input(repo, sha, tree=TREE):
    return acts.ScanSignalInput(repo_dir=repo, commit_sha=sha, tree_hash=tree)


@pytest.mark.asyncio
async def test_s1_reports_the_payments_package(tmp_path):
    repo, sha = _repo(tmp_path)
    out = await acts.scan_packages(_input(repo, sha))
    assert out.row.collected.state is CollectionState.MEASURED
    assert any(c.local_id == "S1-src--payments" for c in out.sources)


@pytest.mark.asyncio
async def test_s3_reports_the_route(tmp_path):
    repo, sha = _repo(tmp_path)
    out = await acts.scan_entrypoints(_input(repo, sha))
    assert out.row.collected.state is CollectionState.MEASURED
    assert any("POST /api/payments" in m.value
               for c in out.sources for m in c.members)


@pytest.mark.asyncio
async def test_a_measured_result_is_stored_and_served_from_the_memo(
        tmp_path, monkeypatch):
    repo, sha = _repo(tmp_path)
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "cache"))
    first = await acts.scan_packages(_input(repo, sha))
    assert memo.load(ScanSignalId.S1, TREE) is not None
    # A second run must not re-read the tree: point it at a repo that is gone.
    second = await acts.scan_packages(_input("/nonexistent", sha))
    assert second.model_dump_json() == first.model_dump_json()


@pytest.mark.asyncio
async def test_a_failed_signal_is_not_cached(tmp_path, monkeypatch):
    """D10: memoizing a failure would return it as a cache hit forever."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "cache"))
    out = await acts.scan_packages(_input("/nonexistent", "deadbeef"))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert memo.load(ScanSignalId.S1, TREE) is None


@pytest.mark.asyncio
async def test_an_activity_never_raises(tmp_path):
    """A signal that fails degrades ALONE; run_or_degrade covers timeouts,
    this covers everything inside the activity."""
    out = await acts.scan_entrypoints(_input("/nonexistent", "deadbeef"))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []


def test_built_and_owed_partition_the_activity_signals():
    """A body that lands without its OWED_BY entry removed would report
    'not implemented' forever; the reverse would KeyError at runtime."""
    declared = {s for s in acts.SCAN_SIGNALS
                if acts.SCAN_SIGNALS[s].activity}
    assert acts.BUILT | set(acts.OWED_BY) == declared
    assert not (acts.BUILT & set(acts.OWED_BY))


def test_the_two_built_signals_are_s1_and_s3():
    assert acts.BUILT == {ScanSignalId.S1, ScanSignalId.S3}
