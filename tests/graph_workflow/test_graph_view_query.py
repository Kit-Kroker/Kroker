# tests/graph_workflow/test_graph_view_query.py
"""E-75 spec §4.2: graph_view on a SANDBOXED GraphWorkflow (catches the
pydantic class-duplication fingerprint), attribution through real hosts, and
command neutrality against the E-74 golden."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from temporalio import activity

from sdlc.benchmarks.models import BenchmarkRecord
from sdlc.core.models import RunState, RunSummary
from sdlc.graph import GraphRunView
from sdlc.notify.contract import NotifyInput, Results
from sdlc.workflows.graph_catalog import build_run_input
from tests.fakes.canned import e2e_config
from tests.replay.harness import GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import (
    QUESTION_IDS,
    SCENARIOS,
    A,
    V,
    answer_clarify,
    decide,
    wait_for,
)

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


async def _view(handle) -> GraphRunView | None:
    raw = await handle.query("graph_view")
    return None if raw is None else GraphRunView.model_validate(raw)


@pytest.mark.asyncio
async def test_graph_view_attributes_and_projects_on_a_sandboxed_run(monkeypatch, tmp_path):
    observed: dict = {}

    async def drive(handle, env):
        await wait_for(handle, "awaiting:clarify")
        observed["clarify"] = await _view(handle)
        await answer_clarify(handle)
        await wait_for(handle, "awaiting:architecture")
        observed["arch"] = await _view(handle)
        observed["state"] = RunState.model_validate(await handle.query("run_state"))
        for gate in ("architecture", "plan", "deploy"):
            await decide(handle, gate, 1, A)
        for _ in range(600):
            v = await _view(handle)
            if v is not None and v.result is not None:
                observed["final"] = v
                break
            await asyncio.sleep(0.05)

    scenario = dataclasses.replace(GREENFIELD, name="graph_view_query", drive=drive)
    captured = await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)

    clarify = observed["clarify"]
    by_key = {p.key: p for p in clarify.pending}
    for qid in QUESTION_IDS:
        assert by_key[qid].activation_id == "clarify#1" and by_key[qid].kind == "clarify"

    arch = observed["arch"]
    assert {p.key: p.activation_id for p in arch.pending} == {"architecture#1": "architecture#1"}
    assert arch.state.nodes["architecture"].status == "running"
    assert arch.result is None
    assert len(arch.graph_sha) == 64

    marks = observed["state"].stage_marks
    assert marks is not None
    assert marks["intake"] == "done"
    assert marks["context"] == "skipped"
    assert marks["architecture"] == "blocked"

    final = observed["final"]
    assert final.state.outcome == "completed"
    assert final.result is not None and final.result.startswith("deployed")
    assert all(f.ended_at is not None for f in final.activations.values())

    golden = load_golden("greenfield_happy")
    assert captured.golden["commands"] == golden["commands"], "SG-1: command projection differs"
    assert captured.golden["close"] == golden["close"]


def test_result_is_published_only_after_retro():
    """Spec F3: the retro window (router completed, execution open) must read
    result=None. The live window is too short to poll reliably, so the
    ordering is pinned on the source."""
    import inspect

    from sdlc.workflows.graph import GraphWorkflow

    src = inspect.getsource(GraphWorkflow.run)
    assert src.index("await self._retro(") < src.index("self._result = result")
    assert src.count("self._result =") == 1


# ---------------------------------------------------------------------------
# E-77 T019: a default-graph run records its graph_sha everywhere (FR-008/009/010).
# ---------------------------------------------------------------------------

_CAPTURED_RECORDS: list = []


@activity.defn(name="record_benchmark")
async def _capture_record(record: BenchmarkRecord) -> None:
    """Test double for the recorder activity: capture instead of persist, so
    the records the workflow scheduled via BenchmarkHost._record can be read
    (cfg.benchmark.case_id is what turns _record into a record_benchmark call)."""
    _CAPTURED_RECORDS.append(record)


@activity.defn(name="notify")
async def _noop_notify(inp: NotifyInput) -> Results:
    """GateHost schedules notification deliveries (workflows/gates.py); the
    real worker registers sdlc.notify.activities.notify. Deliver nothing."""
    return Results(results=[])


@pytest.mark.asyncio
async def test_graph_sha_is_stamped_on_state_summary_and_every_record(monkeypatch, tmp_path):
    observed: dict = {}

    async def drive(handle, env):
        await answer_clarify(handle)
        await decide(handle, "architecture", 1, V, guidance="split the service")
        await decide(handle, "architecture", 2, A)  # revised once, then through
        await decide(handle, "plan", 1, A)
        await decide(handle, "deploy", 1, A)
        await handle.result()
        observed["state"] = RunState.model_validate(await handle.query("run_state"))
        observed["summary"] = RunSummary.model_validate(await handle.query("run_summary"))

    cfg = e2e_config()
    cfg.deploy.enabled = True
    cfg.benchmark.case_id = "add-login"  # BenchmarkHost._record schedules record_benchmark
    cfg.benchmark.bench_run_id = "b1"
    scenario = dataclasses.replace(
        GREENFIELD,
        name="graph_sha_stamped",
        cfg=lambda: cfg,
        activities=lambda: [*GREENFIELD.activities(), _capture_record, _noop_notify],
        drive=drive,
    )
    # The sha the run must name is the start input graph's content hash (R-1).
    expected = build_run_input(GREENFIELD.idea(), cfg, GREENFIELD.seeded()).graph.content_sha()

    _CAPTURED_RECORDS.clear()
    await capture(scenario, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)

    assert observed["state"].graph_sha == expected
    assert observed["summary"].graph_sha == expected

    assert _CAPTURED_RECORDS, "no benchmark records were captured"
    for record in _CAPTURED_RECORDS:
        assert record.graph is not None, record.stage
        assert record.graph.graph_sha == expected

    # Gated-stage records are emitted POST-GATE (gate_node returns on revise
    # before finish), so the architecture stage's one record carries the gate's
    # approve-round activation -- round 2, after the revise loop re-entered the
    # architect -- while every other stage's records carry round 1.
    dump = [
        (r.stage, r.graph.activation_id, r.graph.node_id, r.graph.round) for r in _CAPTURED_RECORDS
    ]
    arch = [r for r in _CAPTURED_RECORDS if r.stage == "architecture"]
    assert len(arch) == 1, dump
    a = arch[0].graph
    assert (a.activation_id, a.node_id, a.round) == ("architecture#2", "architecture", 2)
    assert a.node_stage == "architecture"
    others = [r for r in _CAPTURED_RECORDS if r.stage != "architecture"]
    assert others and all(r.graph.round == 1 for r in others), dump
    # lens records keep their own stage while attributed to the code node (G2)
    lens_node = {r.stage: r.graph.node_id for r in others}
    assert lens_node["review"] == "code" and lens_node["qa"] == "code"
