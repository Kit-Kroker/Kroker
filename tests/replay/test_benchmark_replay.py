"""017 T002: BenchmarkWorkflow replays the single-cell graded execution (D-6).

020 T022 (R-1, plan T046): the replay-safe restart. The recorded parent wrote
an `e74-graph-child:` patch marker when it started its graph child. Once that
marker is retired (deprecate_patch, T023), a replay must still succeed with the
marker absent. test_replays_with_the_e74_marker_stripped pins that.
"""

from __future__ import annotations

import base64
import json

import pytest
from temporalio.client import WorkflowHistory

from sdlc.benchmarks.workflow import BenchmarkWorkflow
from tests.replay.harness import HISTORIES, load_history, replayer

pytestmark = pytest.mark.temporal

E74_PREFIX = "e74-graph-child:"


def _patch_id(event: dict) -> str | None:
    """The patch id of a core_patch marker event, or None for any other event."""
    if event.get("eventType") != "EVENT_TYPE_MARKER_RECORDED":
        return None
    attrs = event["markerRecordedEventAttributes"]
    if attrs.get("markerName") != "core_patch":
        return None
    payload = attrs["details"]["patch-data"]["payloads"][0]
    return json.loads(base64.b64decode(payload["data"]))["id"]


# Proto-JSON encodes int64 event ids as strings. These are the fields that
# reference another event by id (the set observed across benchmark_one_cell).
_EVENT_REF_KEYS = frozenset(
    {
        "eventId",
        "initiatedEventId",
        "scheduledEventId",
        "startedEventId",
        "workflowTaskCompletedEventId",
    }
)


def _renumber(events: list[dict]) -> None:
    """Make event ids consecutive again after a removal, and remap every
    reference to them. A reference to a removed event raises KeyError: the
    strip must never leave a dangling id behind."""
    mapping = {str(e["eventId"]): str(i) for i, e in enumerate(events, 1)}

    def fix(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _EVENT_REF_KEYS and value not in (None, "", "0", 0):
                    node[key] = mapping[str(value)]
                else:
                    fix(value)
        elif isinstance(node, list):
            for item in node:
                fix(item)

    for event in events:
        fix(event)


def _history_without_e74_markers() -> tuple[WorkflowHistory, int, int]:
    """(history, removed, surviving core_patch markers) for benchmark_one_cell
    with every e74-graph-child marker stripped, the remaining events renumbered
    consecutively, and the other core_patch markers left in place."""
    data = json.loads((HISTORIES / "benchmark_one_cell.json").read_text(encoding="utf-8"))
    events = data["history"]["events"]
    kept = [e for e in events if not (_patch_id(e) or "").startswith(E74_PREFIX)]
    removed = len(events) - len(kept)
    survivors = sum(1 for e in kept if _patch_id(e) is not None)
    _renumber(kept)
    data["history"]["events"] = kept
    history = WorkflowHistory.from_json(data["workflow_id"], json.dumps(data["history"]))
    return history, removed, survivors


@pytest.mark.asyncio
async def test_benchmark_workflow_replays_one_cell_history():
    result = await replayer(BenchmarkWorkflow).replay_workflow(
        load_history("benchmark_one_cell"), raise_on_replay_failure=True
    )
    assert result.replay_failure is None


@pytest.mark.asyncio
async def test_replays_with_the_e74_marker_stripped():
    """Replay-safe restart (020 R-1): the one-cell history carries a graph-child
    patch marker. With that marker stripped, the replay must still succeed."""
    stripped, removed, survivors = _history_without_e74_markers()
    assert removed >= 1, "the strip removed no e74-graph-child marker"
    assert survivors == 2, "the 012 and 015 core_patch markers must survive the strip"
    result = await replayer(BenchmarkWorkflow).replay_workflow(
        stripped, raise_on_replay_failure=True
    )
    assert result.replay_failure is None
