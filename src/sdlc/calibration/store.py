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

from ..board.schema import apply_schema, connect, db_path
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
