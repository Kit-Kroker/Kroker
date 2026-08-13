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
C_DATA_SENSITIVITY = "data_sensitivity"          # SS4, computed
C_ENTITY_ACCESS = "entity_access"                # SS4, computed from S3

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
    ScanSignalId.SS4: (C_DATA_SENSITIVITY, C_ENTITY_ACCESS),
    ScanSignalId.QS1: (C_TESTS_PRESENT, C_TEST_LEVELS, C_TEST_MAPPING),
    ScanSignalId.QS2: (C_COVERAGE,),
    ScanSignalId.QS3: (C_TESTABILITY,),
    ScanSignalId.QS4: (C_CI_PRESENT, C_CI_STAGES, C_ENV_DRIFT),
}


def inherited_pending(category: str) -> Measurement:
    """What a COMPUTED activity half puts on a category the INHERITED half
    owns (D7).

    A row must declare every category its signal owes, but an EXTENDED
    signal's activity computes only its own half -- the workflow derives the
    other from RepoTriage and folds it in. This placeholder is what fold_row
    overwrites in the normal path, and what stays, honestly, when triage
    produced no half at all.
    """
    return Measurement.not_collected(
        f"{category}: inherited from triage and folded in by the workflow "
        f"(D7); this row carries the activity's computed half only")


class SecurityObservation(BaseModel):
    """SS1's and SS3's computed half: one security-relevant fact at one path.

    `signal` is carried because the two signals SHARE ScanResult.security and
    _unmeasured_carries_no_payload discriminates a row's own records by
    exactly that attribute -- the same shape S1-S4 use to share `sources`
    (P3-D1).

    `severity_hint`, never `severity`: BrownKit's own rule is that scan emits
    hints and /assess assigns severity (E-49). A field called `severity` would
    invite a consumer to treat a pattern match as a rating.
    """
    signal: ScanSignalId
    category: str
    rule: str
    detail: str
    severity_hint: Literal["info", "low", "medium", "high", "critical"]
    path: str
    line: int | None = None
    evidence: str = ""              # verbatim quote from path@commit_sha
    key: str = ""                   # rule-scoped discriminator (E-44 D3)
    confidence: Confidence

    @model_validator(mode="after")
    def _category_is_owed_by_its_signal(self) -> "SecurityObservation":
        if self.category not in CATEGORIES[self.signal]:
            raise ValueError(
                f"{self.signal.value} observation names category "
                f"{self.category!r}, which it does not owe "
                f"{CATEGORIES[self.signal]} -- CATEGORIES is the one "
                f"declaration")
        return self


def security_identity(o: SecurityObservation) -> str:
    """The identity a delta matches on. Excludes `line`, exactly as
    finding_identity and testability_identity do: a fix landing above an
    observation shifts its line, and a line-keyed identity would report a
    phantom resolved+new pair (E-44 D3)."""
    return f"{o.signal.value}:{o.rule}:{o.path}:{o.key}"


class TestLevel(str, Enum):
    """BrownKit's six levels plus UNKNOWN.

    UNKNOWN is the load-bearing member: a test-shaped file whose level no rule
    decided must not default to `unit`, which would silently inflate the
    unit-test count in a product that sells measurement (FR-915's spirit
    applied to a classification rather than a number).
    """
    UNIT = "unit"
    INTEGRATION = "integration"
    CONTRACT = "contract"
    E2E = "e2e"
    PERFORMANCE = "performance"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class TestFileRecord(BaseModel):
    """QS1's computed half: one test file, its level, and what it covers."""
    path: str
    level: TestLevel
    rule: str                       # the rule that decided the level
    framework: str = ""             # "" when no framework signature matched
    covers: list[str] = Field(default_factory=list)
    mapping_rule: str               # naming_convention | co_location | unmapped
    confidence: Confidence

    @model_validator(mode="after")
    def _mapping_rule_agrees_with_covers(self) -> "TestFileRecord":
        if self.mapping_rule == "unmapped" and self.covers:
            raise ValueError(
                f"{self.path}: mapping_rule=unmapped but covers "
                f"{self.covers} -- a mapping that produced a file is not an "
                f"absent mapping")
        if self.mapping_rule != "unmapped" and not self.covers:
            raise ValueError(
                f"{self.path}: mapping_rule={self.mapping_rule!r} produced no "
                f"covers -- say `unmapped`, so QS2's proxy cannot read an "
                f"empty mapping as a mapping to nothing")
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "TestFileRecord":
        self.covers = sorted(set(self.covers))
        return self


class CoverageRecord(BaseModel):
    """QS2. Never a bare percentage: BrownKit's acceptance gate 5 requires
    every coverage record to carry its source and confidence, and D12 forbids
    running the suite -- so `proxy` is a real and frequent answer here, not an
    edge case."""
    scope: Literal["file", "package"]
    path: str
    covered: Measurement            # percent in [0, 100]
    source: Literal["report", "proxy"]
    tool: str = ""                  # "cobertura" for a report, "" for a proxy
    confidence: Confidence

    @model_validator(mode="after")
    def _source_fields_agree(self) -> "CoverageRecord":
        if self.source == "proxy" and self.confidence is not Confidence.LOW:
            raise ValueError(
                "a proxy coverage record is LOW confidence by construction "
                "(D12) -- tested_files/significant_files is not a measurement "
                "of coverage, and a HIGH-confidence proxy would read as one")
        if self.source == "report" and not self.tool:
            raise ValueError(
                "a report coverage record must name the tool that produced "
                "it -- 'source: <tool>' is BrownKit's own rule")
        return self


