"""E-84: ScanResult -> CodebaseMap. The map is what the Architect reads."""
from __future__ import annotations

import random

from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, CandidateMember, Confidence, CoverageRecord,
    MemberKind, ScanCandidate, ScanResult, ScanSignalId, ScanSignalResult,
    SignalSource, TestabilityFinding, family_of,
)
from sdlc.context.project import map_digest, project
from sdlc.measurement import CollectionState, Measurement


def _row(sid: ScanSignalId, ok: bool = True) -> ScanSignalResult:
    m = (Measurement.measured(1.0) if ok
         else Measurement.not_collected(f"{sid.value} could not run"))
    return ScanSignalResult(signal=sid, family=family_of(sid), version=1,
                            source=SignalSource.COMPUTED, collected=m,
                            categories={k: m for k in CATEGORIES[sid]})


def _scan(*, s5_ok=True, qs2_ok=True, qs3_ok=True, candidates=None,
          testability=(), coverage=()) -> ScanResult:
    ok = {ScanSignalId.S5: s5_ok, ScanSignalId.QS2: qs2_ok,
          ScanSignalId.QS3: qs3_ok}
    return ScanResult(
        signals=[_row(sid, ok.get(sid, True)) for sid in SCAN_ORDER],
        candidates=list(candidates or []),
        testability=list(testability), coverage=list(coverage))


def _candidate(cid="C-01", name="payments") -> ScanCandidate:
    return ScanCandidate(
        candidate_id=cid, name=name, sources=["S1-1"],
        confidence=Confidence.LOW,
        members=[
            CandidateMember(kind=MemberKind.HTTP_ROUTE,
                            value="POST /api/payments",
                            path="src/payments/api.py", line=12),
            CandidateMember(kind=MemberKind.FILE_PATH,
                            value="src/payments/store.py",
                            path="src/payments/store.py"),
        ])


def test_modules_come_from_the_merged_candidates():
    m = project(_scan(candidates=[_candidate()]), "tree1", "c" * 40)
    assert [x.name for x in m.modules] == ["payments"]
    assert m.modules[0].member_paths == ("src/payments/api.py",
                                         "src/payments/store.py")
    assert m.collected.state is CollectionState.MEASURED


def test_contracts_are_the_externally_reachable_members_only():
    """CONTRACT_KINDS: a route is a contract, a file path is not."""
    m = project(_scan(candidates=[_candidate()]), "tree1", "c" * 40)
    assert [c.value for c in m.contracts] == ["POST /api/payments"]
    assert m.contracts[0].path == "src/payments/api.py"
    assert m.contracts[0].line == 12


def test_s5_not_collected_yields_an_empty_map_that_says_why():
    """FR-915: an empty module list must not read as "no modules"."""
    m = project(_scan(s5_ok=False), "tree1", "c" * 40)
    assert m.modules == ()
    assert m.modules_collected.state is CollectionState.NOT_COLLECTED
    assert "S5" in m.modules_collected.reason
    assert m.collected.state is CollectionState.NOT_COLLECTED


def test_hot_spots_carry_their_source():
    finding = TestabilityFinding(
        severity="blocks", pattern="static-clock-access",
        detail="reads the wall clock directly",
        recommended_seam="inject a clock", path="src/payments/api.py", line=9)
    record = CoverageRecord(scope="file", path="src/payments/store.py",
                            covered=Measurement.measured(12.0),
                            source="report", tool="cobertura",
                            confidence=Confidence.HIGH)
    m = project(_scan(candidates=[_candidate()], testability=[finding],
                      coverage=[record]), "tree1", "c" * 40)
    assert {h.source for h in m.hot_spots} == {"testability", "coverage"}
    assert m.hot_spots_collected.state is CollectionState.MEASURED


def test_hot_spots_not_collected_when_neither_contributor_ran():
    m = project(_scan(candidates=[_candidate()], qs2_ok=False, qs3_ok=False),
                "tree1", "c" * 40)
    assert m.hot_spots == ()
    assert m.hot_spots_collected.state is CollectionState.NOT_COLLECTED
    assert "QS2" in m.hot_spots_collected.reason
    assert "QS3" in m.hot_spots_collected.reason


def test_a_partial_contributor_still_measures_and_stays_inspectable():
    """QS3 ran, QS2 did not: hot spots exist, and each record's `source`
    is what makes the partiality visible rather than hidden."""
    finding = TestabilityFinding(
        severity="smell", pattern="p", detail="d", recommended_seam="s",
        path="src/a.py")
    m = project(_scan(candidates=[_candidate()], testability=[finding],
                      qs2_ok=False), "tree1", "c" * 40)
    assert [h.source for h in m.hot_spots] == ["testability"]
    assert m.hot_spots_collected.state is CollectionState.MEASURED


def test_projection_is_order_independent():
    """NFR-10: byte-identical whatever order the records arrive in."""
    cands = [_candidate("C-01", "payments"), _candidate("C-02", "orders")]
    findings = [
        TestabilityFinding(severity="smell", pattern=f"p{i}", detail="d",
                           recommended_seam="s", path=f"src/{i}.py")
        for i in range(4)]
    first = project(_scan(candidates=cands, testability=findings),
                    "tree1", "c" * 40).model_dump_json()
    for _ in range(5):
        c, f = cands[:], findings[:]
        random.shuffle(c)
        random.shuffle(f)
        assert project(_scan(candidates=c, testability=f),
                       "tree1", "c" * 40).model_dump_json() == first


def test_the_digest_moves_with_content_and_not_with_order():
    cands = [_candidate("C-01", "payments"), _candidate("C-02", "orders")]
    a = map_digest(project(_scan(candidates=cands), "tree1", "c" * 40))
    b = map_digest(project(_scan(candidates=cands[::-1]), "tree1", "c" * 40))
    c = map_digest(project(_scan(candidates=[_candidate("C-01", "billing")]),
                           "tree1", "c" * 40))
    assert a == b
    assert a != c


def test_degraded_s5_with_measured_testability_does_not_raise():
    """Finding 3: when S5 degrades but QS3 measured, project() must return
    an unmeasured CodebaseMap with empty payloads rather than raising
    ValueError via CodebaseMap._unmeasured_carries_no_payload."""
    findings = [
        TestabilityFinding(severity="smell", pattern="p", detail="d",
                           recommended_seam="s", path="src/a.py")]
    scan = _scan(s5_ok=False, testability=findings)
    m = project(scan, "tree1", "c" * 40)
    assert m.collected.state is CollectionState.NOT_COLLECTED
    assert m.modules == ()
    assert m.contracts == ()
    assert m.hot_spots == ()
