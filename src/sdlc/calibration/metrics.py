"""SC-6: the soft-gate override rate, purely computed.

Audit row SC-6 asks whether the SOFT-gate policy is earning trust or being
rubber-stamped: the share of SOFT gate decisions where a human decided
rather than the policy auto-approving. Pure like labels.py/verdict.py --
no I/O, no temporalio -- so the number is testable far from any store.

The retained decision records live where the retro export already puts
them (`RunSummary.gates`, written per exported run as summary.json); the
store reader beside the ledger fetches them, this module only counts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from ..core.models import GatePolicy

DECIDED_BY_POLICY = "policy"


class GateDecisionRecord(NamedTuple):
    """One gate decision as the metric reads it: gate, policy, decided_by.

    `GateOutcomeSummary` carries more (round, approved, confidence,
    author_model); SC-6 counts heads, so the reader strips to these three
    and the metric cannot accidentally grow an opinion about the rest.
    """

    gate: str
    policy: str
    decided_by: str


class OverrideRate(NamedTuple):
    """The SC-6 counts. `rate` is None on zero decisions -- undefined, not
    0%, which would claim a perfection no data supports."""

    human: int
    total: int

    @property
    def rate(self) -> float | None:
        if self.total == 0:
            return None
        return self.human / self.total


def soft_gate_override_rate(records: Sequence[GateDecisionRecord]) -> OverrideRate:
    """Human decisions ÷ all decisions on SOFT-policy gates.

    Only policy=="soft" rows enter either side: HARD gates are always
    human and OFF gates always synthesize decided_by="policy", so neither
    population can say whether the SOFT policy earned trust. A timed-out
    SOFT gate counts as an override -- no human arrived and the policy did
    not decide either; it still failed to earn the gate. Zero decisions is
    the empty state (OverrideRate(0, 0), rate None), never a division.
    """
    soft = [r for r in records if r.policy == GatePolicy.SOFT.value]
    human = sum(1 for r in soft if r.decided_by != DECIDED_BY_POLICY)
    return OverrideRate(human=human, total=len(soft))
