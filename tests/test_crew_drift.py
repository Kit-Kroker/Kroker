# tests/test_crew_drift.py
"""E-88 finding 12: drift keys on the activity NAME. A crew turn is a
different activity, and without this drift is silently uncomputed for crew
tasks -- a lost signal, which is the kind nobody notices."""
from __future__ import annotations

from sdlc.benchmarks.drift import CODING_ACTIVITIES


def test_the_crew_turn_counts_as_a_coding_activity():
    assert "run_coding_task" in CODING_ACTIVITIES
    assert "run_crew_turn" in CODING_ACTIVITIES
