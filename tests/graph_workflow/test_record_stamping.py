# tests/graph_workflow/test_record_stamping.py
"""E-77 T015 (RED): GraphWorkflow._stamp -- graph attribution on every record.

Pure unit tests, no Temporal: a GraphWorkflow is built directly, `_graph_sha`
is set and a stub dispatcher installed carrying `_attrib` entries (the T014
API: dict[aid -> ActivationAttrib(node_id, round, node_stage, fail_reentry)]),
then `_stamp` is driven with the ACTIVATION contextvar set or unset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    GraphAttribution,
    QualityScore,
    SpeedBag,
)
from sdlc.graph.run_view import ACTIVATION
from sdlc.workflows.graph import GraphWorkflow

SHA = "a" * 64


@dataclass
class _Attrib:
    """The T014 ActivationAttrib shape, duck-typed so these tests stay pure
    unit tests while T014 is still red."""

    node_id: str
    round: int
    node_stage: str
    fail_reentry: int | None


class _StubDispatcher:
    def __init__(self, attribs: dict[str, _Attrib]) -> None:
        self._attrib = dict(attribs)


def _record(stage: str = "code") -> BenchmarkRecord:
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id="add-login",
        scope=BenchmarkScope.STAGE,
        stage=stage,
        role="dev",
        model="zai-coding-plan/glm-5.2",
        prompt_sha="abc",
        quality=QualityScore(score=0.8, judge="llm_judge"),
        cost=CostBag(usd=0.1, input_tokens=100, output_tokens=50),
        speed=SpeedBag(
            wall_clock_s=12.0,
            started_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
            ended_at=datetime(2026, 9, 19, 10, 0, 12, tzinfo=UTC),
        ),
        outcome=BenchmarkOutcome.PASS,
    )


def _workflow(attribs: dict[str, _Attrib]) -> GraphWorkflow:
    wf = GraphWorkflow()
    wf._graph_sha = SHA
    wf._dispatcher = _StubDispatcher(attribs)
    return wf


def test_inside_an_activation_the_record_carries_the_full_attribution():
    """FR-010/FR-014: inside an activation, record.graph is the GraphAttribution
    assembled from _graph_sha and the dispatcher's _attrib entry -- and nothing
    else on the record changes."""
    wf = _workflow({"code_1#2": _Attrib("code_1", 2, "code", 1)})
    rec = _record(stage="code")
    expected = GraphAttribution(
        graph_sha=SHA,
        activation_id="code_1#2",
        node_id="code_1",
        round=2,
        node_stage="code",
        fail_reentry=1,
    )
    token = ACTIVATION.set("code_1#2")
    try:
        stamped = wf._stamp(rec)
    finally:
        ACTIVATION.reset(token)
    assert stamped.graph == expected
    assert stamped == rec.model_copy(update={"graph": expected})


def test_outside_any_activation_only_graph_sha_is_recorded():
    """Retro/preamble records (ACTIVATION unset): graph_sha only, every
    activation field None (FR-024; the GraphAttribution invariant)."""
    wf = _workflow({"code_1#1": _Attrib("code_1", 1, "code", None)})
    assert ACTIVATION.get() is None  # nothing leaked into this test
    stamped = wf._stamp(_record(stage="retro"))
    assert stamped.graph == GraphAttribution(graph_sha=SHA)


def test_an_activation_id_missing_from_attrib_records_only_graph_sha():
    """A cancelled/invalidated activation's aid may be gone from _attrib; the
    record still gets its run's graph, never a fabricated attribution."""
    wf = _workflow({})
    token = ACTIVATION.set("ghost#7")
    try:
        stamped = wf._stamp(_record())
    finally:
        ACTIVATION.reset(token)
    assert stamped.graph == GraphAttribution(graph_sha=SHA)


@pytest.mark.parametrize("stage", ["code", "qa", "review", "adversary", "handoff", "deep_review"])
def test_mapped_node_keeps_the_handler_or_lens_stage(stage):
    """G2: only `unknown` rewrites; a mapped node's handler stage and its lens
    records' stages are kept even though they differ from the node's stage."""
    wf = _workflow({"code_1#1": _Attrib("code_1", 1, "code", None)})
    rec = _record(stage=stage)
    token = ACTIVATION.set("code_1#1")
    try:
        stamped = wf._stamp(rec)
    finally:
        ACTIVATION.reset(token)
    assert stamped.stage == stage
    assert stamped.graph is not None and stamped.graph.node_stage == "code"


def test_unknown_node_stage_rewrites_the_record_stage():
    """G2: records produced inside an activation resolving to `unknown` carry
    stage `unknown` -- never the handler's own stage."""
    wf = _workflow({"custom_1#1": _Attrib("custom_1", 1, "unknown", None)})
    rec = _record(stage="code")  # the handler emitted under its own stage
    token = ACTIVATION.set("custom_1#1")
    try:
        stamped = wf._stamp(rec)
    finally:
        ACTIVATION.reset(token)
    assert stamped.stage == "unknown"
    assert stamped.graph is not None and stamped.graph.node_stage == "unknown"


def test_stamp_never_mutates_its_input():
    """_stamp returns a stamped copy; the input record is untouched."""
    wf = _workflow({"custom_1#3": _Attrib("custom_1", 3, "unknown", 1)})
    rec = _record(stage="code")
    before = rec.model_copy(deep=True)
    token = ACTIVATION.set("custom_1#3")
    try:
        stamped = wf._stamp(rec)
    finally:
        ACTIVATION.reset(token)
    assert rec == before
    assert rec.graph is None
    assert stamped is not rec
