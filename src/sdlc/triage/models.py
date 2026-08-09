"""FR-901/FR-902 (E-41): the triage artifact and its contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as measurement.py and
grounding.py must not: a dependency here would appear as a reviewable import.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
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
    # E-44 D3: rule-scoped discriminator, supplied by the signal when a rule
    # can fire more than once for one path. "" is correct for a rule that
    # fires at most once per path. NEVER derived from `line`: a fix landing
    # above a finding shifts it, and a delta keyed on it would report a
    # phantom resolved+new pair.
    key: str = ""


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

    @model_validator(mode="after")
    def _identities_unique(self) -> "SignalResult":
        """E-44 D3. Two findings with one identity are the same fact reported
        twice: the delta cannot key on them, and the severity tally
        double-counts. Signals collapse them with dedupe_by_identity; this
        catches the case where a new rule forgot to supply `key` at all --
        in the signal that caused it, not in the delta that inherits it."""
        seen: set[str] = set()
        for f in self.findings:
            identity = finding_identity(f)
            if identity in seen:
                raise ValueError(
                    f"{self.signal}: duplicate finding identity {identity!r} "
                    f"-- the rule fires more than once per path and needs a "
                    f"`key` (E-44 D3)")
            seen.add(identity)
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


class ReadinessOverride(BaseModel):
    """FR-903: an audited decision to proceed despite a verdict that is not
    READY (E-42 D1).

    Local and pure -- this module must not import models.py, so GateDecision
    cannot appear here; TriageWorkflow maps one to the other.

    `approved_by` carries GateDecision.decided_by VERBATIM: it is the CLASS of
    decider, so "policy" (gate OFF) and "timeout" (on_timeout=APPROVE) stay
    legible as non-human on the face of the artifact. `reviewer` is the
    operator identity -- optional and self-asserted, the gap FR-1004 exists to
    close. Mirrored rather than hidden: a bundle claiming a named human
    approved a not-ready repository, on a field anyone can set, would be worse
    than one that says "human" and leaves the principal unproven.
    """
    approved_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    reason: str
    decided_at: datetime
    gate_round: int


class RepoTriage(BaseModel):
    repo_dir: str
    commit_sha: str                             # triage is pinned at a commit
    toolchain: str | None = None                # None is a finding, not an error
    readiness: Readiness
    override: ReadinessOverride | None = None
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


def finding_identity(f: TriageFinding) -> str:
    """E-44 D3. The identity a before/after delta matches on.

    Sited here rather than in delta.py because SignalResult's uniqueness
    validator needs it, and delta.py imports this module -- the other
    direction would close an import cycle.
    """
    return f"{f.signal}:{f.rule}:{f.path}:{f.key}"


def evidence_key(text: str) -> str:
    """A short stable discriminator for matched text.

    Used by rules whose only natural discriminator IS the matched line
    (misconfig's regex rules, secrets' provider rules). Hashed rather than
    stored raw so an identity is bounded in length and readable in a report;
    the raw line is already carried in `evidence`, so this hides nothing that
    is not disclosed elsewhere.
    """
    return hashlib.sha256(
        text.encode("utf-8", "replace")).hexdigest()[:12]


def dedupe_by_identity(findings: list[TriageFinding]) -> list[TriageFinding]:
    """Keep the first finding for each identity, in order.

    Two findings sharing an identity are the same fact reported twice -- the
    same credential on two lines of one file, the same `DEBUG = True` in two
    places. Reporting both double-counts the severity tally, and the E-44
    delta cannot key on them. Collapsing to the first occurrence is the
    behaviour SignalResult's validator (Task 2) then enforces.
    """
    seen: set[str] = set()
    out: list[TriageFinding] = []
    for f in findings:
        identity = finding_identity(f)
        if identity in seen:
            continue
        seen.add(identity)
        out.append(f)
    return out
