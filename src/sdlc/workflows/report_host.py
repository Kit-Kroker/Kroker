"""ReportHost -- the run trace and the status vocabulary (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54). temporalio collects
definitions with inspect.getmembers, which walks the MRO
(temporalio/workflow/_definition.py:288), so a mixin is a blessed place for
workflow behaviour. Only @workflow.run must be on the concrete class.

Owns: _trace, _seq, _status, _role_usage. Nothing else may write them --
see workflows/AGENTS.md for the full attribute-ownership table.
"""

from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..core.models import RoleUsage
    from ..observability.trace import RunEvent, RunEventKind
    from ..observability.usage import merge_usage


class ReportHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        self._trace: list[RunEvent] = []
        self._seq: int = 0
        self._status: str = "starting"
        self._role_usage: dict[str, RoleUsage] = {}

    def _emit(self, kind: RunEventKind, stage: str | None = None, **data: str) -> None:
        """Append a domain event to the run trace. Pure state mutation — safe
        in workflow code (no I/O, deterministic seq + workflow.now())."""
        self._trace.append(
            RunEvent(seq=self._seq, at=workflow.now(), kind=kind, stage=stage, data=data)
        )
        self._seq += 1

    def _stage(self, status: str, trace: str | None = None) -> None:
        """Record stage start: _status keeps the run's status vocabulary
        (status() query consumers), while the STAGE_STARTED trace event uses
        the canonical stage nouns -- the same vocabulary STAGE_ENDED,
        run_summary.terminal_stage, and the dashboard's CANONICAL_STAGES
        (benchmarks/heatmap.py) already speak. Two vocabularies in one trace
        is how the fleet view and the benchmarks come to disagree."""
        self._status = status
        self._emit(RunEventKind.STAGE_STARTED, stage=trace or status)

    def _track_usage(
        self,
        *,
        role: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_usd: float | None = None,
        into: RoleUsage | None = None,
    ) -> None:
        """Fold one model call into the run's per-role accumulator and emit
        a MODEL_USAGE event. Pure state mutation — safe in workflow code.
        `into` additionally folds the same delta into a caller-held bag
        (per-stage benchmark records)."""
        bag = self._role_usage.setdefault(role, RoleUsage(role=role, model=model))
        for target in (bag, into) if into is not None else (bag,):
            merge_usage(
                target,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_write_tokens,
                cost_usd=cost_usd,
            )
        self._emit(
            RunEventKind.MODEL_USAGE,
            role=role,
            model=model,
            calls="1",
            input_tokens=str(input_tokens),
            output_tokens=str(output_tokens),
            cache_read_tokens=str(cache_read_tokens),
            cache_write_tokens=str(cache_write_tokens),
            **({"cost_usd": str(cost_usd)} if cost_usd is not None else {}),
        )
