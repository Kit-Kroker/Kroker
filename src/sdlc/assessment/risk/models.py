"""FR-916 (E-49): the UnifiedRiskMap contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as
assessment/models.py, triage/models.py and discover/map.py must not: a
dependency here would appear as a reviewable import.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...measurement import CollectionState, Measurement
from ..scan.models import EvidenceRef

MAX_DRIVERS = 3

# RD10's four cross-capability families, named ONCE. SystemRisk's `truncated`
# validator and crosscap's assembly both read these, and two lists of family
# names that agree by coincidence is the defect ADR-6's duplicate role lists
# already cost this codebase.
FAM_CASCADES = "cascades"
FAM_ESCALATIONS = "escalation_paths"
FAM_SHARED = "shared_vulnerabilities"
FAM_BOUNDARIES = "trust_boundaries"
SYSTEM_FAMILIES: tuple[str, ...] = tuple(sorted(
    (FAM_CASCADES, FAM_ESCALATIONS, FAM_SHARED, FAM_BOUNDARIES)))

# Supporting file edges kept on one projected capability edge. Declared HERE
# because CapabilityEdge's validator enforces it and models.py may not import
# rules.py (rules.py imports models.py). models.py therefore joins
# RULE_MODULES below: it already carried MAX_DRIVERS unhashed, which is a
# stale-cache hole of exactly the kind E-46's D10 records.
EDGE_EVIDENCE_MAX = 3


class RiskSource(str, Enum):
    BASELINE = "baseline"       # the deterministic rule (plan 1)
    PROPOSER = "proposer"       # dispositioned by the model (plan 2)


class Factor(BaseModel):
    """One input to a composite, with its own Measurement.

    The Measurement is per-factor rather than per-composite because that is
    what makes `partial` derivable (RD3): a composite whose factors each
    carry their own collection state cannot claim a partiality its factors
    contradict.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str
    value: Measurement
    weight: float = 1.0

    @property
    def collected(self) -> bool:
        return self.value.state is CollectionState.MEASURED


class Driver(BaseModel):
    """FR-916's driver as a typed reference to a factor that exists (RD9).

    The source schema guards drivers with a minimum string length, because a
    model-authored driver is prose and length is the only property prose
    admits. Here the composite is computed, so a driver names a factor key
    and carries its contribution -- a generic label is unrepresentable rather
    than merely improbable.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    factor_key: str
    value: float
    contribution: float


class Composite(BaseModel):
    """A score over factors, or the reason it is not one.

    `is_partial` is a PROPERTY, never a field: CollectionState has three
    members and adding a fourth would change a type CoverageReport,
    SecurityReport, triage, scan and discover all share, for one consumer's
    need (RD3). Partiality is a fact about the factors, so it is read from
    them.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    value: Measurement
    factors: tuple[Factor, ...] = ()
    drivers: tuple[Driver, ...] = ()

    @property
    def collected_factors(self) -> tuple[Factor, ...]:
        return tuple(f for f in self.factors if f.collected)

    @property
    def is_partial(self) -> bool:
        """Some collected, some not. All-or-nothing is not partial."""
        got = len(self.collected_factors)
        return 0 < got < len(self.factors)

    @model_validator(mode="after")
    def _factors_are_sorted(self) -> "Composite":
        keys = [f.key for f in self.factors]
        if keys != sorted(keys):
            raise ValueError(
                f"factors must be sorted by key, got {keys} -- a producer "
                f"emitting discovery order is an NFR-10 determinism bug, and "
                f"repairing it here would hide that bug")
        return self

    @model_validator(mode="after")
    def _measured_means_every_factor_collected(self) -> "Composite":
        if self.value.state is CollectionState.MEASURED:
            missing = [f.key for f in self.factors if not f.collected]
            if missing:
                raise ValueError(
                    f"composite is MEASURED but factor(s) {missing} did not "
                    f"collect -- a number over a subset of its specified "
                    f"factors is the conflation FR-915 exists to prevent")
        return self

    @model_validator(mode="after")
    def _drivers_need_a_collected_factor(self) -> "Composite":
        """RD9's third case: no factor collected means no drivers."""
        if self.drivers and not self.collected_factors:
            raise ValueError(
                "drivers were supplied but no collected factor exists -- "
                "_unmeasured_carries_no_payload")
        if len(self.drivers) > MAX_DRIVERS:
            raise ValueError(
                f"at most three drivers (FR-916), got {len(self.drivers)}")
        keys = {f.key for f in self.factors}
        for d in self.drivers:
            if d.factor_key not in keys:
                raise ValueError(
                    f"driver names no factor: {d.factor_key!r} is not among "
                    f"{sorted(keys)}")
        return self


