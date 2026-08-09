"""FR-904 (E-44): the before/after triage delta.

Pure by design -- Pydantic, stdlib, `.models` and `..measurement` only, exactly
as models.py and grounding.py are. A dependency on temporalio or the root
models.py would appear as a reviewable import.

`compute_delta` is the ONLY producer of a FindingState (D4), mirroring
compute_readiness's relationship to Verdict: no caller sets a state, so a
TidyUpReport cannot disagree with its own inputs.

This is deliberately NOT a set difference. A naive before-minus-after diff
reads ABSENCE as RESOLUTION -- so a signal that timed out on the after side
would report every finding it had found as fixed. That is the same conflation
E-40 removed from report_from_sarif, which returned critical=0 for a malformed
document. Five conditions (D5) produce UNVERIFIABLE instead.
"""
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator

from ..measurement import CollectionState
from .models import RepoTriage, SignalResult, TriageFinding, finding_identity


class FindingState(str, Enum):
    RESOLVED = "resolved"          # present before, absent after
    PERSISTED = "persisted"        # present in both
    NEW = "new"                    # absent before, present after
    UNVERIFIABLE = "unverifiable"  # not measurable on one side


class FindingDelta(BaseModel):
    identity: str
    signal: str
    rule: str
    severity: Literal["critical", "high", "medium", "low"]
    state: FindingState
    reason: str = ""

    @model_validator(mode="after")
    def _unverifiable_states_a_reason(self) -> "FindingDelta":
        if self.state is FindingState.UNVERIFIABLE and not self.reason:
            raise ValueError(
                f"{self.identity}: UNVERIFIABLE without a reason -- the whole "
                f"point of the state is that it says WHY it could not be "
                f"measured")
        return self


def _unusable(signal_id: str,
              before: dict[str, SignalResult],
              after: dict[str, SignalResult]) -> str:
    """Why this signal's findings cannot be compared, or "" when they can."""
    b, a = before.get(signal_id), after.get(signal_id)
    for side, result in (("before", b), ("after", a)):
        if result is None:
            return (f"signal {signal_id!r} did not report on the {side} "
                    f"side, so its findings were never compared")
        if result.collected.state is not CollectionState.MEASURED:
            return (f"signal {signal_id!r} did not collect on the {side} "
                    f"side: {result.collected.reason}")
    if b.version != a.version:
        return (f"signal {signal_id!r} changed version between the two "
                f"triages (v{b.version} -> v{a.version}), so the two runs "
                f"did not measure the same thing")
    return ""


def _delta(identity: str, f: TriageFinding, state: FindingState,
           reason: str = "") -> FindingDelta:
    return FindingDelta(identity=identity, signal=f.signal, rule=f.rule,
                        severity=f.severity, state=state, reason=reason)


def compute_delta(before: RepoTriage,
                  after: RepoTriage | None,
                  conflicted: Sequence[str] = ()) -> list[FindingDelta]:
    """Classify every finding across the two triages.

    `conflicted` carries the identities whose fix branch failed to merge into
    the verification tree (D6). Their findings are present in `after` because
    the fix is not in the tree being measured -- reporting them PERSISTED
    would be true of that tree and misleading about the fix, so they are
    UNVERIFIABLE (D5 rule 3).
    """
    blocked = set(conflicted)
    before_f = {finding_identity(f): f
                for s in before.signals for f in s.findings}

    if after is None:
        # D5 rule 4. Never an empty delta: "nothing resolved" and "nothing
        # was measured" must not render identically.
        return [
            _delta(i, before_f[i], FindingState.UNVERIFIABLE,
                   "no verification tree was produced, so the after state "
                   "was never measured")
            for i in sorted(before_f)
        ]

    after_f = {finding_identity(f): f
               for s in after.signals for f in s.findings}
    before_s = {s.signal: s for s in before.signals}
    after_s = {s.signal: s for s in after.signals}

    out: list[FindingDelta] = []
    for identity in sorted(set(before_f) | set(after_f)):
        f = before_f.get(identity) or after_f[identity]

        reason = _unusable(f.signal, before_s, after_s)
        if reason:
            out.append(_delta(identity, f, FindingState.UNVERIFIABLE, reason))
            continue
        if identity in blocked:
            out.append(_delta(
                identity, f, FindingState.UNVERIFIABLE,
                "the fix branch for this finding hit a merge conflict and is "
                "not in the verification tree"))
            continue
        if identity in before_f and identity in after_f:
            out.append(_delta(identity, f, FindingState.PERSISTED))
        elif identity in before_f:
            out.append(_delta(identity, f, FindingState.RESOLVED))
        else:
            out.append(_delta(identity, f, FindingState.NEW))
    return out