class CiStageRecord(BaseModel):
    """QS4's stages. `order` is the position within its workflow file, so a
    reader sees the pipeline's shape without re-parsing it."""
    workflow: str                   # path of the CI file
    stage: str                      # job / stage id
    order: int
    runs_tests: bool
    test_levels: list[TestLevel] = Field(default_factory=list)
    deploys_to: str = ""            # environment name; "" when it does not
    # A required check is a branch-protection setting, not a tracked file, so
    # it is not readable at a pinned commit. not_collected, never False --
    # "this job does not block merges" and "we cannot see what blocks merges"
    # are different facts (FR-915). E-59's app install is what makes it
    # measurable, with no schema change here.
    blocking: Measurement

    @model_validator(mode="after")
    def _levels_only_when_it_tests(self) -> "CiStageRecord":
        if self.test_levels and not self.runs_tests:
            raise ValueError(
                f"{self.stage}: declares test levels but runs_tests is False")
        return self


CiStageRecord.__test__ = False


class EnvironmentRecord(BaseModel):
    """QS4's env_drift (P3-D7): one environment name and where the repository
    declares it. `drifted` is DERIVED from the two booleans, never assigned --
    D8's rule applied one level down."""
    name: str
    in_ci: bool                     # named by a CI job's deploy target
    in_config: bool                 # named by a committed config / env file
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _declared_somewhere(self) -> "EnvironmentRecord":
        if not self.in_ci and not self.in_config:
            raise ValueError(
                f"{self.name!r} is declared nowhere -- an environment no side "
                f"names is not an environment, it is an empty record")
        return self

    @property
    def drifted(self) -> bool:
        return self.in_ci != self.in_config


class ScanUpstream(BaseModel):
    """Everything a signal may read from the signals it declares in
    `consumes` (D10, P3-D4).

    One field per payload kind, so a new dependent signal is a registry edit
    rather than a new activity-input field. `collected` travels beside the
    payloads because an empty list cannot distinguish "the upstream measured
    zero" from "the upstream did not collect" -- the distinction section 5
    requires every wave-2 signal to make, and the reason merge() already takes
    both.
    """
    sources: list[SourceCandidate] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    collected: dict[ScanSignalId, Measurement] = Field(default_factory=dict)

    def measured(self, signal_id: ScanSignalId) -> bool:
        """Whether a consumed signal collected. False when it is absent from
        the map: an upstream that never reported is not one that reported
        nothing."""
        m = self.collected.get(signal_id)
        return m is not None and m.state is CollectionState.MEASURED

    def gap(self, signal_id: ScanSignalId, category: str) -> Measurement:
        """The not_collected a dependent category reports when its input did
        not collect, carrying the upstream's own reason so the assessment says
        WHY and not merely THAT (section 5, D5)."""
        m = self.collected.get(signal_id)
        why = (m.reason if m is not None and m.reason
               else f"{signal_id.value} did not report")
        return Measurement.not_collected(
            f"{category}: depends on {signal_id.value}, which did not "
            f"collect ({why})")


TestLevel.__test__ = False
TestFileRecord.__test__ = False


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


# Which ScanResult field(s) each signal's payload lands in. Declared once so
# _unmeasured_carries_no_payload can check the right field per signal rather
# than a hardcoded pairing in the validator. A TUPLE per signal because QS4
# owns two payloads whose shapes share nothing (P3-D2); SS2 owns none, since
# D12 cut its computed half.
PAYLOAD_FIELD: dict[ScanSignalId, tuple[str, ...]] = {
    ScanSignalId.S1: ("sources",),
    ScanSignalId.S2: ("sources",),
    ScanSignalId.S3: ("sources",),
    ScanSignalId.S4: ("sources",),
    ScanSignalId.S5: ("candidates",),
    ScanSignalId.SS1: ("security",),
    ScanSignalId.SS3: ("security",),
    ScanSignalId.SS4: ("data_sensitivity",),
    ScanSignalId.QS1: ("tests",),
    ScanSignalId.QS2: ("coverage",),
    ScanSignalId.QS3: ("testability",),
    ScanSignalId.QS4: ("ci", "environments"),
}


class SignalOutput(BaseModel):
    """One computed signal's whole output -- the row AND its payload, cached
    as a unit (D10). An activity returns this; the workflow folds in the
    inherited half (D7)."""
    row: ScanSignalResult
    sources: list[SourceCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)
    security: list[SecurityObservation] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    ci: list[CiStageRecord] = Field(default_factory=list)
    environments: list[EnvironmentRecord] = Field(default_factory=list)


class ScanResult(BaseModel):
    signals: list[ScanSignalResult]
    sources: list[SourceCandidate] = Field(default_factory=list)
    candidates: list[ScanCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)
    security: list[SecurityObservation] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    ci: list[CiStageRecord] = Field(default_factory=list)
    environments: list[EnvironmentRecord] = Field(default_factory=list)

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
        for signal_id, field_names in PAYLOAD_FIELD.items():
            row = by_id[signal_id]
            if row.collected.state is CollectionState.MEASURED:
                continue
            for field_name in field_names:
                # A field can hold other signals' records too (S1-S4 share
                # `sources`, SS1+SS3 share `security`), so only this signal's
                # own records are checked.
                mine = [r for r in getattr(self, field_name)
                        if getattr(r, "signal", signal_id) is signal_id]
                if mine:
                    raise ValueError(
                        f"{signal_id.value} is {row.collected.state.value} "
                        f"but carries {len(mine)} record(s) in "
                        f"{field_name!r} -- a signal that did not run has no "
                        f"records; partial output is UNKNOWN")
        return self
