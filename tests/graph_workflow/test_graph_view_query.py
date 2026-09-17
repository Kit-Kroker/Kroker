# tests/graph_workflow/test_graph_view_query.py
"""E-75 spec §4.2: graph_view on a SANDBOXED GraphWorkflow (catches the
pydantic class-duplication fingerprint), attribution through real hosts, and
command neutrality against the E-74 golden."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from sdlc.core.models import RunState
from sdlc.graph import GraphRunView
from tests.replay.harness import GRAPH_STARTER, capture, load_golden
from tests.replay.scenarios import (
    QUESTION_IDS,
    SCENARIOS,
    A,
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