class Criticality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CriticalityRating(BaseModel):
    """An optional level plus a Measurement, rather than a Criticality with an
    UNKNOWN member: an UNKNOWN member would be a second way to say
    not_collected, and two registries for one fact is the defect this codebase
    has paid for more than once."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    level: Criticality | None = None
    collected: Measurement

    @model_validator(mode="after")
    def _level_matches_collection(self) -> "CriticalityRating":
        measured = self.collected.state is CollectionState.MEASURED
        if measured and self.level is None:
            raise ValueError("collected criticality must carry a level")
        if not measured and self.level is not None:
            raise ValueError(
                f"criticality did not collect but carries level "
                f"{self.level.value!r} -- _unmeasured_carries_no_payload")
        return self


class ControlFamily(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    ENCRYPTION = "encryption"


class ControlState(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"


class ControlCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    family: ControlFamily
    state: ControlState | None = None
    collected: Measurement
    evidence: tuple[EvidenceRef, ...] = ()
    rule: str
    rationale: str = ""
    source: RiskSource = RiskSource.BASELINE

    @model_validator(mode="after")
    def _state_matches_collection(self) -> "ControlCoverage":
        measured = self.collected.state is CollectionState.MEASURED
        if measured and self.state is None:
            raise ValueError("collected control coverage must carry a state")
        if not measured and self.state is not None:
            raise ValueError(
                f"{self.family.value} did not collect but carries state "
                f"{self.state.value!r} -- _unmeasured_carries_no_payload")
        return self


class StrideCategory(str, Enum):
    SPOOFING = "spoofing"
    TAMPERING = "tampering"
    REPUDIATION = "repudiation"
    INFORMATION_DISCLOSURE = "information_disclosure"
    DENIAL_OF_SERVICE = "denial_of_service"
    ELEVATION_OF_PRIVILEGE = "elevation_of_privilege"


class ThreatAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    category: StrideCategory
    applicable: bool
    rationale: str
    vulnerability_keys: tuple[str, ...] = ()
    source: RiskSource = RiskSource.BASELINE

    @model_validator(mode="after")
    def _rationale_is_required(self) -> "ThreatAssessment":
        if not self.rationale.strip():
            raise ValueError(
                f"{self.category.value} needs a rationale -- FR-916 requires "
                f"an explicit one even when the category does not apply")
        return self


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityClass(str, Enum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    POTENTIAL = "potential"


class Vulnerability(BaseModel):
    """`key` IS security_identity(observation) -- no new identity scheme, so
    E-54's delta and E-53's seeds match on a key that already exists and is
    line-excluding."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str
    classification: VulnerabilityClass
    severity: Severity
    stride_category: StrideCategory
    path: str
    line: int | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    # P2-D6: a classification with no stated basis is the self-asserted shape
    # E-51's acceptance criteria exist to refuse. Empty on a BASELINE row,
    # which asserts nothing beyond "the scan matched a pattern here".
    rationale: str = ""
    source: RiskSource


