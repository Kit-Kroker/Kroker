"""Code-stage attempt usage recording (split from step.py at the 1000-line
ceiling).

One seam, two sinks, fed from the same numbers: the MODEL_USAGE trace event
the dashboard and retro read, and the per-attempt spend bag the code
record's CostBag is built from (stage_record(spend=...) -> cost_bag_from_spend).
The two must never diverge — a bag that never saw the tokens degrades every
code record to CostBag(usd=..., tokens=None), the exact seam the crew wiring
test exists to guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from temporalio import workflow

if TYPE_CHECKING:
    from ...core.context import StageContext
    from ...core.models import RoleUsage
    from ...harness.models import HarnessRunResult

with workflow.unsafe.imports_passed_through():
    from ...observability.trace import RunEventKind
    from ...observability.usage import merge_usage


def _record_attempt_usage(
    ctx: StageContext, code_spend: RoleUsage, run: HarnessRunResult, model: str
) -> None:
    """Emit the attempt's MODEL_USAGE event and fold the same tokens into
    `code_spend`. cost_usd is emitted but NOT folded: stage_record takes the
    harness-reported dollars explicitly, and folding them here would
    double-count the bag."""
    merge_usage(
        code_spend,
        model=model,
        input_tokens=run.input_tokens or 0,
        output_tokens=run.output_tokens or 0,
    )
    ctx.emit(
        RunEventKind.MODEL_USAGE,
        stage="code",
        role="dev",
        model=model,
        calls="1",
        input_tokens=str(run.input_tokens or 0),
        output_tokens=str(run.output_tokens or 0),
        cost_usd=str(run.cost_usd or 0.0),
    )
