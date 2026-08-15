# tests/test_discover_finalize_activity.py
"""FR-913 (E-48 DD4 step 7): attribute() + decompose() + assign(), wired."""
from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment.activities import (
    DiscoverFinalizeInput, discover_finalize,
)
from sdlc.assessment.discover.apply import apply, stamp
from sdlc.assessment.discover.context import (
    build_context, contract_collected, schema_collected,
)
from sdlc.assessment.discover.models import OwnershipOutcome
from sdlc.assessment.scan.merge import merge
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, CandidateMember, Confidence, MemberKind,
    ScanResult, ScanSignalResult, ScanSignalId, SignalSource, SourceCandidate,
    family_of,
)
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
NC = Measurement.not_collected("timed out")


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pay").mkdir()
    (tmp_path / "pay" / "api.py").write_text(
        "from pay.models import Order\n"
        "@app.post('/api/payments')\ndef charge(): pass\n")
    # s2_sqlalchemy_tablename is the pattern that fires here; the declaration
    # deliberately lives OUTSIDE BC-001's member paths, so ownership resolves
    # by write access rather than by declaration site.
    (tmp_path / "pay" / "models.py").write_text(
        "class Order(Base):\n    __tablename__ = 'payments'\n"
        "    id = Column(Integer)\n")
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = _git(["rev-parse", "HEAD"], tmp_path).strip()
    return str(tmp_path), sha


def _scan(candidates=(), sources=(), **states) -> ScanResult:
    """Thirteen rows, MEASURED unless a signal id is named not-collected.

    The payloads are constructed rather than model_copy'd in, so ScanResult's
    _unmeasured_carries_no_payload validator actually runs over the pairing.
    """
    return ScanResult(
        signals=[
            ScanSignalResult(
                signal=s, family=family_of(s), version=1,
                source=SignalSource.COMPUTED,
                collected=states.get(s.value, MEASURED),
                categories={k: states.get(s.value, MEASURED)
                            for k in CATEGORIES[s]})
            for s in SCAN_ORDER],
        sources=list(sources), candidates=list(candidates))


def _input(repo_dir, sha, **kw) -> DiscoverFinalizeInput:
    base = dict(
        repo_dir=repo_dir, commit_sha=sha,
        members={"BC-001": [CandidateMember(
            kind=MemberKind.HTTP_ROUTE, value="POST /api/payments",
            path="pay/api.py", line=2)]},
        entry_point_paths=["pay/api.py"],
        schema_collected=MEASURED, contract_collected=MEASURED)
    return DiscoverFinalizeInput(**(base | kw))


def test_schema_collected_is_s2s_row():
    assert schema_collected(_scan()).state is CollectionState.MEASURED
    assert schema_collected(_scan(S2=NC)).state is CollectionState.NOT_COLLECTED


def test_contract_collected_needs_both_s3_and_s4():
    """P2-D5: CONTRACT_KINDS includes FRONTEND_ROUTE, which only S4 emits, so
    deriving this from S3 alone would let a dead S4 read as a capability that
    genuinely exposes no frontend route."""
    assert contract_collected(_scan()).state is CollectionState.MEASURED
    for degraded in ("S3", "S4"):
        got = contract_collected(_scan(**{degraded: NC}))
        assert got.state is CollectionState.NOT_COLLECTED
        assert degraded in got.reason


@pytest.mark.asyncio
async def test_finalize_attributes_decomposes_and_assigns(repo):
    repo_dir, sha = repo
    out = await discover_finalize(_input(repo_dir, sha))
    assert out.attribution.coverage.state is CollectionState.MEASURED
    assert out.decomposition.collected.state is CollectionState.MEASURED
    assert out.decomposition.by_capability["BC-001"] == 1
    assert out.ownership.collected.state is CollectionState.MEASURED
    payments = next(e for e in out.ownership.entities if e.entity == "payment")
    assert payments.outcome is OwnershipOutcome.OWNED
    assert payments.owner == "BC-001"


@pytest.mark.asyncio
async def test_the_seam_carries_real_producer_output_end_to_end(repo):
    """E-47c's review found a fabricated field every unit test missed, and
    the fix commit named the cause: "unit tests built inputs decompose() would
    never produce." So this pipes merge() -> build_context() -> stamp() ->
    apply() -> discover_finalize with no hand-built member anywhere.
    """
    repo_dir, sha = repo
    source = SourceCandidate(
        signal=ScanSignalId.S3, local_id="S3-payments", name="payments",
        rule="s3_http_route", detail="one POST route",
        confidence_contribution=Confidence.HIGH,
        members=[CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="POST /api/payments",
                                 path="pay/api.py", line=2)])
    merged = merge([source], {ScanSignalId.S3: MEASURED})
    scan = _scan(candidates=merged.candidates, sources=[source])
    inventory = {"pay/api.py": "from pay.models import Order\n",
                 "pay/models.py": "class Order(Base):\n"
                                  "    __tablename__ = 'payments'\n"}
    context = build_context(scan, inventory, [])
    applied = apply(context, stamp(context, None))
    assert [c.local_key for c in applied.locked] == ["C-01"]

    out = await discover_finalize(DiscoverFinalizeInput(
        repo_dir=repo_dir, commit_sha=sha,
        # bc_id stands in for the lock's attachment; every member below came
        # from apply(), which got it from merge().
        members={"BC-001": list(applied.locked[0].members)},
        entry_point_paths=["pay/api.py"],
        schema_collected=MEASURED, contract_collected=MEASURED))
    assert out.decomposition.by_capability["BC-001"] == 1
    payments = next(e for e in out.ownership.entities if e.entity == "payment")
    assert payments.owner == "BC-001"


@pytest.mark.asyncio
async def test_an_unreadable_tree_degrades_to_three_not_collected_reports(repo):
    """DD9: everything except the capability set itself degrades per-report
    INSIDE the map. The map still ships, with the gap visible where it
    happened."""
    repo_dir, _ = repo
    out = await discover_finalize(_input(repo_dir, "0" * 40))
    assert out.attribution.coverage.state is CollectionState.NOT_COLLECTED
    assert out.attribution.meets_floor is False
    assert out.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert out.ownership.collected.state is CollectionState.NOT_COLLECTED
    assert "could not read the tree" in out.ownership.collected.reason


@pytest.mark.asyncio
async def test_a_degraded_contract_tier_fails_decompose_and_assign_closed(repo):
    """E-47c D9: a degraded contract tier must not read as a capability that
    genuinely exposes nothing. Attribution is unaffected -- it reads blobs,
    not S3."""
    repo_dir, sha = repo
    out = await discover_finalize(_input(repo_dir, sha,
                                         contract_collected=NC))
    assert out.attribution.coverage.state is CollectionState.MEASURED
    assert out.decomposition.collected.state is CollectionState.NOT_COLLECTED
    assert out.ownership.collected.state is CollectionState.NOT_COLLECTED
