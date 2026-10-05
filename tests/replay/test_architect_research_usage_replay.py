"""Replay proof for the architect research surface (C12, plan D5): the
committed `architect_research_usage` history replays under GraphWorkflow and
holds exactly one research `price_usage` — the harvest's pricing command —
besides the architect's own.

The capture test runs ONCE, after the harvest is green (T010), behind its own
switch `SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE`; it never listens to
`SDLC_CAPTURE_HISTORIES` and never writes golden files. Test 4 is the
committed negative control: the same identification rule applied to the
report-less `architect_research_tool` history must find no research
`price_usage` — the shape pin's teeth (the uncommitted base-commit control
backs it once)."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.contrib.pydantic import pydantic_data_converter

from sdlc.pricing import PriceUsageInput
from tests.replay.architect_research_usage import NAME, REPORT, SCENARIO
from tests.replay.harness import (
    GRAPH_STARTER,
    HISTORIES,
    capture,
    load_history,
    source_commit,
)
from tests.replay.test_feature_replay import replayer


def _scheduled(history) -> list[tuple[str, Any]]:
    """Every activity-task-scheduled event as (activity name, event), in
    schedule order."""
    return [
        (event.activity_task_scheduled_event_attributes.activity_type.name, event)
        for event in history.events
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]


def _decode_price_usage(event) -> PriceUsageInput:
    """Decode one scheduled `price_usage` input (the 009 decode pattern)."""
    attrs = event.activity_task_scheduled_event_attributes
    (inp,) = pydantic_data_converter.payload_converter.from_payloads(
        list(attrs.input.payloads), [PriceUsageInput]
    )
    return inp


def _fields(inp: PriceUsageInput) -> tuple:
    return (
        inp.model,
        inp.input_tokens,
        inp.output_tokens,
        inp.cache_read_tokens,
        inp.cache_write_tokens,
    )


def _harvest_pair(history) -> tuple[PriceUsageInput | None, PriceUsageInput | None]:
    """The plan's identification rule (every fake shares one model label, so
    the model id cannot pick the architect's): walking the scheduled
    activities in order, the architect's own `price_usage` is the FIRST
    `price_usage` scheduled after the architect agent's FINAL
    `agent__architect_agent__model_request`; the research one is the
    `price_usage` scheduled IMMEDIATELY after it — adjacency is what
    separates the harvest from a later stage's own pricing. Returns
    (architect_own, research_or_None)."""
    names = _scheduled(history)
    final_arch = max(
        (
            i
            for i, (name, _event) in enumerate(names)
            if name.startswith("agent__architect_agent__") and name.endswith("__model_request")
        ),
        default=-1,
    )
    assert final_arch >= 0, "the history schedules no architect model_request"
    price_indices = [
        i for i, (name, _event) in enumerate(names) if i > final_arch and name == "price_usage"
    ]
    if not price_indices:
        return None, None
    own_index = price_indices[0]
    architect_own = _decode_price_usage(names[own_index][1])
    research = None
    if own_index + 1 < len(names) and names[own_index + 1][0] == "price_usage":
        research = _decode_price_usage(names[own_index + 1][1])
    return architect_own, research


@pytest.mark.asyncio
async def test_report_carrying_history_replays():
    """The committed with-report history replays under the graph workflows
    with no replay failure."""
    history = load_history(NAME)
    result = await replayer(*GRAPH_STARTER.workflows).replay_workflow(
        history, raise_on_replay_failure=True
    )
    assert result.replay_failure is None


def test_fixture_holds_the_harvest():
    """PIN: the fixture is one architect round whose harvest priced the
    report — the research `price_usage` after the architect's own carries
    exactly REPORT's model and four counts, the architect's own does not,
    exactly ONE `price_usage` in the whole history equals REPORT, and the
    file names GraphWorkflow at a 40-character source commit. Never
    re-record the fixture to change it."""
    history = load_history(NAME)
    architect_own, research = _harvest_pair(history)
    assert research is not None, "the harvest's price_usage must follow the architect's own"
    assert _fields(research) == _fields(REPORT)
    assert architect_own is not None
    assert _fields(architect_own) != _fields(REPORT)

    all_prices = [
        _decode_price_usage(event) for name, event in _scheduled(history) if name == "price_usage"
    ]
    assert sum(1 for p in all_prices if _fields(p) == _fields(REPORT)) == 1, (
        "across the whole history exactly one price_usage input equals REPORT"
    )

    fixture = json.loads((HISTORIES / f"{NAME}.json").read_text(encoding="utf-8"))
    assert len(fixture["source_commit"]) == 40
    assert fixture["workflow"] == "GraphWorkflow"


@pytest.mark.temporal
@pytest.mark.skipif(
    os.environ.get("SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE") != "1",
    reason="fixture capture runs once, after the harvest is green (C12 T011)",
)
@pytest.mark.asyncio
async def test_capture_architect_research_usage_history(monkeypatch, tmp_path):
    """Capture the with-report history ONCE (never `SDLC_CAPTURE_HISTORIES`,
    never a golden file, never `write_fixtures`): two captures must agree on
    the command projection (SG-6), and only the history file is written."""
    first = await capture(SCENARIO, GRAPH_STARTER, monkeypatch, tmp_path / "a", sandboxed=True)
    second = await capture(SCENARIO, GRAPH_STARTER, monkeypatch, tmp_path / "b", sandboxed=True)
    assert first.golden["commands"] == second.golden["commands"], (
        "SG-6: the double capture must agree on the command projection"
    )
    HISTORIES.mkdir(exist_ok=True)
    (HISTORIES / f"{NAME}.json").write_text(
        json.dumps(
            {
                "workflow_id": first.workflow_id,
                "workflow": GRAPH_STARTER.name,
                "source_commit": source_commit(),
                "history": json.loads(first.history.to_json()),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_pin_rejects_an_unharvested_history():
    """PIN — the committed negative control: applying the SAME identification
    rule to the report-less `architect_research_tool` history finds the
    architect's own pricing but no research `price_usage` after it. Without
    this pin the harvest pin above could pass on any history."""
    architect_own, research = _harvest_pair(load_history("architect_research_tool"))
    assert architect_own is not None, "the report-less history still prices the architect itself"
    assert research is None, (
        "an unharvested history schedules no price_usage immediately after the "
        "architect's own — the shape pin has teeth"
    )