class CapabilityEdge(BaseModel):
    """RD10's projection: one capability -> capability dependency, plus the
    file edges that support it.

    Deliberately NOT stored on the artifact. It is the intermediate the four
    families are computed over, and persisting it would put a dense O(n^2)
    structure in a bundle a human reads.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_bc_id: str
    target_bc_id: str
    weight: int = 1
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _an_edge_joins_two_capabilities(self) -> "CapabilityEdge":
        if self.source_bc_id == self.target_bc_id:
            raise ValueError(
                f"{self.source_bc_id} edges to itself -- an intra-capability "
                f"edge is not a cross-capability fact, and dropping it at the "
                f"projection is what keeps that true of every consumer")
        if self.weight < 1:
            raise ValueError(
                "an edge with no supporting file edge is not an edge")
        if len(self.evidence) > EDGE_EVIDENCE_MAX:
            raise ValueError(
                f"at most {EDGE_EVIDENCE_MAX} supporting reference(s), got "
                f"{len(self.evidence)}")
        return self


class SharedVulnerability(BaseModel):
    """A weakness CLASS recurring across capabilities (RD10).

    The join key is `(signal, rule, key)` -- coarser than `Vulnerability.key`
    (= security_identity), which includes `path` and is therefore right for
    the per-instance identity E-54's delta and E-53's seeds match on. Both
    keys are on the artifact and answer different questions.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    weakness_class: str
    signal: str
    rule: str
    key: str = ""
    bc_ids: tuple[str, ...]
    vulnerability_keys: tuple[str, ...]
    severity: Severity

    @model_validator(mode="after")
    def _shared_means_at_least_two_capabilities(self) -> "SharedVulnerability":
        if len(self.bc_ids) < 2:
            raise ValueError(
                f"{self.weakness_class!r} names {list(self.bc_ids)} -- a class "
                f"carried by one capability is not shared, and emitting it "
                f"would make 'shared' mean 'present'")
        if list(self.bc_ids) != sorted(set(self.bc_ids)):
            raise ValueError(
                f"bc_ids {list(self.bc_ids)} are not sorted and deduped -- a "
                f"producer emitting discovery order is an NFR-10 bug, and "
                f"repairing it here would hide that")
        if list(self.vulnerability_keys) != sorted(set(self.vulnerability_keys)):
            raise ValueError(
                f"vulnerability_keys {list(self.vulnerability_keys)} are not "
                f"sorted and deduped")
        if not self.vulnerability_keys:
            raise ValueError(
                "a shared weakness names no vulnerability row -- FR-918's "
                "cross-reference integrity starts at the producer")
        return self


class Cascade(BaseModel):
    """A bounded reachability path from a high-security-composite capability
    (RD10). One path per (origin, reached) pair -- the shortest -- because
    enumerating every simple path is exponential on a dense graph and is not
    what a reader of the FR-921 bundle can act on."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    origin: str
    path: tuple[str, ...]

    @property
    def impacted(self) -> str:
        return self.path[-1]

    @property
    def depth(self) -> int:
        return len(self.path) - 1

    @model_validator(mode="after")
    def _the_path_starts_at_its_origin(self) -> "Cascade":
        if len(self.path) < 2:
            raise ValueError(
                f"a cascade needs at least one hop, got {list(self.path)} -- "
                f"a capability does not cascade into itself")
        if self.path[0] != self.origin:
            raise ValueError(
                f"path {list(self.path)} does not start at origin "
                f"{self.origin!r}")
        if len(set(self.path)) != len(self.path):
            raise ValueError(
                f"path {list(self.path)} repeats a capability -- a cycle is "
                f"not a cascade, and emitting one would double-count impact")
        return self


class BoundaryVerdict(str, Enum):
    """RD10's disposition over a candidate edge. UNCLEAR is the baseline's
    own value and a legitimate proposer answer: 'we looked and cannot tell'
    is a finding, and forcing a binary would manufacture one."""
    WEAK = "weak"
    SOUND = "sound"
    UNCLEAR = "unclear"


class TrustBoundary(BaseModel):
    """A candidate edge whose endpoints differ in criticality or sensitivity
    exposure. `rule` is why code enumerated it; `verdict` is what judged it."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_bc_id: str
    target_bc_id: str
    rule: str
    verdict: BoundaryVerdict = BoundaryVerdict.UNCLEAR
    rationale: str
    evidence: tuple[EvidenceRef, ...] = ()
    source: RiskSource = RiskSource.BASELINE

    @model_validator(mode="after")
    def _rationale_is_required(self) -> "TrustBoundary":
        if not self.rationale.strip():
            raise ValueError(
                f"{self.source_bc_id}->{self.target_bc_id} needs a rationale "
                f"-- an unexplained verdict is unreviewable")
        return self


