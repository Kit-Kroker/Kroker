"""ReflectWorkflow (FR-404, E-13) — the nightly memory-consolidation job.

Exists only because Temporal Schedules start workflows, never activities:
`reflect` is an @activity.defn. This wrapper holds no logic beyond sequencing
the one job: each project bank reflects, then — when an org bank is
configured — gotchas recurring across projects promote into it and the org
bank reflects too (FR-404 whole, E-25). Each step is its own activity
execution so one backend failure retries independently without re-reflecting
the others.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from ..memory.activities import PromoteInput, ReflectInput, promote_org_learnings, reflect

# Reflect consolidates a whole bank — slower than the 30s recall/retain ops
# in feature.py's MEM_ACT, hence the longer ceiling.
REFLECT_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=3)
)


class ReflectScheduleInput(BaseModel):
    banks: list[str] = Field(min_length=1)
    backend: str = "fake"
    base_url: str = "http://localhost:8888"
    # Defaulted so pre-change recorded Schedule args decode identically;
    # None means the org half of the job is off.
    org_bank: str | None = None
    promote_min_projects: int = 2


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
        if inp.org_bank is not None:
            # Promote first so the org reflect consolidates what promotion
            # just retained. Both steps are attempted even if one fails —
            # each lands in `failed` below, never silently skipped.
            org = inp.org_bank
            try:
                await workflow.execute_activity(
                    promote_org_learnings,
                    PromoteInput(
                        project_banks=inp.banks,
                        org_bank=org,
                        min_projects=inp.promote_min_projects,
                        backend=inp.backend,
                        base_url=inp.base_url,
                    ),
                    **REFLECT_ACT,
                )
            except Exception:
                failed.append(f"promote:{org}")
            try:
                await workflow.execute_activity(
                    reflect,
                    ReflectInput(bank=org, backend=inp.backend, base_url=inp.base_url),
                    **REFLECT_ACT,
                )
            except Exception:
                failed.append(org)
        if failed:
            raise ApplicationError(
                f"reflect failed for banks: {', '.join(failed)}", non_retryable=True
            )
        return len(inp.banks)
