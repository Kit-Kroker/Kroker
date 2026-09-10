"""C7: gate-confidence calibration -- the ledger behind a self-reported
confidence that would otherwise skip a human gate.

See docs/superpowers/specs/2026-09-10-c7-confidence-gate-design.md.
"""

from __future__ import annotations

from .decision import auto_decision_for
from .labels import fix_attempt_label, plan_drift_label, unhinted_ratio
from .models import INSUFFICIENT, CalibrationSample, CalibrationVerdict, LabelSource
from .verdict import MIN_SAMPLES, WINDOW, bucket_key, verdict_for

__all__ = [
    "INSUFFICIENT",
    "MIN_SAMPLES",
    "WINDOW",
    "CalibrationSample",
    "CalibrationVerdict",
    "LabelSource",
    "auto_decision_for",
    "bucket_key",
    "fix_attempt_label",
    "plan_drift_label",
    "unhinted_ratio",
    "verdict_for",
]
