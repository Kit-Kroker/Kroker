"""FR-912 (E-46): the scan phase artifact and its contracts.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py, capability/models.py and assessment/models.py must not: a
dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement


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


class Sensitivity(str, Enum):
    PII = "pii"
    FINANCIAL = "financial"
    AUTHENTICATION = "authentication"
    HEALTH = "health"
    REGULATORY = "regulatory"


class SensitivityRecord(BaseModel):
    """SS4. Classifies an entity, not a file: the question E-49 asks is which
    capability handles regulated data."""
    classification: Sensitivity
    entity: str
    origin: Literal["table", "model", "dto"]
    fields: list[str]
    # S3 entry points reading or writing the entity, by local_id. Empty when
    # S3 reported not_collected -- the owing category's reason states that,
    # so this must never be read as "no entry point touches PII".
    accessed_by: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rule: str
    confidence: Confidence


class TestabilityFinding(BaseModel):
    """QS3. Carries TriageFinding's `evidence` and `key` semantics because a
    testability blocker is a per-capability finding E-49 scores and E-53 may
    seed a fix run from, so it needs the same delta-stable identity.

    `severity` is BrownKit's three-valued scale, not TriageFinding's four:
    blocks/impedes/smell answers a different question than
    critical/high/medium/low, and collapsing them loses what FR-916 needs.
    """
    severity: Literal["blocks", "impedes", "smell"]
    pattern: str                    # "static-clock-access"
    detail: str
    recommended_seam: str
    path: str
    line: int | None = None
    evidence: str = ""              # verbatim quote from path@commit_sha
    key: str = ""                   # rule-scoped discriminator (E-44 D3)


# pytest must not collect these -- their names begin with "test" because the
# domain is "testability", not because they are tests (pytest honours __test__).
TestabilityFinding.__test__ = False


def testability_identity(f: TestabilityFinding) -> str:
    """The identity a delta matches on. Deliberately excludes `line`, exactly
    as triage's finding_identity does."""
    return f"QS3:{f.pattern}:{f.path}:{f.key}"


testability_identity.__test__ = False


# --- Category keys (D3) -------------------------------------------------
# A signal's coverage is tracked per category because ScanSignalResult
# carries ONE `collected` and a signal like SS1 genuinely has an inherited
# half and a computed half. Declared here, beside the artifact, so the
# registry and the row cannot disagree about what a signal owes.

C_PACKAGES = "packages"                          # S1
C_SCHEMA = "schema_clusters"                     # S2
C_BACKEND_ENTRY = "backend_entry_points"         # S3
C_FRONTEND_ENTRY = "frontend_entry_points"       # S4
C_MERGE = "candidate_merge"                      # S5

C_CREDENTIAL_STORAGE = "credential_storage"      # SS1, inherited
C_AUTHN_AUTHZ = "authn_authz"                    # SS1, inherited
C_TLS = "tls_enforcement"                        # SS1, computed
C_INPUT_VALIDATION = "input_validation"          # SS1, computed
C_DIRECT_DEPS = "direct_dependencies"            # SS2, inherited
C_FRAMEWORK_DEFAULTS = "framework_defaults"      # SS3, inherited
C_EXPOSED_PORTS = "exposed_ports"                # SS3, computed
C_ENV_DIVERGENCE = "env_divergence"              # SS3, computed
C_DB_SECURITY = "db_security"                    # SS3, computed
C_LOG_MASKING = "log_masking"                    # SS3, computed
C_DATA_SENSITIVITY = "data_sensitivity"          # SS4

C_TESTS_PRESENT = "tests_present"                # QS1, inherited
C_TEST_LEVELS = "test_levels"                    # QS1, computed
C_TEST_MAPPING = "test_mapping"                  # QS1, computed
C_COVERAGE = "coverage"                          # QS2
C_TESTABILITY = "testability"                    # QS3
C_CI_PRESENT = "ci_present"                      # QS4, inherited
C_CI_STAGES = "ci_stages"                        # QS4, computed
C_ENV_DRIFT = "env_drift"                        # QS4, computed

CATEGORIES: dict[ScanSignalId, tuple[str, ...]] = {
    ScanSignalId.S1: (C_PACKAGES,),
    ScanSignalId.S2: (C_SCHEMA,),
    ScanSignalId.S3: (C_BACKEND_ENTRY,),
    ScanSignalId.S4: (C_FRONTEND_ENTRY,),
    ScanSignalId.S5: (C_MERGE,),
    ScanSignalId.SS1: (C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ, C_TLS,
                       C_INPUT_VALIDATION),
    ScanSignalId.SS2: (C_DIRECT_DEPS,),
    ScanSignalId.SS3: (C_FRAMEWORK_DEFAULTS, C_EXPOSED_PORTS,
                       C_ENV_DIVERGENCE, C_DB_SECURITY, C_LOG_MASKING),
    ScanSignalId.SS4: (C_DATA_SENSITIVITY,),
    ScanSignalId.QS1: (C_TESTS_PRESENT, C_TEST_LEVELS, C_TEST_MAPPING),
    ScanSignalId.QS2: (C_COVERAGE,),
    ScanSignalId.QS3: (C_TESTABILITY,),
    ScanSignalId.QS4: (C_CI_PRESENT, C_CI_STAGES, C_ENV_DRIFT),
}