class ChainVerdict(str, Enum):
    """RD10's disposition over a candidate escalation chain."""
    PLAUSIBLE = "plausible"
    REFUTED = "refuted"
    UNCLEAR = "unclear"


class EscalationPath(BaseModel):
    """A bounded path from an externally-reachable capability whose
    authentication control is absent or uncollected, to one handling
    sensitive entities.

    KNOWN LIMIT (RD10): these chains are AUTHENTICATION-gated, not
    AUTHORIZATION-gated, because RD5 leaves Authorization with no scan
    source. A narrower claim than FR-916's wording implies, stated here
    rather than discovered by a customer.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    path: tuple[str, ...]
    rule: str
    verdict: ChainVerdict = ChainVerdict.UNCLEAR
    rationale: str
    evidence: tuple[EvidenceRef, ...] = ()
    source: RiskSource = RiskSource.BASELINE

    @property
    def path_id(self) -> str:
        """Derived from the path, never stored: an id that could disagree
        with the path it names is two claims."""
        return "->".join(self.path)

    @property
    def entry_bc_id(self) -> str:
        return self.path[0]

    @property
    def target_bc_id(self) -> str:
        return self.path[-1]

    @model_validator(mode="after")
    def _a_chain_is_at_least_one_hop(self) -> "EscalationPath":
        if len(self.path) < 2:
            raise ValueError(
                f"an escalation chain needs at least one hop, got "
                f"{list(self.path)}")
        if len(set(self.path)) != len(self.path):
            raise ValueError(
                f"path {list(self.path)} repeats a capability -- a cycle is "
                f"not an escalation chain")
        if not self.rationale.strip():
            raise ValueError(
                f"{'->'.join(self.path)} needs a rationale -- an unexplained "
                f"verdict is unreviewable")
        return self


class ProposedThreat(BaseModel):
    """One STRIDE applicability judgment for one capability.

    Carries no `source` and no `severity`: provenance is code's to stamp
    (E-48 DD1) and severity is a table (RD4). A model able to set either
    could label a hallucinated judgment as a computed baseline, or overrule
    the table the FR-921 bundle publishes.
    """
    bc_id: str
    category: StrideCategory
    applicable: bool
    rationale: str
    vulnerability_keys: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    quote: str = ""

    @property
    def row_id(self) -> str:
        """Prefixed so one flat verification pass over the three families
        cannot collide a bc_id with a vulnerability key."""
        return f"threat:{self.bc_id}:{self.category.value}"


class ProposedVulnerability(BaseModel):
    """A classification and a STRIDE linkage for a vulnerability that already
    exists. `key` names a baseline row; it never creates one."""
    key: str
    classification: VulnerabilityClass
    stride_category: StrideCategory
    rationale: str
    evidence: tuple[EvidenceRef, ...] = ()
    quote: str = ""

    @property
    def row_id(self) -> str:
        return f"vuln:{self.key}"


class ProposedControl(BaseModel):
    """A control state for a family whose scan source COLLECTED. A family
    with no source is refused downstream (P2-D4): flipping "we have no signal
    for this" into "present" is the most expensive over-claim the artifact
    admits."""
    bc_id: str
    family: ControlFamily
    state: ControlState
    rationale: str
    evidence: tuple[EvidenceRef, ...] = ()
    quote: str = ""

    @property
    def row_id(self) -> str:
        return f"control:{self.bc_id}:{self.family.value}"


class RiskProposal(BaseModel):
    """The proposer's output_type. Three disposition families and nothing
    else -- a proposer that could return a CapabilityRisk would author the
    number FR-917 gates on (RD1)."""
    threats: list[ProposedThreat] = Field(default_factory=list)
    vulnerabilities: list[ProposedVulnerability] = Field(default_factory=list)
    controls: list[ProposedControl] = Field(default_factory=list)

    @property
    def rows(self) -> tuple[ProposedThreat | ProposedVulnerability
                            | ProposedControl, ...]:
        """Every row, for one verification pass over one fabrication rate."""
        return (*self.threats, *self.vulnerabilities, *self.controls)


class RiskVerification(BaseModel):
    """RD6's result, typed for the Temporal boundary. Mirrors
    discover/verify.py's RefVerification; the row-level logic is the shared
    one in assessment/verification.py."""
    proposal: RiskProposal = Field(default_factory=RiskProposal)
    refusals: dict[str, tuple[str, str]] = {}
    total_references: int = 0
    unresolved_references: int = 0

    @property
    def fabrication_rate(self) -> float:
        if self.total_references == 0:
            return 0.0
        return self.unresolved_references / self.total_references


class SystemRisk(BaseModel):
    """RD10's four families. Plan 1 lands the contract with every family
    reporting not_collected naming plan 3, so the artifact is honest between
    plans exactly as PHASE_OWNER makes the workflow honest between items."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    shared_vulnerabilities: Measurement = Measurement.not_collected(
        "cross-capability analysis not implemented (E-49 plan 3)")
    cascades: Measurement = Measurement.not_collected(
        "cross-capability analysis not implemented (E-49 plan 3)")
    trust_boundaries: Measurement = Measurement.not_collected(
        "cross-capability analysis not implemented (E-49 plan 3)")
    escalation_paths: Measurement = Measurement.not_collected(
        "cross-capability analysis not implemented (E-49 plan 3)")


