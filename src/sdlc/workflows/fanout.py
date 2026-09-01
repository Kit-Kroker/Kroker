"""One home for the degrade-alone rule (E-41 D3, E-46 D14).

TriageWorkflow and AssessmentWorkflow both fan out per-signal activities over
different row types, and both need the same guarantee: a timeout, a lost
worker or an exhausted retry becomes not_collected for THAT signal while
every other one still reports. The activity's own try/except cannot keep it,
because these failures happen outside the activity.

Two copies of that rule would agree only by coincidence -- the reason E-42 D2
extracted GateHost out of FeatureWorkflow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from temporalio import workflow

T = TypeVar("T")


async def run_or_degrade(
    activity: Any, arg: Any, opts: workflow.ActivityConfig, *, fallback: Callable[[], T]
) -> T:
    """Run one activity, or return `fallback()` if it could not run.

    `fallback` takes no arguments so the caller closes over whatever its own
    row type needs -- the one thing the two tiers do not share.
    """
    try:
        return await workflow.execute_activity(activity, arg, **opts)
    except Exception:  # noqa: BLE001
        return fallback()
