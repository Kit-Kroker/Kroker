# tests/test_risk_verify_activity.py
"""RD6 at the activity seam. The activity READS; verification.py DECIDES."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import VerifyRiskRefsInput, verify_risk_refs
from sdlc.assessment.risk.models import (
    ControlFamily, ControlState, ProposedControl, ProposedThreat,
    ProposedVulnerability, RiskProposal, StrideCategory, VulnerabilityClass,
)
from sdlc.assessment.scan.models import EvidenceRef


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t.t")
    git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("def charge(): pass\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "one")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, text=True).stdout.strip()
    return str(tmp_path), sha


@pytest.mark.asyncio
async def test_a_verified_row_survives_in_its_own_family(repo):
    repo_dir, sha = repo
    proposal = RiskProposal(
        threats=[ProposedThreat(
            bc_id="BC-001", category=StrideCategory.SPOOFING,
            applicable=True, rationale="r",
            evidence=(EvidenceRef(path="a.py", lines="1"),),
            quote="def charge(): pass")],
        controls=[ProposedControl(
            bc_id="BC-001", family=ControlFamily.VALIDATION,
            state=ControlState.ABSENT, rationale="r")])
    out = await verify_risk_refs(VerifyRiskRefsInput(
        repo_dir=repo_dir, commit_sha=sha, proposal=proposal))
    assert len(out.proposal.threats) == 1
    assert len(out.proposal.controls) == 1
    assert out.unresolved_references == 0


@pytest.mark.asyncio
async def test_a_fabricated_path_drops_its_row_and_feeds_the_rate(repo):
    repo_dir, sha = repo
    proposal = RiskProposal(vulnerabilities=[ProposedVulnerability(
        key="ss1:r:a.py:", classification=VulnerabilityClass.CONFIRMED,
        stride_category=StrideCategory.SPOOFING, rationale="r",
        evidence=(EvidenceRef(path="ghost.py", lines="1"),))])
    out = await verify_risk_refs(VerifyRiskRefsInput(
        repo_dir=repo_dir, commit_sha=sha, proposal=proposal))
    assert out.proposal.vulnerabilities == []
    assert out.refusals["vuln:ss1:r:a.py:"][0] == "dropped_ref_unresolved"
    assert out.fabrication_rate == 1.0


@pytest.mark.asyncio
async def test_an_unreadable_repository_refuses_rather_than_raises(repo):
    """Fail-closed means "unverified", not "crash"."""
    _, sha = repo
    proposal = RiskProposal(threats=[ProposedThreat(
        bc_id="BC-001", category=StrideCategory.SPOOFING, applicable=True,
        rationale="r", evidence=(EvidenceRef(path="a.py", lines="1"),))])
    out = await verify_risk_refs(VerifyRiskRefsInput(
        repo_dir="/nonexistent/repo", commit_sha=sha, proposal=proposal))
    assert out.proposal.threats == []
    assert out.fabrication_rate == 1.0


@pytest.mark.asyncio
async def test_system_rows_verify_in_their_own_families(repo):
    from sdlc.assessment.risk.models import (
        BoundaryVerdict, ChainVerdict, ProposedBoundary, ProposedEscalation,
    )
    repo_dir, sha = repo
    proposal = RiskProposal(
        boundaries=[ProposedBoundary(
            source_bc_id="BC-001", target_bc_id="BC-002",
            verdict=BoundaryVerdict.WEAK, rationale="r",
            evidence=(EvidenceRef(path="a.py", lines="1"),),
            quote="def charge(): pass")],
        escalations=[ProposedEscalation(
            path_id="BC-001->BC-002", verdict=ChainVerdict.PLAUSIBLE,
            rationale="r")])
    out = await verify_risk_refs(VerifyRiskRefsInput(
        repo_dir=repo_dir, commit_sha=sha, proposal=proposal))
    assert len(out.proposal.boundaries) == 1
    assert len(out.proposal.escalations) == 1
    assert out.unresolved_references == 0


@pytest.mark.asyncio
async def test_a_fabricated_boundary_reference_drops_its_row(repo):
    from sdlc.assessment.risk.models import BoundaryVerdict, ProposedBoundary
    repo_dir, sha = repo
    proposal = RiskProposal(boundaries=[ProposedBoundary(
        source_bc_id="BC-001", target_bc_id="BC-002",
        verdict=BoundaryVerdict.SOUND, rationale="r",
        evidence=(EvidenceRef(path="ghost.py"),))])
    out = await verify_risk_refs(VerifyRiskRefsInput(
        repo_dir=repo_dir, commit_sha=sha, proposal=proposal))
    assert out.proposal.boundaries == []
    assert out.refusals["boundary:BC-001->BC-002"][0] == (
        "dropped_ref_unresolved")

