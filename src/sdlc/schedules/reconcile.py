"""Pure yaml→server diff (E-12). Deliberately free of any Temporal client so
every reconcile rule is unit-testable; apply.py supplies `existing` and turns
Changes into API calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ScheduleAsset


@dataclass(frozen=True)
class Change:
    action: str  # create | update | noop | drift
    id: str
    reason: str = ""


def plan_changes(desired: list[ScheduleAsset], existing: dict[str, ScheduleAsset]) -> list[Change]:
    """Diff yaml assets against server state. Never emits a delete: a server
    schedule with no yaml is reported as drift, and only apply's explicit
    --prune turns that into a deletion."""
    changes: list[Change] = []
    desired_ids = {a.id for a in desired}
    for a in desired:
        current = existing.get(a.id)
        if current is None:
            changes.append(Change("create", a.id, "not on server"))
        elif current != a:
            changes.append(Change("update", a.id, "differs from server"))
        else:
            changes.append(Change("noop", a.id, "identical"))
    for sid in sorted(existing):
        if sid not in desired_ids:
            changes.append(Change("drift", sid, "on server, no yaml asset"))
    return changes
