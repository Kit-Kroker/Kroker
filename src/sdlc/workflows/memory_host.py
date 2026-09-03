"""MemoryHost -- episodic memory recall and retention (spec A §3.1).

A mixin, following GateHost (workflows/gates.py:54).

Owns: _memory_watermark.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..core.models import PipelineConfig
    from ..memory.activities import (
        RecallInput,
        RetainInput,
        recall_snapshot,
        retain,
    )
    from ..models import MemoryKind, RecallSnapshot, RetainItem

MEM_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(seconds=30), retry_policy=RetryPolicy(maximum_attempts=5)
)


class MemoryHost:
    """Mixin. Subclasses must call super().__init__()."""

    def __init__(self) -> None:
        super().__init__()
        self._memory_watermark: str | None = None

    async def _recall(
        self, cfg: PipelineConfig, bank: str, query: str, filters: dict[str, str]
    ) -> RecallSnapshot:
        if not cfg.memory.enabled:
            return RecallSnapshot(query_hash="", bank=bank, watermark="unknown", items=[])
        return await workflow.execute_activity(
            recall_snapshot,
            RecallInput(
                bank=bank,
                query=query,
                filters=filters,
                watermark=self._memory_watermark,
                backend=cfg.memory.backend,
                base_url=cfg.memory.base_url,
            ),
            **MEM_ACT,
        )

    async def _retain(
        self, cfg: PipelineConfig, kind: MemoryKind, bank: str, text: str, metadata: dict[str, str]
    ) -> None:
        if not cfg.memory.enabled:
            return
        try:
            await workflow.execute_activity(
                retain,
                RetainInput(
                    item=RetainItem(kind=kind, bank=bank, text=text, metadata=metadata),
                    backend=cfg.memory.backend,
                    base_url=cfg.memory.base_url,
                ),
                **MEM_ACT,
            )
        except Exception:
            pass
