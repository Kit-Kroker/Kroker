"""FR-901/FR-902 (E-41): the triage artifact and its contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as measurement.py and
grounding.py must not: a dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..measurement import CollectionState, Measurement


class FixClass(str, Enum):
    """FR-904. MECHANICAL is a promise an E-44 child run can keep with a PR;
    everything it cannot is JUDGEMENT or STRUCTURAL. See spec D7 -- deleting a
    committed .env is mechanical, rotating the exposed credential is not."""
    MECHANICAL = "mechanical"
    JUDGEMENT = "judgement"
    STRUCTURAL = "structural"


class Verdict(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    INDETERMINATE = "indeterminate"


class TriageFinding(BaseModel):
    signal: str                                 # signal id, e.g. "secrets"
    rule: str                                   # which rule inside it
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    path: str = ""
    line: int | None = None
    evidence: str = ""                          # verbatim quote from path@commit_sha
    fix_class: FixClass


class SignalResult(BaseModel):
    """One signal's output. `collected` is a Measurement, not a bool: a signal
    that timed out reports not_collected and contributes nothing, which is
    distinguishable from a signal that ran and found nothing (FR-915)."""
    signal: str
    version: int                                # bump invalidates E-46's memo key
    collected: Measurement                      # MEASURED value = finding count
    findings: list[TriageFinding] = Field(default_factory=list)
    metrics: dict[str, Measurement] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _not_collected_has_no_findings(self) -> "SignalResult":
        if (self.collected.state is CollectionState.NOT_COLLECTED
                and self.findings):
            raise ValueError(
                f"{self.signal}: NOT_COLLECTED carries {len(self.findings)} "
                f"finding(s) -- those are findings from a run that did not "
                f"happen. Partial output is UNKNOWN.")
        return self


class Readiness(BaseModel):
    """FR-901's four dimensions. Every value is positive-is-good, so the
    verdict rule is uniform: buildable/runnable/structure_discernible are
    1.0 or 0.0, tests_present is a count."""
    buildable: Measurement
    runnable: Measurement
    tests_present: Measurement
    structure_discernible: Measurement
    verdict: Verdict


class RepoTriage(BaseModel):
    repo_dir: str
    commit_sha: str                             # triage is pinned at a commit
    toolchain: str | None = None                # None is a finding, not an error
    readiness: Readiness
    signals: list[SignalResult] = Field(default_factory=list)


# The four reserved metric keys carrying FR-901's readiness dimensions.
# Exactly ONE signal may report each: build_probe owns buildable/runnable,
# baseline owns tests_present/structure_discernible. A duplicate is FR-902's
# one-implementation rule being broken, so compute_readiness raises rather
# than silently preferring one producer.
M_BUILDABLE = "buildable"
M_RUNNABLE = "runnable"
M_TESTS_PRESENT = "tests_present"
M_STRUCTURE = "structure_discernible"
READINESS_KEYS: tuple[str, ...] = (
    M_BUILDABLE, M_RUNNABLE, M_TESTS_PRESENT, M_STRUCTURE)


def compute_readiness(signals: list[SignalResult]) -> Readiness:
    """The ONLY producer of Verdict (spec D4). No caller sets it, so the
    artifact cannot disagree with its own inputs.

    Any dimension that is not MEASURED -- because a signal reported
    not_collected/unknown, or because no signal reported it at all -- forces
    INDETERMINATE. An unmeasured dimension never reads as READY: that is the
    conflation E-40 removed from SecurityReport, and FR-903 gates the Tier 2
    audit on this verdict.
    """
    reported: dict[str, Measurement] = {}
    for sig in sorted(signals, key=lambda s: s.signal):
        for key, m in sig.metrics.items():
            if key not in READINESS_KEYS:
                continue                      # signals may carry other metrics
            if key in reported:
                raise ValueError(
                    f"readiness key {key!r} reported by more than one signal "
                    f"(second was {sig.signal!r}) -- exactly one signal owns "
                    f"each dimension (FR-902)")
            reported[key] = m

    dims = {
        key: reported.get(key)
        or Measurement.not_collected(f"no signal reported {key}")
        for key in READINESS_KEYS
    }

    if any(m.state is not CollectionState.MEASURED for m in dims.values()):
        verdict = Verdict.INDETERMINATE
    elif all((m.value or 0.0) > 0 for m in dims.values()):
        verdict = Verdict.READY
    else:
        verdict = Verdict.NOT_READY
    return Readiness(**dims, verdict=verdict)
