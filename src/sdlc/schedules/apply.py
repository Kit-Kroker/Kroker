"""Reconcile schedule assets into Temporal Schedules (E-12).

Files are the source of truth, but Schedules are server-side mutable state —
so applying is an explicit act with a visible diff (`--dry-run`), never a side
effect of a worker restart. See the spec's "explicit CLI apply" decision.
"""

from __future__ import annotations

from typing import Literal, cast

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleSpec,
    ScheduleUpdate,
)

from ..models import (
    KNOWN_SCHEDULE_WORKFLOWS,
    ScheduleAction,
    ScheduleAsset,
    ScheduleSpecAsset,
)
from ..workflows.reflect import ReflectScheduleInput
from .reconcile import Change


def _workflow_id(sid: str) -> str:
    # A fixed id is correct here: Temporal auto-appends a per-fire scheduled-time
    # suffix to schedule-started workflow ids, so each nightly fire gets a unique
    # id and the default WorkflowIdReusePolicy never rejects a later fire. Verified
    # live on Temporal Server 1.31.1 (a fixed-id control produced <id>-<time> per
    # fire; two fires both started). The {{ .ScheduledTime }} templating token is
    # NOT substituted by this SDK/server and would render as literal text, so it is
    # intentionally NOT used here.
    return f"sched-{sid}"


def to_temporal(a: ScheduleAsset) -> Schedule:
    from ..worker import TASK_QUEUE

    return Schedule(
        action=ScheduleActionStartWorkflow(
            a.action.workflow,
            args=[
                ReflectScheduleInput(
                    banks=a.action.banks, backend=a.action.backend, base_url=a.action.base_url
                )
            ],
            id=_workflow_id(a.id),
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(cron_expressions=[a.spec.cron], time_zone_name=a.spec.timezone),
    )


def from_temporal(sid: str, sched: Schedule) -> ScheduleAsset | None:
    """Server Schedule → asset, or None if we don't manage it. Unmanaged
    schedules must be invisible to the diff, not reported as drift."""
    action = sched.action
    if not isinstance(action, ScheduleActionStartWorkflow):
        return None
    if action.workflow not in KNOWN_SCHEDULE_WORKFLOWS:
        return None
    if not action.args:
        return None
    if not sched.spec.cron_expressions:
        return None
    # Tolerates both a decoded ReflectScheduleInput and the plain dict the
    # default converter can hand back for an untyped arg.
    inp = ReflectScheduleInput.model_validate(action.args[0])
    return ScheduleAsset(
        id=sid,
        spec=ScheduleSpecAsset(
            cron=sched.spec.cron_expressions[0],
            timezone=sched.spec.time_zone_name or "UTC",
        ),
        action=ScheduleAction(
            workflow=action.workflow,
            banks=inp.banks,
            # ReflectScheduleInput.backend is a plain str; ScheduleAction
            # re-validates the literal at construction.
            backend=cast(Literal["fake", "hindsight"], inp.backend),
            base_url=inp.base_url,
        ),
    )


async def fetch_existing(client: Client) -> dict[str, ScheduleAsset]:
    out: dict[str, ScheduleAsset] = {}
    async for entry in await client.list_schedules():
        desc = await client.get_schedule_handle(entry.id).describe()
        asset = from_temporal(entry.id, desc.schedule)
        if asset is not None:
            out[entry.id] = asset
    return out


def format_plan(changes: list[Change]) -> str:
    if not changes:
        return "no schedules to reconcile"
    return "\n".join(f"  {c.action:<7} {c.id:<24} ({c.reason})" for c in changes)


async def apply_changes(
    client: Client, desired: list[ScheduleAsset], changes: list[Change], prune: bool = False
) -> list[str]:
    """Execute a plan. Drift is only deleted when prune is True."""
    by_id = {a.id: a for a in desired}
    results: list[str] = []
    for c in changes:
        if c.action == "create":
            await client.create_schedule(c.id, to_temporal(by_id[c.id]))
            results.append(f"created {c.id}")
        elif c.action == "update":
            handle = client.get_schedule_handle(c.id)
            asset = by_id[c.id]

            # update() takes an updater that returns a ScheduleUpdate, never a
            # bare Schedule. The default-arg bind avoids the late-binding trap.
            def _updater(_: object, a: ScheduleAsset = asset) -> ScheduleUpdate:
                return ScheduleUpdate(schedule=to_temporal(a))

            await handle.update(_updater)
            results.append(f"updated {c.id}")
        elif c.action == "noop":
            pass
        elif c.action == "drift":
            if prune:
                await client.get_schedule_handle(c.id).delete()
                results.append(f"deleted {c.id}")
            else:
                results.append(f"DRIFT {c.id} on server with no yaml asset (use --prune to delete)")
        else:
            raise ValueError(f"unknown schedule change action: {c.action!r}")
    return results
