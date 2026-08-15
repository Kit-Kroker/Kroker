# tests/test_discover_baseline.py
"""FR-913 (E-48 DD6): the disposition code computes before any model runs."""
from __future__ import annotations

from sdlc.assessment.discover.apply import baseline, baseline_dispositions
from sdlc.assessment.discover.map import (
    DiscoverAction, DiscoverContext, DispositionSource, CandidateContext,
    GraphSummary,
)
from sdlc.assessment.scan.models import CandidateMember, Confidence, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
GRAPH = GraphSummary(parsed=4, unparsed=0, edges=3,
                     unresolved_relative_rate=Measurement.measured(0.0))


def _ctx(candidate_id="C-01", **kw):
    base = dict(
        candidate_id=candidate_id, name="payments", confidence=Confidence.HIGH,
        sources=("S3-payments",), source_rules=("s3_http_route",),
        members=(CandidateMember(kind=MemberKind.HTTP_ROUTE,
                                 value="POST /pay", path="pay/api.py"),),
        member_paths=("pay/api.py",),
        cohesion=MEASURED, coupling=MEASURED, guardrail_only=False)
    return CandidateContext(**(base | kw))


def _layer(candidate_id="C-02", **kw):
    return _ctx(candidate_id, name="services",
                source_rules=("s1_layer_name",), guardrail_only=True, **kw)


def test_a_layer_named_candidate_is_de_scoped():
    """Clause D2's guardrail, computed rather than asked: delivery channels
    and deployment boundaries are not capabilities."""
    d = baseline(_layer())
    assert d.action is DiscoverAction.DE_SCOPE
    assert d.rule == "baseline_guardrail"


def test_a_possible_duplicate_is_flagged():
    """The honest limit of code: S5 detects the overlap, but only judgment
    decides MERGE versus genuinely-distinct."""
    d = baseline(_ctx(possible_duplicate_of=("C-02",)))
    assert d.action is DiscoverAction.FLAG
    assert d.rule == "baseline_possible_duplicate"


def test_everything_else_is_confirmed():
    d = baseline(_ctx())
    assert d.action is DiscoverAction.CONFIRM
    assert d.rule == "baseline_confirm"


def test_the_guardrail_outranks_the_duplicate_flag():
    """P2-D1: DD6's table is read top to bottom. A candidate named like a
    layer is not a capability whichever other candidate it overlaps, and
    FLAGging it would ask a human to adjudicate a boundary D2 rejects."""
    d = baseline(_layer(possible_duplicate_of=("C-01",)))
    assert d.action is DiscoverAction.DE_SCOPE


def test_a_baseline_names_its_rule_and_carries_no_rationale():
    """A baseline's rule IS its rationale; only a model verdict owes one."""
    d = baseline(_ctx())
    assert d.source is DispositionSource.BASELINE
    assert d.rationale == ""


def test_one_disposition_per_candidate_in_candidate_order():
    ctx = DiscoverContext(candidates=(_ctx(), _layer()), graph=GRAPH,
                          collected=Measurement.measured(2.0))
    got = baseline_dispositions(ctx)
    assert [d.candidate_id for d in got] == ["C-01", "C-02"]
    assert [d.action for d in got] == [DiscoverAction.CONFIRM,
                                       DiscoverAction.DE_SCOPE]