class CapabilityRisk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bc_id: str
    criticality: CriticalityRating
    threats: tuple[ThreatAssessment, ...]
    vulnerabilities: tuple[Vulnerability, ...] = ()
    controls: tuple[ControlCoverage, ...]
    security: Composite
    qa: Composite
    unified: Composite

    @model_validator(mode="after")
    def _structurally_complete(self) -> "CapabilityRisk":
        got_t = tuple(t.category for t in self.threats)
        if got_t != tuple(StrideCategory):
            raise ValueError(
                f"{self.bc_id}: threats must be all six STRIDE categories in "
                f"declaration order, got {[c.value for c in got_t]} -- "
                f"omission must never come to mean 'not applicable'")
        got_c = tuple(c.family for c in self.controls)
        if got_c != tuple(ControlFamily):
            raise ValueError(
                f"{self.bc_id}: controls must be all five control families in "
                f"declaration order, got {[f.value for f in got_c]}")
        return self


class UnifiedRiskMap(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capabilities: tuple[CapabilityRisk, ...] = ()
    system: SystemRisk = SystemRisk()
    collected: Measurement
    # RD7: the judgment layer's own collection state, in ONE place. The
    # per-row rationale never restates it (P2-D2) -- one fact in one field is
    # what keeps two reasons that must not converge from converging.
    judgment: Measurement = Measurement.not_collected(
        "no proposer output was applied")

    @property
    def counts(self) -> dict[str, int]:
        """Derived from rows, never assigned."""
        return {
            "capabilities": len(self.capabilities),
            "vulnerabilities": sum(len(c.vulnerabilities)
                                   for c in self.capabilities),
        }

    @model_validator(mode="after")
    def _capabilities_are_sorted(self) -> "UnifiedRiskMap":
        ids = [c.bc_id for c in self.capabilities]
        if ids != sorted(ids):
            raise ValueError(
                f"capabilities must be sorted by bc_id, got {ids} -- a "
                f"producer emitting discovery order is an NFR-10 bug")
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate bc_id in {ids}")
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> "UnifiedRiskMap":
        if (self.collected.state is not CollectionState.MEASURED
                and self.capabilities):
            raise ValueError(
                f"risk map did not collect ({self.collected.reason}) but "
                f"carries {len(self.capabilities)} capabilities")
        return self

    @model_validator(mode="after")
    def _unjudged_carries_no_proposer_rows(self) -> "UnifiedRiskMap":
        """_unmeasured_carries_no_payload, for the judgment layer."""
        if self.judgment.state is CollectionState.MEASURED:
            return self
        for c in self.capabilities:
            bad = ([t.category.value for t in c.threats
                    if t.source is RiskSource.PROPOSER]
                   + [v.key for v in c.vulnerabilities
                      if v.source is RiskSource.PROPOSER]
                   + [k.family.value for k in c.controls
                      if k.source is RiskSource.PROPOSER])
            if bad:
                raise ValueError(
                    f"{c.bc_id}: the judgment layer did not collect "
                    f"({self.judgment.reason}) but row(s) {bad} are stamped "
                    f"PROPOSER")
        return self
