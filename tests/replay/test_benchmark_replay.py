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


def _strip_change_versions(events: list[dict]) -> int:
    """Drop the e74-graph-child: patch from the TemporalChangeVersion stream.

    A patched() first-encounter issues TWO commands -- the core_patch marker
    and a change-version upsert -- and the strip removes both sides of the
    pair: an upsert event is DROPPED when, with the e74 entries removed, it
    carries no version the run did not already have (that upsert existed only
    to record e74); otherwise the event stays with the e74 entries deleted
    from its list (a later patch's upsert legitimately lists the versions
    known at that point -- in the counterfactual run it never knew e74).
    Returns the number of upsert events dropped."""
    dropped = 0
    running: set[str] = set()
    kept_events: list[dict] = []
    for event in events:
        if event.get("eventType") != "EVENT_TYPE_UPSERT_WORKFLOW_SEARCH_ATTRIBUTES":
            kept_events.append(event)
            continue
        fields = event["upsertWorkflowSearchAttributesEventAttributes"]["searchAttributes"][
            "indexedFields"
        ]
        payload = fields.get("TemporalChangeVersion")
        if payload is None:
            kept_events.append(event)
            continue
        ids = json.loads(base64.b64decode(payload["data"]))
        without_e74 = [i for i in ids if not i.startswith(E74_PREFIX)]
        if set(without_e74) <= running:
            dropped += 1  # the upsert existed only to record the e74 patch
            continue
        payload["data"] = base64.b64encode(json.dumps(without_e74).encode()).decode()
        running = set(without_e74)
        kept_events.append(event)
    events[:] = kept_events
    return dropped


def _history_without_e74_markers() -> tuple[WorkflowHistory, int, int, int]:
    """(history, markers removed, upserts dropped, surviving core_patch
    markers) for benchmark_one_cell with every e74-graph-child patch marker
    stripped AND its change-version side dropped, the remaining events
    renumbered consecutively, and the other core_patch markers left in place.
    This is the store that never knew the e74 patch: the replay must succeed
    purely through deprecate_patch semantics (020 T023, R-1)."""
    data = json.loads((HISTORIES / "benchmark_one_cell.json").read_text(encoding="utf-8"))
    events = data["history"]["events"]
    kept = [e for e in events if not (_patch_id(e) or "").startswith(E74_PREFIX)]
    removed = len(events) - len(kept)
    upserts = _strip_change_versions(kept)
    survivors = sum(1 for e in kept if _patch_id(e) is not None)
    _renumber(kept)
    data["history"]["events"] = kept
    history = WorkflowHistory.from_json(data["workflow_id"], json.dumps(data["history"]))
    return history, removed, upserts, survivors


@pytest.mark.asyncio
async def test_benchmark_workflow_replays_one_cell_history():
    result = await replayer(BenchmarkWorkflow).replay_workflow(
        load_history("benchmark_one_cell"), raise_on_replay_failure=True
    )
    assert result.replay_failure is None


@pytest.mark.asyncio
async def test_replays_with_the_e74_marker_stripped():
    """Replay-safe restart (020 R-1): the one-cell history carries a graph-child
    patch marker. With the marker AND its change-version upsert stripped, the
    replay must still succeed."""
    stripped, removed, upserts, survivors = _history_without_e74_markers()
    assert removed >= 1, "the strip removed no e74-graph-child marker"
    assert upserts >= 1, "the strip dropped no e74 change-version upsert"
    assert survivors == 2, "the 012 and 015 core_patch markers must survive the strip"
    result = await replayer(BenchmarkWorkflow).replay_workflow(
        stripped, raise_on_replay_failure=True
    )
    assert result.replay_failure is None
