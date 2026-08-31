"""DriftHarvester — production telemetry → BenchmarkRecords.

Observational only: judge ∈ {"contract", "human_override"} — we never re-judge
production artifacts with the LLM. The Temporal client is behind an injectable
history_provider so tests pass a fake.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import (BenchmarkOutcome, BenchmarkRecord, BenchmarkScope,
                     CostBag, QualityScore, SpeedBag)
from .recorder import RecordStore
from ..models import HarnessKind

_log = logging.getLogger(__name__)


class HistoryProvider(Protocol):
    async def list_completed(self, hours: int) -> list[tuple[str, Any]]: ...
    async def fetch_history(self, run_id: str) -> Any: ...


class DriftHarvester:
    def __init__(self, provider: HistoryProvider, root: str | None = None,
                 bench_run_id: str = "_drift") -> None:
        self.provider = provider
        # Store the configured bench_run_id verbatim and pass it through to
        # each record. Deriving it from the store's path parent is buggy: a
        # namespace like "_drift/2026-07-04" would collapse to its final
        # segment ("2026-07-04") and corrupt the record's identity.
        self.bench_run_id = bench_run_id
        self.store = RecordStore(root=root, bench_run_id=bench_run_id,
                                 cell_id=None)

    async def harvest_since(self, hours: int) -> int:
        runs = await self.provider.list_completed(hours)
        n = 0
        for run_id, _ in runs:
            try:
                history = await self.provider.fetch_history(run_id)
            except Exception as exc:
                _log.warning("drift: skipping run %s (fetch_history raised: %r)",
                             run_id, exc)
                continue
            for ev in _iter_events(history):
                rec = _record_from_event(run_id, ev, self.bench_run_id)
                if rec is not None:
                    self.store.append(rec)
                    n += 1
        return n


def _iter_events(history: Any):
    # history is either a list of events or a dict with "events"
    if isinstance(history, dict) and "events" in history:
        return history["events"]
    if isinstance(history, (list, tuple)):
        return history
    return []


# E-88: a coding turn is no longer one activity name. Naming the set here
# rather than inline is what makes the omission testable.
#
# NOTE for _run_drift's future implementation: run_crew_turn events live
# in the CHILD workflow's (CrewTaskWorkflow) history, not FeatureWorkflow's
# — list_completed/fetch_history must walk child executions, or crew turns
# never surface.
CODING_ACTIVITIES = frozenset({"run_coding_task", "run_crew_turn"})


def _record_from_event(run_id: str, event: Any, bench_run_id: str
                       ) -> BenchmarkRecord | None:
    if not isinstance(event, dict):
        return None
    if event.get("event_type") != "ActivityTaskCompleted":
        return None
    if event.get("activity") not in CODING_ACTIVITIES:
        return None
    result = event.get("result")
    if not isinstance(result, dict):
        return None
    # E-88: run_crew_turn returns CrewTurnOutput; the shared-contract
    # fields (harness/exit_code/cost_usd/...) live on .run.
    if isinstance(result.get("run"), dict):
        result = result["run"]
    try:
        ts = event.get("timestamp") or datetime.now(timezone.utc)
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        started = ts
        ended = ts
        harness = HarnessKind(result.get("harness", "claude_code"))
        exit_code = int(result.get("exit_code", 1))
        return BenchmarkRecord(
            run_id=run_id,
            bench_run_id=bench_run_id,
            case_id="_production",
            scope=BenchmarkScope.TASK_ATTEMPT, stage="code", task_id=run_id,
            attempt=0, role="dev", harness=harness,
            model="unknown",   # drift can't reliably recover the per-run model
                               # without parsing WorkflowStarted attributes; left
                               # for a later hardening pass
            quality=QualityScore(score=None if exit_code != 0 else 1.0,
                                 judge="contract"),
            cost=CostBag(usd=result.get("cost_usd"),
                         input_tokens=result.get("input_tokens"),
                         output_tokens=result.get("output_tokens")),
            speed=SpeedBag(wall_clock_s=0.0, started_at=started, ended_at=ended),
            outcome=(BenchmarkOutcome.PASS if exit_code == 0
                     else BenchmarkOutcome.FAIL),
        )
    except (TypeError, ValueError):
        return None
