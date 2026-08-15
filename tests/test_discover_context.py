"""FR-913 (E-48): assembling the proposer's packet from a ScanResult."""
from __future__ import annotations

import random

from sdlc.assessment.discover.context import build_context, entry_point_paths
from sdlc.assessment.scan.models import (
    CATEGORIES, SCAN_ORDER, CandidateMember, Confidence, MemberKind,
    ScanCandidate, ScanResult, ScanSignalResult, SecurityObservation,
    SignalSource, SourceCandidate, family_of,
)
from sdlc.measurement import CollectionState, Measurement

PAY = ScanCandidate(
    candidate_id="C-01", name="payments", sources=["S1-payments",
                                                   "S3-payments"],
    confidence=Confidence.MEDIUM,
    members=[CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay",
                             path="pay/api.py", line=10),
             CandidateMember(kind=MemberKind.FILE_PATH, value="pay/core.py",
                             path="pay/core.py")])
UTIL = ScanCandidate(
    candidate_id="C-02", name="services", sources=["S1-services"],
    confidence=Confidence.LOW,
    members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="services",
                             path="services/__init__.py")])

SOURCES = [
    SourceCandidate(signal="S1", local_id="S1-payments", name="payments",
                    rule="s1_domain_term", detail="", 
                    confidence_contribution=Confidence.HIGH,
                    members=[CandidateMember(kind=MemberKind.PACKAGE_PATH,
                                             value="pay")]),
    SourceCandidate(signal="S3", local_id="S3-payments", name="payments",
                    rule="s3_http_route", detail="",
                    confidence_contribution=Confidence.HIGH,
                    members=[CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                             value="POST /pay",
                                             path="pay/api.py", line=10)]),
    SourceCandidate(signal="S1", local_id="S1-services", name="services",
                    rule="s1_layer_name", detail="",
                    confidence_contribution=Confidence.LOW,
                    members=[CandidateMember(kind=MemberKind.PACKAGE_PATH,
                                             value="services")]),
]

INVENTORY = {
    "pay/api.py": "from pay.core import charge\n",
    "pay/core.py": "def charge(): pass\n",
    "services/__init__.py": "from pay.core import charge\n",
}


def _signals() -> list[ScanSignalResult]:
    """All thirteen rows, MEASURED.

    ScanResult is stricter than it looks: `_signals_are_the_whole_set`
    requires every signal in SCAN_ORDER, and `_unmeasured_carries_no_payload`
    forbids a payload whose owning signal did not collect. `signals=[]` does
    not construct.
    """
    val = Measurement.measured(0.0)
    return [ScanSignalResult(signal=s, family=family_of(s), version=1,
                             source=SignalSource.COMPUTED, collected=val,
                             categories={k: val for k in CATEGORIES[s]})
            for s in SCAN_ORDER]


def _scan(**kw) -> ScanResult:
    base = dict(signals=_signals(), sources=SOURCES, candidates=[PAY, UTIL])
    return ScanResult(**(base | kw))


def test_the_packet_carries_one_context_per_candidate():
    ctx = build_context(_scan(), INVENTORY, [])
    assert [c.candidate_id for c in ctx.candidates] == ["C-01", "C-02"]


def test_source_rules_come_from_the_source_candidates():
    ctx = build_context(_scan(), INVENTORY, [])
    pay = ctx.candidates[0]
    assert set(pay.source_rules) == {"s1_domain_term", "s3_http_route"}


def test_a_layer_named_candidate_is_flagged_guardrail_only():
    """DD6's input: 'services' is supported only by s1_layer_name."""
    ctx = build_context(_scan(), INVENTORY, [])
    by_id = {c.candidate_id: c for c in ctx.candidates}
    assert by_id["C-02"].guardrail_only is True
    assert by_id["C-01"].guardrail_only is False


def test_security_observations_join_on_member_paths():
    obs = SecurityObservation(
        signal="SS1", category="tls_enforcement", rule="plaintext_http",
        detail="", severity_hint="medium", path="pay/api.py",
        confidence=Confidence.MEDIUM)
    ctx = build_context(_scan(security=[obs]), INVENTORY, [])
    by_id = {c.candidate_id: c for c in ctx.candidates}
    assert len(by_id["C-01"].security) == 1
    assert by_id["C-02"].security == ()


def test_entry_point_paths_come_from_s3_and_s4_members():
    assert entry_point_paths(_scan()) == ("pay/api.py",)


def test_no_candidates_is_a_measured_zero_not_a_failure():
    ctx = build_context(_scan(candidates=[]), INVENTORY, [])
    assert ctx.collected.state is CollectionState.MEASURED
    assert ctx.collected.value == 0.0
    assert ctx.candidates == ()


def test_skipped_blobs_are_carried_not_dropped():
    """The E-46 review's rule: a gap reported as a zero is the defect."""
    ctx = build_context(_scan(), INVENTORY, ["big/generated.py"])
    assert ctx.skipped == ("big/generated.py",)
    assert ctx.file_count == len(INVENTORY) + 1


def test_unresolvable_source_prevents_guardrail_only_flip():
    """Finding 1: if a source lookup misses, we cannot prove the candidate is
    supported *only* by layer rules. An unresolvable source must record the
    miss and keep guardrail_only=False."""
    cand = ScanCandidate(
        candidate_id="C-03", name="mixed",
        sources=["S1-services", "S3-missing"],
        confidence=Confidence.MEDIUM,
        members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="services",
                                 path="services/__init__.py")])
    ctx = build_context(_scan(candidates=[cand]), INVENTORY, [])
    mixed = ctx.candidates[0]
    assert "unresolved" in mixed.source_rules
    assert mixed.guardrail_only is False


def test_the_packet_is_order_independent():
    """NFR-10: byte-identical regardless of input ordering."""
    first = build_context(_scan(), INVENTORY, []).model_dump_json()
    for _ in range(5):
        cands = [PAY, UTIL]
        srcs = SOURCES[:]
        random.shuffle(cands)
        random.shuffle(srcs)
        items = list(INVENTORY.items())
        random.shuffle(items)
        again = build_context(_scan(candidates=cands, sources=srcs),
                              dict(items), [])
        assert again.model_dump_json() == first
