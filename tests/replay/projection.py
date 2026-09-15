"""Golden-trace projections (E-74 spec §4.1).

Four projections make up a golden trace:
(1) STAGE_STARTED stage names;
(2) GATE_DECIDED rows;
(3) the ordered command projection of the history;
(4) the close.

(1) and (2) come from the in-memory run trace, so they are captured by
wrapping ReportHost._emit on an UNSANDBOXED capture worker. An unsandboxed
worker issues exactly the same commands as a sandboxed one.
"""

from __future__ import annotations

from typing import Any

from temporalio import workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter


def command_projection(history: WorkflowHistory) -> list[str]:
    out: list[str] = []
    for ev in history.events:
        t = ev.event_type
        if t == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED:
            out.append(f"activity:{ev.activity_task_scheduled_event_attributes.activity_type.name}")
        elif t == EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED:
            attrs = ev.start_child_workflow_execution_initiated_event_attributes
            out.append(f"child:{attrs.workflow_type.name}")
        elif t == EventType.EVENT_TYPE_TIMER_STARTED:
            out.append("timer")
        elif t == EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED:
            out.append("cancel_requested")
    return out


def close_projection(history: WorkflowHistory) -> str:
    for ev in reversed(history.events):
        t = ev.event_type
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED:
            payloads = list(ev.workflow_execution_completed_event_attributes.result.payloads)
            (value,) = pydantic_data_converter.payload_converter.from_payloads(payloads, [str])
            return str(value)
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED:
            failure = ev.workflow_execution_failed_event_attributes.failure
            return f"FAILED:{failure.application_failure_info.type}:{failure.message}"
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED:
            return "CANCELED"
        if t == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_TERMINATED:
            return "TERMINATED"
    return "OPEN"


class TraceRecorder:
    """Records STAGE_STARTED and GATE_DECIDED per workflow id, skipping replays."""

    def __init__(self) -> None:
        self._rows: dict[str, list[list[str]]] = {}

    def install(self, monkeypatch: Any) -> None:
        from sdlc.observability.trace import RunEventKind
        from sdlc.workflows.report_host import ReportHost

        original = ReportHost._emit
        rows = self._rows

        def _emit(host: Any, kind: Any, stage: str | None = None, **data: str) -> None:
            if not workflow.unsafe.is_replaying():
                wid = workflow.info().workflow_id
                if kind is RunEventKind.STAGE_STARTED:
                    rows.setdefault(wid, []).append(["stage", stage or ""])
                elif kind is RunEventKind.GATE_DECIDED:
                    rows.setdefault(wid, []).append(
                        [
                            "gate",
                            data.get("gate", ""),
                            data.get("round", ""),
                            data.get("decided_by", ""),
                            data.get("approved", ""),
                        ]
                    )
            original(host, kind, stage, **data)

        monkeypatch.setattr(ReportHost, "_emit", _emit)

    def trace(self, workflow_id: str) -> list[list[str]]:
        return list(self._rows.get(workflow_id, []))
