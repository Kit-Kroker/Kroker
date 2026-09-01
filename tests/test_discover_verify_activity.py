# tests/test_discover_verify_activity.py
"""E-48 DD8: the activity reads blobs at the pinned commit; the pure function
decides. NFR-9: git show only -- no checkout, no execution."""

import subprocess

import pytest

from sdlc.assessment.activities import VerifyRefsInput, verify_discover_refs
from sdlc.assessment.discover.map import (
    DiscoverAction,
    DiscoverProposal,
    EvidenceRef,
    ProposedDisposition,
)


@pytest.fixture
def repo(tmp_path):
    def run(*args):
        subprocess.run(
            args, cwd=tmp_path, check=True, capture_output=True, stdin=subprocess.DEVNULL
        )

    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    (tmp_path / "pay.py").write_text(
        "def charge(order_id):\n    return gateway.charge(order_id)\n", encoding="utf-8"
    )
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "seed")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()
    return str(tmp_path), sha


def _proposal(**kw):
    return DiscoverProposal(
        dispositions=[
            ProposedDisposition(
                candidate_id="C1", action=DiscoverAction.CONFIRM, rationale="r", **kw
            )
        ]
    )


@pytest.mark.asyncio
async def test_a_real_path_resolves_against_the_pinned_commit(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(evidence=(EvidenceRef(path="pay.py", lines="1-2"),)),
        )
    )
    assert out.refusals == {}
    assert out.total_references == 1


@pytest.mark.asyncio
async def test_a_fabricated_path_is_refused_by_the_activity(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(evidence=(EvidenceRef(path="ghost.py"),)),
        )
    )
    assert out.refusals["C1"][0] == "dropped_ref_unresolved"
    assert out.unresolved_references == 1


@pytest.mark.asyncio
async def test_a_directory_path_does_not_resolve_as_a_file(repo):
    """git show sha:dir returns a TREE LISTING with exit 0 -- which is not
    the file's bytes (read_committed_bytes code review #4)."""
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir, commit_sha=sha, proposal=_proposal(evidence=(EvidenceRef(path="."),))
        )
    )
    assert out.refusals["C1"][0] == "dropped_ref_unresolved"


@pytest.mark.asyncio
async def test_a_quote_byte_verifies_against_the_committed_bytes(repo):
    repo_dir, sha = repo
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=repo_dir,
            commit_sha=sha,
            proposal=_proposal(
                evidence=(EvidenceRef(path="pay.py", lines="1-2"),), quote="gateway.charge"
            ),
        )
    )
    assert out.refusals == {}


@pytest.mark.asyncio
async def test_an_unreadable_repo_refuses_every_reference_rather_than_raising(tmp_path):
    """Fail-closed means "unverified", not "crash" -- read_committed_bytes'
    rule. Every ref unresolved trips the guard upstream, which is correct."""
    out = await verify_discover_refs(
        VerifyRefsInput(
            repo_dir=str(tmp_path),
            commit_sha="0" * 40,
            proposal=_proposal(evidence=(EvidenceRef(path="pay.py"),)),
        )
    )
    assert out.unresolved_references == 1
