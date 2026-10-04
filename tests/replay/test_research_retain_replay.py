"""Replay proof for the research retain path (009, plan D3): a committed
history of a research run with grounded findings and memory on replays with
its page files present, absent and overwritten — after the fix. On
unmodified source the `absent` and `overwritten` rows fail with a
nondeterminism error (the workflow re-verifies from page files); that red
output is kept as `.workspace/tmp/009-red.txt`.

The capture test (bottom) runs ONCE, before any edit under `src/`, behind
its own switch `SDLC_CAPTURE_RESEARCH_RETAIN`. It never listens to
`SDLC_CAPTURE_HISTORIES` (which would re-record every existing fixture) and
never runs again after the source change.
"""

from __future__ import annotations

import json
import os

import pytest
from temporalio.api.enums.v1 import EventType
from temporalio.contrib.pydantic import pydantic_data_converter

from sdlc.memory.activities import RetainInput
from sdlc.stages.research import verify
from tests.replay.harness import (
    FEATURE_STARTER,
    HISTORIES,
    capture,
    load_history,
    source_commit,
)
from tests.replay.projection import command_projection
from tests.replay.research_retain import NAME, SCENARIO, stage_pages
from tests.replay.test_feature_replay import replayer


@pytest.mark.temporal
@pytest.mark.skipif(
    os.environ.get("SDLC_CAPTURE_RESEARCH_RETAIN") != "1",
    reason="fixture capture runs once, from unmodified source (009 T002)",
)
@pytest.mark.asyncio
async def test_capture_research_retain_history(monkeypatch, tmp_path):
    first = await capture(SCENARIO, FEATURE_STARTER, monkeypatch, tmp_path / "a", sandboxed=True)
    second = await capture(SCENARIO, FEATURE_STARTER, monkeypatch, tmp_path / "b", sandboxed=True)
    assert first.golden["commands"] == second.golden["commands"], "SG-3: unstable commands"
    HISTORIES.mkdir(exist_ok=True)
    (HISTORIES / f"{NAME}.json").write_text(
        json.dumps(
            {
                "workflow_id": first.workflow_id,
                "workflow": FEATURE_STARTER.name,
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
@pytest.mark.parametrize("how", ["present", "absent", "overwritten"])
async def test_retain_decisions_do_not_depend_on_page_files(how, monkeypatch, tmp_path):
    """FR-007, SC-001, SC-002: the committed history replays whatever became
    of the run's page files. On unmodified source the `absent` and
    `overwritten` rows fail with a nondeterminism error (the workflow
    re-verifies from disk inside the retain path); that red output is the
    SC-001 evidence in `.workspace/tmp/009-red.txt`."""
    history = load_history(NAME)
    monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))
    stage_pages(history.workflow_id, how)
    if how == "absent":
        assert not verify.pages_dir(history.workflow_id).exists()
    result = await replayer().replay_workflow(history, raise_on_replay_failure=True)
    assert result.replay_failure is None


def test_fixture_holds_the_grounded_retain_path():
    """PIN (SG-3): the fixture is one research run with the grounded retain
    path — one verify, one sub-question, three retains (a gate feedback then
    one finding each) — captured from `FeatureWorkflow` at a commit whose
    `src/` equals main `d51eef5`. Never re-record the fixture to change it."""
    history = load_history(NAME)
    commands = command_projection(history)
    assert commands.count("activity:verify_brief_activity") == 1
    assert commands.count("activity:research_subquestion") == 1
    assert commands.count("activity:retain") == 3

    kinds = []
    for event in history.events:
        if event.event_type != EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            continue
        attrs = event.activity_task_scheduled_event_attributes
        if attrs.activity_type.name == "retain":
            (inp,) = pydantic_data_converter.payload_converter.from_payloads(
                list(attrs.input.payloads), [RetainInput]
            )
            kinds.append(inp.item.kind)
    assert kinds == ["gate_feedback", "research_finding", "research_finding"]

    fixture = json.loads((HISTORIES / f"{NAME}.json").read_text(encoding="utf-8"))
    assert len(fixture["source_commit"]) == 40
    assert fixture["workflow"] == "FeatureWorkflow"
