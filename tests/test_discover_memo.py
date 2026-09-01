# tests/test_discover_memo.py
"""FR-103 / FR-913 (E-48 DD10): the phase memo, and the terms it keys on."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover import memo
from sdlc.assessment.discover.map import (
    CandidateContext,
    CapabilityMap,
    DiscoverContext,
    GraphSummary,
    context_digest,
)
from sdlc.assessment.discover.models import (
    AttributionReport,
    DecompositionReport,
    FileBucket,
    OwnershipOutcome,
    OwnershipReport,
    ReferenceGraph,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement
from sdlc.memoization.cache import NO_PROPOSER, discover_key

GRAPH = GraphSummary(
    parsed=4, unparsed=0, edges=3, unresolved_relative_rate=Measurement.measured(0.0)
)
MAP = CapabilityMap(collected=Measurement.measured(0.0))
KEY = dict(
    project="acme",
    tree_hash="t" * 40,
    context_digest="d" * 64,
    prompt_sha=NO_PROPOSER,
    model=NO_PROPOSER,
)


@pytest.fixture(autouse=True)
def cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "memo"))


def _ctx(candidate_id="C-01") -> DiscoverContext:
    member = CandidateMember(kind=MemberKind.HTTP_ROUTE, value="POST /pay", path="pay/api.py")
    return DiscoverContext(
        candidates=(
            CandidateContext(
                candidate_id=candidate_id,
                name="payments",
                confidence=Confidence.HIGH,
                sources=("S3-payments",),
                source_rules=("s3_http_route",),
                members=(member,),
                member_paths=("pay/api.py",),
                cohesion=Measurement.measured(1.0),
                coupling=Measurement.measured(0.0),
                guardrail_only=False,
            ),
        ),
        graph=GRAPH,
        collected=Measurement.measured(1.0),
    )


def test_every_term_moves_the_key():
    """DD10 lists five terms plus the project. A term that does not move the
    key is a term that is not in it."""
    base = discover_key("acme", "t", "d", 1, "p", "m")
    assert base != discover_key("other", "t", "d", 1, "p", "m")
    assert base != discover_key("acme", "u", "d", 1, "p", "m")
    assert base != discover_key("acme", "t", "e", 1, "p", "m")
    assert base != discover_key("acme", "t", "d", 2, "p", "m")
    assert base != discover_key("acme", "t", "d", 1, "q", "m")
    assert base != discover_key("acme", "t", "d", 1, "p", "n")


def test_an_unchanged_tree_hits():
    assert memo.store(**KEY, registry_version=1, out=MAP) is True
    assert memo.load(**KEY, registry_version=1) is not None


def test_an_identity_write_invalidates():
    """E-47a's amendment to FR-103, and what makes skipping the lock on a hit
    safe: if the registry moved, the key moved."""
    memo.store(**KEY, registry_version=1, out=MAP)
    assert memo.load(**KEY, registry_version=2) is None


def test_a_prompt_or_model_change_invalidates():
    memo.store(**KEY, registry_version=1, out=MAP)
    assert memo.load(**{**KEY, "prompt_sha": "abc"}, registry_version=1) is None
    assert memo.load(**{**KEY, "model": "claude-x"}, registry_version=1) is None


def test_a_not_collected_map_is_never_stored():
    """scan/memo.py's rule verbatim in intent: never serve a failure
    forever."""
    failed = CapabilityMap(collected=Measurement.not_collected("S5 did not collect"))
    assert memo.store(**KEY, registry_version=1, out=failed) is False
    assert memo.load(**KEY, registry_version=1) is None


def test_corrupt_content_is_a_miss_not_a_crash():
    """A truncated cache file must cost a recompute, not an assessment."""
    from sdlc.memoization import cache

    cache.put(discover_key("acme", "t" * 40, "d" * 64, 1, NO_PROPOSER, NO_PROPOSER), "{not json")
    assert memo.load(**KEY, registry_version=1) is None


def test_the_context_digest_is_order_independent():
    """The digest inherits build_context's guarantee: DiscoverContext's
    model_dump_json is already asserted byte-identical across input order
    (test_discover_context.py), and this hashes exactly those bytes."""
    assert context_digest(_ctx()) == context_digest(_ctx())
    assert context_digest(_ctx()) != context_digest(_ctx("C-02"))


def test_the_sentinel_is_never_empty():
    """signal_key's rule: '' would make 'no model was involved'
    indistinguishable from a bug that dropped the model id (P2-D6)."""
    assert NO_PROPOSER
    assert NO_PROPOSER != ""


def test_a_map_with_degraded_sub_reports_is_never_stored():
    """scan/memo.py's rule 2: a transient finalize blip or git timeout must not
    freeze a permanently missing sub-report into the cache."""
    nc = Measurement.not_collected("git timeout")

    # Degraded attribution:
    map_attr_nc = CapabilityMap(
        collected=Measurement.measured(1.0),
        attribution=AttributionReport(
            counts={b: 0 for b in FileBucket},
            coverage=nc,
            meets_floor=False,
            graph=ReferenceGraph(unresolved_relative_rate=nc),
        ),
    )
    assert memo.store(**KEY, registry_version=1, out=map_attr_nc) is False

    # Degraded decomposition:
    map_decomp_nc = CapabilityMap(
        collected=Measurement.measured(1.0), decomposition=DecompositionReport(collected=nc)
    )
    assert memo.store(**KEY, registry_version=1, out=map_decomp_nc) is False

    # Degraded ownership:
    map_owner_nc = CapabilityMap(
        collected=Measurement.measured(1.0),
        ownership=OwnershipReport(counts={o: 0 for o in OwnershipOutcome}, collected=nc),
    )
    assert memo.store(**KEY, registry_version=1, out=map_owner_nc) is False
