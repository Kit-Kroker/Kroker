"""C7: SQLite I/O for the calibration ledger -- an activity, never workflow
code (the same rule memoization/activities.py states)."""

from __future__ import annotations

from dataclasses import dataclass, field

from temporalio import activity

from ..board.schema import db_path
from .models import CalibrationSample, CalibrationVerdict
from .store import CalibrationLedger
from .verdict import verdict_for


def _db_path():
    """Indirection so tests can point the ledger at a tmp_path."""
    return db_path()


@dataclass
class RecordSamplesInput:
    samples: list[CalibrationSample] = field(default_factory=list)


@dataclass
class VerdictInput:
    gate: str
    bucket_key: str


@activity.defn
async def record_calibration_samples(inp: RecordSamplesInput) -> None:
    ledger = CalibrationLedger(db=_db_path())
    try:
        ledger.append(inp.samples)
    finally:
        ledger.close()


@activity.defn
async def calibration_verdict(inp: VerdictInput) -> CalibrationVerdict:
    ledger = CalibrationLedger(db=_db_path())
    try:
        return verdict_for(ledger.recent(inp.gate, inp.bucket_key))
    finally:
        ledger.close()


ACTIVITIES = [record_calibration_samples, calibration_verdict]
