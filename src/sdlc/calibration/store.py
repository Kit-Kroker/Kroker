"""C7: the gate-calibration ledger.

Append-only, so none of capability/store.py's optimistic-concurrency
machinery applies -- this is the capability_event shape, not the
capability_identity shape. It lives in the board's SQLite file (ADR-19:
adapters, not substrate) rather than a third storage scheme.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from ..board.schema import apply_schema, connect, db_path
from ..core.models import RunSummary
from .metrics import GateDecisionRecord
from .models import BucketSummary, CalibrationSample
from .verdict import WINDOW, verdict_for


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CalibrationLedger:
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def append(self, samples: Sequence[CalibrationSample]) -> None:
        if not samples:
            return
        at = _now()
        self._conn.executemany(
            "INSERT INTO gate_calibration (gate, bucket_key, confidence, "
            "outcome_label, run_id, recorded_at) VALUES (?,?,?,?,?,?)",
            [(s.gate, s.bucket_key, s.confidence, s.outcome_label, s.run_id, at) for s in samples],
        )

    def recent(self, gate: str, bucket_key: str, limit: int = WINDOW) -> list[tuple[float, float]]:
        """The window's (confidence, outcome_label) pairs, oldest-first.

        Ruling OQ5 bounds what the verdict READS, not what the table keeps:
        superseded samples stay on disk so a past verdict can be audited."""
        rows = self._conn.execute(
            "SELECT confidence, outcome_label FROM gate_calibration "
            "WHERE gate = ? AND bucket_key = ? ORDER BY id DESC LIMIT ?",
            (gate, bucket_key, limit),
        ).fetchall()
        return [(r[0], r[1]) for r in reversed(rows)]

    def summary(self) -> list[BucketSummary]:
        """One row per DISTINCT (gate, bucket_key) bucket, each verdict
        computed over the same windowed read (`recent` -> `verdict_for`)
        the gate's decision path makes -- so what the operator sees is
        what the gate would do, not a second statistic. FR-301's read
        surface; nothing decides from it."""
        buckets = self._conn.execute(
            "SELECT DISTINCT gate, bucket_key FROM gate_calibration ORDER BY gate, bucket_key"
        ).fetchall()
        out: list[BucketSummary] = []
        for gate, bucket_key in buckets:
            verdict = verdict_for(self.recent(gate, bucket_key))
            row = self._conn.execute(
                "SELECT MAX(recorded_at) FROM gate_calibration WHERE gate = ? AND bucket_key = ?",
                (gate, bucket_key),
            ).fetchone()
            out.append(
                BucketSummary(
                    gate=gate,
                    bucket_key=bucket_key,
                    verdict=verdict,
                    last_sample_at=row[0] if row is not None else None,
                )
            )
        return out


def gate_decisions_from_exports(
    root: str | os.PathLike | None = None,
) -> list[GateDecisionRecord]:
    """Every gate decision every closed run exported, as SC-6 reads them.

    The retained source is the retro export (observability/activities.py):
    each run closes with `<root>/<run_id>/summary.json`, RunSummary as
    data, whose `gates` list `GateOutcomeSummary` documents as the SC-6
    signal -- already deduped per (gate, round) by build_run_summary. No
    second store is built beside it.

    Root defaults to SDLC_EXPORT_ROOT or ./runs/pipeline, mirroring the
    export activity's own resolution. A missing root reads as no decisions
    (empty state, not an error -- a fresh checkout must answer); a
    summary that fails to parse or read is skipped, because a truncated
    export from a crashed run must not hide every other run's decisions.
    Sorted glob so the read never depends on directory order.
    """
    base = root if root is not None else os.environ.get("SDLC_EXPORT_ROOT", "./runs/pipeline")
    records: list[GateDecisionRecord] = []
    for path in sorted(Path(base).glob("*/summary.json")):
        try:
            summary = RunSummary.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
        records.extend(
            GateDecisionRecord(gate=g.gate, policy=g.policy, decided_by=g.decided_by)
            for g in summary.gates
        )
    return records
