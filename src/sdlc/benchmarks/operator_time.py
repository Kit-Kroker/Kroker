"""SC-2 operator-time derivation (025, FR-003/004/005, spec A.1/A.6).

Pure derivation from data a run already writes: the summary stores raw
raise/decide times and the marker; this module owns the engagement cap and
the counting rules. No I/O — changing the cap re-derives without re-running
runs (FR-004).

Counting rules (A.6):
- "human" for a gate means `decided_by` not in {policy, timeout}: a merge
  override can carry a reviewer name (research R2), and it still engaged a
  person.
- A clarification batch — questions raised together share `raised_at` (one
  ASKED loop, R3; the summary row keeps no stage, so `raised_at` alone keys
  the batch) — is ONE interaction when at least one question was answered
  by a human, deciding on the batch's latest answered_at (a suggested
  straggler's time is the batch's close; unanswered rows contribute none).
- not_measured: a pre-025 summary (marker False), or any human interaction
  lacking its raise or decide time — never silently zero (FR-005).
- Overlapping interactions are summed, not merged: engaged_s is an upper
  bound and is reported as such.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..core.models import ClarificationOutcome, RunSummary

# Q1 (GATE 1, 2026-11-16): the per-interaction engagement cap, ten minutes.
# The system sees raise and decide, not when reading started; the cap bounds
# the error in the only direction that matters (overnight waits).
ENGAGEMENT_CAP_S = 600

OperatorTimeState = Literal["not_measured", "zero", "measured"]

# Gate deciders that never engaged a person (A.6). Everything else —
# "human" and any merge-override reviewer name — did.
_NON_HUMAN_DECIDERS = frozenset({"policy", "timeout"})


class Interaction(BaseModel):
    """One human-decided interaction: a gate round, or a clarification batch."""

    kind: Literal["gate", "clarification"]
    key: str  # gate: "<gate>#<round>"; batch: "clarification@<raised_at>"
    raised_at: datetime
    decided_at: datetime


class RunOperatorTime(BaseModel):
    """FR-003: per-run operator time. engaged_s is capped per interaction;
    wait_s is the uncapped wall-clock sum; both over the same interactions."""

    state: OperatorTimeState
    interactions: list[Interaction] = Field(default_factory=list)
    engaged_s: float = 0.0
    wait_s: float = 0.0


def operator_time(summary: RunSummary) -> RunOperatorTime:
    if not summary.operator_instrumented:
        return RunOperatorTime(state="not_measured")

    interactions: list[Interaction] = []
    for g in summary.gates:
        if g.decided_by in _NON_HUMAN_DECIDERS:
            continue
        if g.raised_at is None or g.decided_at is None:
            return RunOperatorTime(state="not_measured")
        interactions.append(
            Interaction(
                kind="gate",
                key=f"{g.gate}#{g.round}",
                raised_at=g.raised_at,
                decided_at=g.decided_at,
            )
        )

    batches: dict[datetime, list[ClarificationOutcome]] = defaultdict(list)
    for c in summary.clarifications:
        if c.raised_at is None:
            # A human question without its raise time cannot be intervalled;
            # anything else simply joins no batch.
            if c.answered_by == "human":
                return RunOperatorTime(state="not_measured")
            continue
        batches[c.raised_at].append(c)
    for raised_at, rows in batches.items():
        if not any(c.answered_by == "human" for c in rows):
            continue
        answered = [c.answered_at for c in rows if c.answered_at is not None]
        if not answered:
            return RunOperatorTime(state="not_measured")
        interactions.append(
            Interaction(
                kind="clarification",
                key=f"clarification@{raised_at.isoformat()}",
                raised_at=raised_at,
                decided_at=max(answered),
            )
        )

    if not interactions:
        return RunOperatorTime(state="zero")

    spans = [(i.decided_at - i.raised_at).total_seconds() for i in interactions]
    return RunOperatorTime(
        state="measured",
        interactions=interactions,
        engaged_s=sum(min(s, ENGAGEMENT_CAP_S) for s in spans),
        wait_s=sum(spans),
    )
