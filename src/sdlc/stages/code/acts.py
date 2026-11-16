"""Activity-config construction for the code stage.

The `ACT` / `LONG_ACT` configs and the `_long_act` role override, split out
of `step.py` for the 1000-line ceiling (024 T021, plan G1) — a pure,
line-neutral move: `step.py` re-imports them under the same names, so every
existing `from sdlc.stages.code.step import …` site keeps working (the
`freeze.py` precedent).

Long-running harness activities use heartbeat timeouts and retry policies
(this slice's AGENTS.md Temporal notes).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import TYPE_CHECKING

from temporalio import workflow
from temporalio.common import RetryPolicy

if TYPE_CHECKING:
    from ...core.models import RoleConfig

ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10),
    retry_policy=RetryPolicy(maximum_attempts=3),
)

LONG_ACT_HEARTBEAT_MINUTES = int(os.environ.get("SDLC_LONG_ACTIVITY_HEARTBEAT_MINUTES", "60"))
LONG_ACT_TIMEOUT_HOURS = int(os.environ.get("SDLC_LONG_ACTIVITY_TIMEOUT_HOURS", "4"))
LONG_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(hours=LONG_ACT_TIMEOUT_HOURS),
    heartbeat_timeout=timedelta(minutes=LONG_ACT_HEARTBEAT_MINUTES),
    retry_policy=RetryPolicy(maximum_attempts=2),
)


def _long_act(role_cfg: RoleConfig | None = None) -> workflow.ActivityConfig:
    if role_cfg is None:
        return LONG_ACT
    hours = role_cfg.activity_timeout_hours
    minutes = role_cfg.activity_heartbeat_minutes
    if hours is None and minutes is None:
        return LONG_ACT
    return workflow.ActivityConfig(
        start_to_close_timeout=timedelta(hours=hours or LONG_ACT_TIMEOUT_HOURS),
        heartbeat_timeout=timedelta(minutes=minutes or LONG_ACT_HEARTBEAT_MINUTES),
        retry_policy=RetryPolicy(maximum_attempts=2),
    )
