"""ReflectWorkflow (FR-404, E-13) — the nightly memory-consolidation job.

Exists only because Temporal Schedules start workflows, never activities:
`reflect` is an @activity.defn. This wrapper holds no logic beyond looping the
bank list. Each bank is its own activity execution so one bank's backend
failure retries independently without re-reflecting the others.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..memory.activities import ReflectInput, reflect

# Reflect consolidates a whole bank — slower than the 30s recall/retain ops
# in feature.py's MEM_ACT, hence the longer ceiling.
REFLECT_ACT = dict(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


class ReflectScheduleInput(BaseModel):
    banks: list[str] = Field(min_length=1)
    backend: str = "fake"
    base_url: str = "http://localhost:8888"


@workflow.defn
class ReflectWorkflow:
    """NEVER rename — the class name is the Temporal contract, and live
    Schedules reference it by name."""

    @workflow.run
    async def run(self, inp: ReflectScheduleInput) -> int:
        failed: list[str] = []
        for bank in inp.banks:
            try:
                await workflow.execute_activity(
                    reflect,
                    ReflectInput(bank=bank, backend=inp.backend, base_url=inp.base_url),
                    **REFLECT_ACT,
                )
            except Exception:
                # One unreachable bank must not skip the others, but the run
                # still fails below — a silent no-op is the failure mode this
                # whole feature exists to avoid.
                failed.append(bank)
        if failed:
            raise ApplicationError(
                f"reflect failed for banks: {', '.join(failed)}", non_retryable=True
            )
        return len(inp.banks)