class InheritedProducer(BaseModel):
    """D2. Which producer already recorded this fact, and which findings of
    its this row cites. Findings are cited, never copied: two copies in the
    FR-921 bundle, and a copy re-labelled with a scan signal id would break
    the finding_identity keying E-44's delta depends on.
    """
    producer: str                   # "triage:secrets"
    version: int                    # the producer's declared version, PINNED
    finding_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _canonicalize(self) -> "InheritedProducer":
        self.finding_ids = sorted(set(self.finding_ids))
        return self


class ScanSignalResult(BaseModel):
    """One signal's status row. The payload lives on ScanResult beside it,
    exactly as Readiness lives beside RepoTriage.signals."""
    signal: ScanSignalId
    family: SignalFamily
    version: int
    source: SignalSource
    collected: Measurement          # MEASURED value = record count
    categories: dict[str, Measurement] = Field(default_factory=dict)
    producer: InheritedProducer | None = None

    @model_validator(mode="after")
    def _producer_matches_source(self) -> "ScanSignalResult":
        if self.source is SignalSource.COMPUTED:
            if self.producer is not None:
                raise ValueError(
                    f"{self.signal.value}: source=computed carries a producer "
                    f"-- a signal this phase computed inherits nothing (D2)")
        elif self.producer is None:
            raise ValueError(
                f"{self.signal.value}: source={self.source.value} requires a "
                f"producer -- an inherited fact must name what recorded it "
                f"(D2)")
        return self

    @model_validator(mode="after")
    def _declares_every_category_it_owes(self) -> "ScanSignalResult":
        owed = set(CATEGORIES[self.signal])
        got = set(self.categories)
        if missing := owed - got:
            raise ValueError(
                f"{self.signal.value}: missing category/categories "
                f"{sorted(missing)} -- a signal reports every category it "
                f"owes, so an unreported one cannot pass as absent")
        if undeclared := got - owed:
            raise ValueError(
                f"{self.signal.value}: undeclared category/categories "
                f"{sorted(undeclared)} -- CATEGORIES is the one declaration")
        return self

    @model_validator(mode="after")
    def _family_matches_its_id(self) -> "ScanSignalResult":
        if self.family is not family_of(self.signal):
            raise ValueError(
                f"{self.signal.value}: family {self.family.value!r} "
                f"contradicts the id prefix")
        return self


# Which ScanResult field each signal's payload lands in. Declared once so
# _unmeasured_carries_no_payload can check the right field per signal rather
# than a hardcoded pairing in the validator.
PAYLOAD_FIELD: dict[ScanSignalId, str] = {
    ScanSignalId.S1: "sources",
    ScanSignalId.S2: "sources",
    ScanSignalId.S3: "sources",
    ScanSignalId.S4: "sources",
    ScanSignalId.S5: "candidates",
    ScanSignalId.SS4: "data_sensitivity",
    ScanSignalId.QS3: "testability",
}


class SignalOutput(BaseModel):
    """One computed signal's whole output -- the row AND its payload, cached
    as a unit (D10). An activity returns this; the workflow folds in the
    inherited half (D7)."""
    row: ScanSignalResult
    sources: list[SourceCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)


class ScanResult(BaseModel):
    signals: list[ScanSignalResult]
    sources: list[SourceCandidate] = Field(default_factory=list)
    candidates: list[ScanCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _signals_are_the_whole_set(self) -> "ScanResult":
        got = tuple(s.signal for s in self.signals)
        if got != SCAN_ORDER:
            raise ValueError(
                f"signals must be the whole set in order -- expected "
                f"{[s.value for s in SCAN_ORDER]}, got "
                f"{[s.value for s in got]}")
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "ScanResult":
        by_id = {s.signal: s for s in self.signals}
        for signal_id, field_name in PAYLOAD_FIELD.items():
            row = by_id[signal_id]
            if row.collected.state is CollectionState.MEASURED:
                continue
            # The field can hold other signals' records too (S1-S4 all land
            # in `sources`), so only this signal's own records are checked.
            payload = getattr(self, field_name)
            mine = [r for r in payload
                    if getattr(r, "signal", signal_id) is signal_id]
            if mine:
                raise ValueError(
                    f"{signal_id.value} is {row.collected.state.value} but "
                    f"carries {len(mine)} record(s) in {field_name!r} -- a "
                    f"signal that did not run has no records; partial output "
                    f"is UNKNOWN")
        return self
