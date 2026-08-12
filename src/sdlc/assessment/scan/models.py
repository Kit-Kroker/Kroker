"""FR-912 (E-46): the scan phase artifact and its contracts.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py, capability/models.py and assessment/models.py must not: a
dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ...measurement import Measurement


class ScanSignalId(str, Enum):
    """BrownKit's scan signal ids, kept verbatim: they are the traceable
    contract with the source methodology, and renaming them would make every
    cross-reference to `scan.md` a translation step.

    Declaration order IS the order (see SCAN_ORDER) -- a hand-written tuple
    beside the enum is a second registry, exactly as PHASE_ORDER records.
    """
    S1 = "S1"       # package structure
    S2 = "S2"       # database schema clusters
    S3 = "S3"       # backend entry points
    S4 = "S4"       # frontend entry points
    S5 = "S5"       # cross-source merge and confidence
    SS1 = "SS1"     # static security
    SS2 = "SS2"     # dependency vulnerabilities
    SS3 = "SS3"     # configuration and infrastructure
    SS4 = "SS4"     # data sensitivity
    QS1 = "QS1"     # test inventory
    QS2 = "QS2"     # coverage
    QS3 = "QS3"     # testability
    QS4 = "QS4"     # environment and CI


SCAN_ORDER: tuple[ScanSignalId, ...] = tuple(ScanSignalId)


class SignalFamily(str, Enum):
    CAPABILITY = "capability"
    SECURITY = "security"
    QA = "qa"


def family_of(signal_id: ScanSignalId) -> SignalFamily:
    """Derived from the id prefix rather than declared per signal: the prefix
    IS the family in BrownKit's scheme, and a declaration could disagree."""
    if signal_id.value.startswith("QS"):
        return SignalFamily.QA
    if signal_id.value.startswith("SS"):
        return SignalFamily.SECURITY
    return SignalFamily.CAPABILITY


class SignalSource(str, Enum):
    """D2. INHERITED is narrow: the fact is already recorded in an artifact
    this assessment holds (Assessment.triage). Reusing a parser is code reuse,
    not inheritance."""
    COMPUTED = "computed"
    INHERITED = "inherited"
    EXTENDED = "extended"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence_from(signals: Iterable[ScanSignalId]) -> Confidence:
    """S5's rule (D8): 3+ distinct source SIGNALS high, 2 medium, else low.

    Distinct signals, not distinct candidates -- two S1 groupings are one
    source's opinion twice, which is FR-912's "never the depth of one source".
    Total by construction so it is never the thing that raises; a candidate
    with no sources is refused by ScanCandidate instead.
    """
    n = len(set(signals))
    if n >= 3:
        return Confidence.HIGH
    if n == 2:
        return Confidence.MEDIUM
    return Confidence.LOW


class MemberKind(str, Enum):
    """What a candidate is made of. The value set is chosen so every
    CapabilityFingerprint tier has members that can populate it, making
    E-48's MemberKind -> SignalTier mapping total (D13).

    That mapping is deliberately NOT here: E-47a's pipeline is
    scan -> discover proposes boundaries -> fingerprint + resolve, so siting a
    capability-identity fact in the scan phase would put it two stages early.
    """
    HTTP_ROUTE = "http_route"
    CLI_COMMAND = "cli_command"
    DB_TABLE = "db_table"
    QUEUE_TOPIC = "queue_topic"
    GRPC_METHOD = "grpc_method"
    SCHEDULED_JOB = "scheduled_job"
    FRONTEND_ROUTE = "frontend_route"
    ENTITY_NAME = "entity_name"
    TEST_NAME = "test_name"
    EXPORTED_SYMBOL = "exported_symbol"
    PACKAGE_PATH = "package_path"
    FILE_PATH = "file_path"


