"""E-9 (FR-303): gate notifications, reminder timers, fallback escalation.

The workflow owns the timers; this package owns everything else -- what a
notification says, where it goes, and how it is delivered. All file I/O lives
in `activities.py`, because the workflow sandbox cannot read files (the same
split as harness containment).
"""

from .contract import DeliveryResult, Notifier, NotifyInput, NotifyReason
from .schedule import build_schedule

__all__ = [
    "DeliveryResult",
    "NotifyInput",
    "Notifier",
    "NotifyReason",
    "build_schedule",
]
