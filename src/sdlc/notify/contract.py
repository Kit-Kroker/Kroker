"""What a notification is, independent of how it is delivered."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..pending import PendingDecision


class NotifyReason(str, Enum):
    """Why this notification is being sent. Also selects the recipient tier:
    ESCALATE goes to primary AND fallback; everything else to primary."""
    OPENED = "opened"
    REMIND = "remind"
    ESCALATE = "escalate"
    EXPIRE = "expire"


class NotifyInput(BaseModel):
    """Workflow -> notify activity. Carries the pending decision itself so
    the activity can render it with E-6's default_render; no route is passed
    because route resolution reads a file the workflow cannot."""
    run_id: str
    pending: PendingDecision
    reason: NotifyReason
    opened_at: datetime
    now: datetime            # workflow.now() -- the activity reads no clock
    deadline: datetime | None = None


class DeliveryResult(BaseModel):
    """One delivery attempt. `notifier` is the adapter NAME only -- never the
    resolved target, which for a webhook is a bearer credential."""
    notifier: str
    delivered: bool
    error: str | None = None


class Results(BaseModel):
    """The notify activity's return value. A list is not used directly so the
    payload stays a named type across the Temporal boundary."""
    results: list[DeliveryResult] = Field(default_factory=list)


@runtime_checkable
class Notifier(Protocol):
    """A delivery transport. `target` is the route's suffix (a URL for
    webhook, None for log). Raising is allowed -- the activity catches and
    reports it as a failed delivery."""
    async def deliver(self, text: str, target: str | None) -> None: ...
