"""Golden projections over a synthetic history (E-74 spec §4.1)."""

from __future__ import annotations

from temporalio.api.enums.v1 import EventType
from temporalio.api.history.v1 import HistoryEvent
from temporalio.client import WorkflowHistory
from temporalio.contrib.pydantic import pydantic_data_converter

from tests.replay.projection import close_projection, command_projection


def _history(*events: HistoryEvent) -> WorkflowHistory:
    return WorkflowHistory("wf-1", list(events))


def _scheduled(name: str) -> HistoryEvent:
    ev = HistoryEvent(event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED)
    ev.activity_task_scheduled_event_attributes.activity_type.name = name
    return ev


def test_command_projection_keeps_order_and_kinds():
    child = HistoryEvent(event_type=EventType.EVENT_TYPE_START_CHILD_WORKFLOW_EXECUTION_INITIATED)
    child.start_child_workflow_execution_initiated_event_attributes.workflow_type.name = (
        "DeploymentWorkflow"
    )
    timer = HistoryEvent(event_type=EventType.EVENT_TYPE_TIMER_STARTED)
    cancel = HistoryEvent(event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_CANCEL_REQUESTED)
    marker = HistoryEvent(event_type=EventType.EVENT_TYPE_MARKER_RECORDED)
    history = _history(_scheduled("classify_repo"), timer, marker, child, cancel)
    assert command_projection(history) == [
        "activity:classify_repo",
        "timer",
        "child:DeploymentWorkflow",
        "cancel_requested",
    ]


def test_close_projection_completed_failed_canceled():
    done = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED)
    payloads = pydantic_data_converter.payload_converter.to_payloads(["deployed:x"])
    done.workflow_execution_completed_event_attributes.result.payloads.extend(payloads)
    assert close_projection(_history(done)) == "deployed:x"

    failed = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_FAILED)
    failure = failed.workflow_execution_failed_event_attributes.failure
    failure.message = "boom"
    failure.application_failure_info.type = "ApplicationError"
    assert close_projection(_history(failed)) == "FAILED:ApplicationError:boom"

    canceled = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_EXECUTION_CANCELED)
    assert close_projection(_history(canceled)) == "CANCELED"
