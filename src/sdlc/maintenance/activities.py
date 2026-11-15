"""The maintenance loop's own activities (023b T014, R2).

``probe_repair_child`` is the client-side observation surface: one
describe plus the two queries (``pending_decisions`` / ``run_state``)
per in-flight child, and a history read for terminal children. It makes
NO git mutation -- the only git touch is the read-only
``integration_branch_head`` rev-parse through the S/vcs/ helper, so
S/maintenance keeps its hands clean (B-FR-016); everything the probe
learns comes from Temporal or a read.
"""

from __future__ import annotations

import json

from temporalio import activity
from temporalio.service import RPCError, RPCStatusCode

from ..vcs.integration import integration_branch_for, integration_branch_head
from .models import ChildProbe


def _result_of_completed(payloads) -> str | None:  # noqa: ANN001 -- proto payloads
    """The child's return string, from the completion event's payload."""
    if not payloads:
        return None
    try:
        out = json.loads(payloads[0].data)
    except (ValueError, IndexError):
        return None
    return out if isinstance(out, str) else None


def _merge_round(pending) -> int | None:  # noqa: ANN001 -- query payload
    """The open merge gate's round from a pending_decisions query.

    A by-name query deserializes without type information, so the entries
    may be dicts (plain converter) or PendingDecision models (typed); read
    both shapes."""
    for p in pending:
        gate = p.get("gate") if isinstance(p, dict) else getattr(p, "gate", None)
        rnd = p.get("round") if isinstance(p, dict) else getattr(p, "round", None)
        if gate == "merge" and isinstance(rnd, int):
            return rnd
    return None


def _repo_url(state) -> str | None:  # noqa: ANN001 -- query payload
    """The child's repo from a by-name run_state query: dict or model."""
    if state is None:
        return None
    value = state.get("repo_url") if isinstance(state, dict) else state.repo_url
    return value or None


def _failure_of(failure) -> tuple[str | None, bool]:  # noqa: ANN001 -- proto failure
    """(message, non_retryable) from a terminal failure."""
    if failure is None:
        return None, False
    message = (failure.message or "")[:300]
    info = failure.application_failure_info
    non_retryable = bool(info.non_retryable) if info is not None else False
    return message, non_retryable


@activity.defn
async def probe_repair_child(child_id: str) -> ChildProbe:
    """What one repair child is doing right now (R2): ``running`` |
    ``awaiting_merge`` | ``completed`` | ``failed`` | ``cancelled`` |
    ``terminated`` | ``timed_out`` | ``not_found``. One describe, two
    queries for a live child, one history read for a closed one."""
    client = activity.client()
    handle = client.get_workflow_handle(child_id)
    try:
        desc = await handle.describe()
    except RPCError as err:
        if err.status == RPCStatusCode.NOT_FOUND:
            return ChildProbe(phase="not_found")
        raise

    status = desc.status.name if desc.status is not None else ""
    if status == "RUNNING":
        pending = await handle.query("pending_decisions")
        round = _merge_round(pending)
        if round is None:
            return ChildProbe(phase="running")
        branch = integration_branch_for(child_id)
        repo_url = _repo_url(await handle.query("run_state"))
        head = integration_branch_head(repo_url, child_id) if repo_url else None
        return ChildProbe(
            phase="awaiting_merge",
            pending_merge_round=round,
            integration_branch=branch,
            integration_head=head,
        )

    if status == "COMPLETED":
        history = await handle.fetch_history()
        closed = history.events[-1]
        return ChildProbe(
            phase="completed",
            result=_result_of_completed(
                closed.workflow_execution_completed_event_attributes.result.payloads
            ),
        )

    if status == "FAILED":
        history = await handle.fetch_history()
        closed = history.events[-1]
        message, non_retryable = _failure_of(
            closed.workflow_execution_failed_event_attributes.failure
        )
        return ChildProbe(phase="failed", failure=message, non_retryable=non_retryable)

    if status == "TIMED_OUT":
        return ChildProbe(phase="timed_out")
    if status == "CANCELED":
        return ChildProbe(phase="cancelled")
    if status == "TERMINATED":
        return ChildProbe(phase="terminated")
    # CONTINUED_AS_NEW and anything future: the run IS still going.
    return ChildProbe(phase="running")