def signal_of(local_id: str) -> ScanSignalId:
    """The signal that minted a local id. Parsed rather than stored beside it,
    so the id and its owner cannot disagree."""
    head, _, rest = local_id.partition("-")
    if not rest:
        raise ValueError(
            f"malformed local_id {local_id!r} -- expected '<signal>-<slug>'")
    try:
        return ScanSignalId(head)
    except ValueError:
        raise ValueError(
            f"malformed local_id {local_id!r} -- {head!r} is not a signal id"
        ) from None


class CandidateMember(BaseModel):
    model_config = {"frozen": True}
    kind: MemberKind
    value: str                      # "POST /api/payments", "orders"
    path: str = ""
    line: int | None = None

    def sort_key(self) -> tuple[str, str, str, int]:
        return (self.kind.value, self.value, self.path, self.line or 0)


class EvidenceRef(BaseModel):
    model_config = {"frozen": True}
    path: str
    lines: str = ""                 # "42-78"; "" means whole file


class SourceCandidate(BaseModel):
    """One candidate as seen by ONE source signal (S1-S4). Not a capability:
    /discover (E-48) decides that, and E-47a assigns the BC-NNN id.

    (rule, detail) is TriageFinding's pair, carried for the same reason -- the
    rule that produced a confidence rating is what makes it auditable. S1's
    domain/generic/layer classification is expressed as the rule that fired
    (s1_domain_term, s1_generic_name, s1_layer_name) rather than a boolean,
    because E-48's "delivery channels and deployment boundaries are not
    capabilities" guardrail needs the distinction, not only its outcome.
    """
    signal: ScanSignalId
    local_id: str                   # "S3-payments"
    name: str
    rule: str
    detail: str
    confidence_contribution: Confidence
    members: list[CandidateMember]
    evidence: list[EvidenceRef] = Field(default_factory=list)
    metrics: dict[str, Measurement] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _local_id_declares_its_signal(self) -> "SourceCandidate":
        if signal_of(self.local_id) is not self.signal:
            raise ValueError(
                f"local_id {self.local_id!r} is not prefixed by its signal "
                f"{self.signal.value!r} -- signal_of() must agree with the "
                f"field, or a merged candidate miscounts its sources (D8)")
        return self

    @model_validator(mode="after")
    def _has_members(self) -> "SourceCandidate":
        if not self.members:
            raise ValueError(
                "a SourceCandidate needs at least one member -- an empty "
                "candidate is a silently-empty extraction, which is the "
                "conflation D5 forbids")
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "SourceCandidate":
        # NFR-10: discovery order must not change the artifact.
        self.members = sorted(set(self.members), key=CandidateMember.sort_key)
        self.evidence = sorted(set(self.evidence),
                              key=lambda e: (e.path, e.lines))
        return self


class ScanCandidate(BaseModel):
    """S5's merge: one distinct candidate corroborated across sources.

    candidate_id is local to ONE assessment. BC-NNN is E-47a's surrogate key,
    allocated after discover -- the two look alike, and conflating them would
    mint capability identity in the wrong phase.
    """
    candidate_id: str               # "C-01"
    name: str
    sources: list[str]              # SourceCandidate.local_id values
    confidence: Confidence          # DERIVED (D8)
    members: list[CandidateMember]
    possible_duplicate_of: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_sources(self) -> "ScanCandidate":
        if not self.sources:
            raise ValueError(
                "a ScanCandidate needs at least one source -- it is a merge "
                "of source candidates, and a merge of nothing has no evidence")
        return self

    @model_validator(mode="after")
    def _confidence_is_derived(self) -> "ScanCandidate":
        expected = confidence_from(signal_of(s) for s in self.sources)
        if self.confidence is not expected:
            raise ValueError(
                f"confidence {self.confidence.value!r} does not match the "
                f"derived {expected.value!r} for sources {self.sources} -- "
                f"confidence is derived from the count of DISTINCT source "
                f"signals, never assigned (D8)")
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "ScanCandidate":
        self.sources = sorted(set(self.sources))
        self.members = sorted(set(self.members), key=CandidateMember.sort_key)
        self.possible_duplicate_of = sorted(set(self.possible_duplicate_of))
        return self
