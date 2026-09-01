"""FR-913 (E-48): the discover phase's contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as discover/models.py
and capability/models.py must not.

Separate from discover/models.py deliberately (DD2): that module holds E-47b/c's
SUB-MECHANISM reports (attribution, decomposition, ownership) and is already
387 lines. This one holds the PHASE artifact and the proposer's interface.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

from ...capability.models import Advisory
from ...measurement import CollectionState, Measurement
from ..scan.models import (
    CandidateMember,
    Confidence,
    CoverageRecord,
    EvidenceRef,
    SecurityObservation,
    SensitivityRecord,
    TestabilityFinding,
)
from ..verification import guard_reason
from .models import (
    AttributionReport,
    DecompositionReport,
    OwnershipOutcome,
    OwnershipReport,
    OwnershipVerb,
)

if TYPE_CHECKING:
    from .verify import RefVerification


class DiscoverAction(StrEnum):
    """Clause D2. One verdict per candidate."""

    CONFIRM = "confirm"
    SPLIT = "split"
    MERGE = "merge"
    DE_SCOPE = "de_scope"
    FLAG = "flag"


class DispositionSource(StrEnum):
    """Who decided, and it is never the model's to claim (DD7).

    DROPPED and BASELINE must not converge: "a model decided this and cited
    something that does not exist" is evidence about the candidate, while "no
    model ran" is not. This is unbuilt_signal vs failed_signal, whose docstring
    states the rule -- "the reason strings must not converge".
    """

    BASELINE = "baseline"  # code's rule; no proposer consulted
    PROPOSER = "proposer"  # the model decided and its refs resolved
    DROPPED = "dropped"  # the model decided; verification refused it


class SplitPartition(BaseModel):
    """One side of a SPLIT. `member_values` must be a subset of the
    candidate's own members -- enforced at apply time (plan 2), where the
    candidate is in scope."""

    model_config = {"frozen": True}
    name: str
    member_values: tuple[str, ...]

    @model_validator(mode="after")
    def _member_values_are_sorted(self) -> SplitPartition:
        if list(self.member_values) != sorted(set(self.member_values)):
            raise ValueError(
                f"member_values {self.member_values} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class ProposedDisposition(BaseModel):
    """What the MODEL returns.

    Carries no `source` and no `rule`: provenance is code's to stamp (DD1).
    A model able to set `source` could label a hallucinated verdict as a
    code-computed baseline, which is exactly the laundering DD7 forbids.
    """

    candidate_id: str
    action: DiscoverAction
    rationale: str
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    # DD8 item 5. Optional: a disposition may cite a location without quoting
    # it. When present it is byte-verified under VERBATIM_BYTES against the
    # FIRST evidence ref's file -- a quote with no reference has nothing to
    # verify against and is refused.
    quote: str = ""


class DiscoverProposal(BaseModel):
    """The proposer's output_type. Dispositions and nothing else (DD1)."""

    dispositions: list[ProposedDisposition] = Field(default_factory=list)


class CandidateDisposition(BaseModel):
    """A disposition after code has stamped its provenance."""

    model_config = {"frozen": True}
    candidate_id: str
    action: DiscoverAction
    source: DispositionSource
    rule: str
    rationale: str = ""
    merge_into: str | None = None
    partitions: tuple[SplitPartition, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    quote: str = ""

    @model_validator(mode="after")
    def _merge_names_a_target(self) -> CandidateDisposition:
        if (self.action is DiscoverAction.MERGE) != (self.merge_into is not None):
            raise ValueError(
                f"merge_into is set IFF action is merge -- got "
                f"action={self.action.value} merge_into={self.merge_into}"
            )
        return self

    @model_validator(mode="after")
    def _split_partitions_the_candidate(self) -> CandidateDisposition:
        if self.action is DiscoverAction.SPLIT:
            if len(self.partitions) < 2:
                raise ValueError(
                    f"action=split needs at least two partitions, got "
                    f"{len(self.partitions)} -- a split into one is a confirm"
                )
        elif self.partitions:
            raise ValueError(f"action={self.action.value} must not carry partitions")
        return self

    @model_validator(mode="after")
    def _a_proposer_verdict_carries_its_reasoning(self) -> CandidateDisposition:
        if self.source is DispositionSource.PROPOSER and not self.rationale.strip():
            raise ValueError(
                "source=proposer requires a rationale -- a baseline's rule IS "
                "its rationale, but an unexplained model verdict is "
                "unreviewable"
            )
        return self


# DD8's phase-level citation guard. The threshold and the wording are
# verification.py's since E-49 RD6: two reasons that must not converge cannot
# converge if there is only one. Re-exported here because E-48's tests and
# call sites import it from this module.
from ..verification import (  # noqa: E402
    CITATION_GUARD_MAX_UNRESOLVED as CITATION_GUARD_MAX_UNRESOLVED,
)


def guard_tripped(verification: RefVerification) -> str:
    """DD8's phase-level guard, typed to discover's verification: the reason
    the phase must report not_collected, or "" when the proposal is usable."""
    return guard_reason(verification)


# S1's two non-domain classifications. A candidate supported ONLY by these is
# named like a layer or a container ("services", "utils", "api"), which is
# clause D2's guardrail: delivery channels and deployment boundaries are not
# capabilities. S1 records WHICH rule fired rather than a boolean precisely so
# this distinction is available here (scan spec, SourceCandidate docstring).
GUARDRAIL_RULES: frozenset[str] = frozenset({"s1_layer_name", "s1_generic_name"})


class GraphSummary(BaseModel):
    """The reference graph's shape WITHOUT its edges (DD4).

    The proposer needs to know how much of the tree the extractor could read
    -- a coupling number computed over two parsed files means something
    different from one over two hundred. It does not need the edge list, and
    an edge list in workflow history is the open FR-702 hazard.
    """

    model_config = {"frozen": True}
    parsed: int
    unparsed: int
    edges: int
    unresolved_relative_rate: Measurement


class CandidateContext(BaseModel):
    """One scan candidate as the proposer sees it: everything code could
    compute about it, and no room to invent anything else."""

    model_config = {"frozen": True}
    candidate_id: str
    name: str
    confidence: Confidence
    sources: tuple[str, ...]  # SourceCandidate.local_id
    source_rules: tuple[str, ...]  # the rules that produced them
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement  # clause D1
    coupling: Measurement  # clause D1
    guardrail_only: bool  # DD6's input, DERIVED
    possible_duplicate_of: tuple[str, ...] = ()
    security: tuple[SecurityObservation, ...] = ()  # clause D6
    sensitivity: tuple[SensitivityRecord, ...] = ()  # clause D6
    testability: tuple[TestabilityFinding, ...] = ()  # clause D6a
    coverage: tuple[CoverageRecord, ...] = ()  # clause D6a

    @model_validator(mode="after")
    def _guardrail_only_is_derived(self) -> CandidateContext:
        """Derived, never assigned, so a deserialized payload cannot disagree
        with its own arithmetic (AttributionReport.meets_floor's rule).

        `and self.source_rules` is load-bearing: all() of an empty sequence is
        True, and a candidate whose rules we do not know must not be DE-SCOPEd
        on an absence of evidence.
        """
        expected = bool(self.source_rules) and all(r in GUARDRAIL_RULES for r in self.source_rules)
        if self.guardrail_only != expected:
            raise ValueError(
                f"guardrail_only={self.guardrail_only} does not match the "
                f"derived {expected} for source_rules={self.source_rules} -- "
                f"it is derived, never assigned"
            )
        return self

    @model_validator(mode="after")
    def _member_paths_are_sorted(self) -> CandidateContext:
        if list(self.member_paths) != sorted(set(self.member_paths)):
            raise ValueError(
                f"member_paths {self.member_paths} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class DiscoverContext(BaseModel):
    """The packet handed to the proposer, and the thing DD10's memo digests."""

    candidates: tuple[CandidateContext, ...] = ()
    entry_point_paths: tuple[str, ...] = ()
    graph: GraphSummary
    file_count: int = 0
    skipped: tuple[str, ...] = ()
    collected: Measurement

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> DiscoverContext:
        if self.collected.state is not CollectionState.MEASURED and self.candidates:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.candidates)} candidate(s) are present -- a "
                f"context that could not be built has no candidates (FR-915)"
            )
        return self


# A verdict ABOUT a candidate rather than a surviving boundary. Only the
# actions absent from this set produce a Capability with a bc_id.
REJECTING_ACTIONS: frozenset[DiscoverAction] = frozenset(
    {DiscoverAction.DE_SCOPE, DiscoverAction.FLAG}
)


class Capability(BaseModel):
    """One L1 capability: a candidate that survived disposition and was given
    a durable id by E-47a's resolve()."""

    model_config = {"frozen": True}
    bc_id: str
    local_key: str  # the candidate_id it came from
    name: str
    confidence: Confidence
    members: tuple[CandidateMember, ...]
    member_paths: tuple[str, ...]
    cohesion: Measurement
    coupling: Measurement
    disposition: CandidateDisposition
    security: tuple[SecurityObservation, ...] = ()  # clause D6
    sensitivity: tuple[SensitivityRecord, ...] = ()  # clause D6
    testability: tuple[TestabilityFinding, ...] = ()  # clause D6a
    coverage: tuple[CoverageRecord, ...] = ()  # clause D6a

    @model_validator(mode="after")
    def _a_rejected_candidate_is_not_a_capability(self) -> Capability:
        if self.disposition.action in REJECTING_ACTIONS:
            raise ValueError(
                f"disposition action={self.disposition.action.value} rejects "
                f"the candidate, so it must not hold bc_id={self.bc_id} -- a "
                f"map that both rejected and identified the same thing is "
                f"making two claims"
            )
        return self

    @model_validator(mode="after")
    def _member_paths_are_sorted(self) -> Capability:
        if list(self.member_paths) != sorted(set(self.member_paths)):
            raise ValueError(
                f"member_paths {self.member_paths} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class BlueprintStatus(StrEnum):
    """Clause D8. MISSING is CONTEXT, not failure: a repository that does not
    do what its industry normally does may be correct, incomplete, or out of
    scope, and this comparison cannot tell which."""

    PRESENT = "present"
    MISSING = "missing"
    EXTRA = "extra"


class BlueprintGap(BaseModel):
    model_config = {"frozen": True}
    name: str
    status: BlueprintStatus
    level: int = 0  # 0 for an EXTRA (no blueprint level)
    parent: str = ""
    matched_bc_id: str | None = None

    @model_validator(mode="after")
    def _a_match_names_its_capability(self) -> BlueprintGap:
        matched = self.status in (BlueprintStatus.PRESENT, BlueprintStatus.EXTRA)
        if matched != (self.matched_bc_id is not None):
            raise ValueError(
                f"matched_bc_id is set IFF the status names a capability -- "
                f"got status={self.status.value} "
                f"matched_bc_id={self.matched_bc_id}. A MISSING row that "
                f"names a capability is not a weaker claim, it is two claims"
            )
        return self


class BlueprintComparison(BaseModel):
    """DD11's artifact. Degrades on its own (P3-D4) -- a missing or
    unparseable blueprint reports not_collected here and the rest of the map
    ships."""

    blueprint: str = ""
    version: str = ""
    gaps: tuple[BlueprintGap, ...] = ()
    counts: dict[BlueprintStatus, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> BlueprintComparison:
        if self.collected.state is not CollectionState.MEASURED:
            return self
        missing = [s.value for s in BlueprintStatus if s not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every status, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for status in BlueprintStatus:
            actual = sum(1 for g in self.gaps if g.status is status)
            if self.counts[status] != actual:
                raise ValueError(
                    f"counts[{status.value}]={self.counts[status]} but "
                    f"{actual} row(s) carry it -- counts are derived from "
                    f"rows, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _gaps_are_sorted(self) -> BlueprintComparison:
        keys = [(g.status.value, g.name, g.matched_bc_id or "") for g in self.gaps]
        if keys != sorted(set(keys)):
            raise ValueError(
                f"gaps {keys} are not sorted and deduped -- comparison order "
                f"must not reach the artifact"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> BlueprintComparison:
        if self.collected.state is not CollectionState.MEASURED and (self.gaps or self.counts):
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but rows are present -- a comparison that did not happen "
                f"has no gaps (FR-915)"
            )
        return self


class DomainEntity(BaseModel):
    """One entity in the consolidated domain model (clause D7). A projection
    of EntityOwnership -- never a second judgment of it (DD12)."""

    model_config = {"frozen": True}
    entity: str
    outcome: OwnershipOutcome
    owner: str | None = None
    verb: OwnershipVerb | None = None
    readers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _readers_are_sorted(self) -> DomainEntity:
        if list(self.readers) != sorted(set(self.readers)):
            raise ValueError(
                f"readers {self.readers} are not sorted and deduped -- "
                f"discovery order must not reach the artifact"
            )
        return self


class DomainModel(BaseModel):
    """DD12's artifact: entities, their owner where one resolved, the
    capabilities that read them, and the three unowned outcomes surfaced as
    E-47c left them."""

    entities: tuple[DomainEntity, ...] = ()
    counts: dict[OwnershipOutcome, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> DomainModel:
        if self.collected.state is not CollectionState.MEASURED:
            return self
        missing = [o.value for o in OwnershipOutcome if o not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every outcome, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for outcome in OwnershipOutcome:
            actual = sum(1 for e in self.entities if e.outcome is outcome)
            if self.counts[outcome] != actual:
                raise ValueError(
                    f"counts[{outcome.value}]={self.counts[outcome]} but "
                    f"{actual} entit(ies) carry it -- counts are derived from "
                    f"entities, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _entities_are_sorted(self) -> DomainModel:
        names = [e.entity for e in self.entities]
        if names != sorted(set(names)):
            raise ValueError(f"entities {names} are not sorted and deduped")
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> DomainModel:
        if self.collected.state is not CollectionState.MEASURED and (self.entities or self.counts):
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but rows are present -- a domain model that did not happen "
                f"has no entities (FR-915)"
            )
        return self


class CapabilityMap(BaseModel):
    """The DISCOVER phase artifact (FR-913).

    Plan 3 adds `domain_model` (clause D7) and `blueprint` (clause D8) when it
    builds their producers. Declaring them now would be a field with no
    producer, which is what E-47c's review found and fixed.
    """

    capabilities: tuple[Capability, ...] = ()
    by_action: dict[DiscoverAction, int] = Field(default_factory=dict)
    dispositions: tuple[CandidateDisposition, ...] = ()
    attribution: AttributionReport | None = None
    decomposition: DecompositionReport | None = None
    ownership: OwnershipReport | None = None
    advisories: tuple[Advisory, ...] = ()
    dropped_dispositions: int = 0
    total_references: int = 0
    blueprint: BlueprintComparison | None = None
    domain_model: DomainModel | None = None
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> CapabilityMap:
        for action, claimed in self.by_action.items():
            actual = sum(1 for c in self.capabilities if c.disposition.action is action)
            if claimed != actual:
                raise ValueError(
                    f"by_action[{action.value}]={claimed} but {actual} "
                    f"capabilit(ies) carry it -- counts are derived from "
                    f"capabilities, never assigned"
                )
        unlisted = sorted(
            {c.disposition.action.value for c in self.capabilities}
            - {a.value for a in self.by_action}
        )
        if unlisted:
            raise ValueError(
                f"capabilities carry actions absent from by_action "
                f"({unlisted}) -- an absent key and a zero count are "
                f"different claims and only one of them is true"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> CapabilityMap:
        if self.collected.state is not CollectionState.MEASURED:
            if (
                self.capabilities
                or self.dispositions
                or self.by_action
                or self.attribution is not None
                or self.decomposition is not None
                or self.ownership is not None
                or self.advisories
                or self.dropped_dispositions != 0
                or self.total_references != 0
                or self.blueprint is not None
                or self.domain_model is not None
            ):
                raise ValueError(
                    f"collected={self.collected.state.value} carries no payload, "
                    f"but payload fields are present -- a discover that did "
                    f"not happen has no capabilities, rows, or reports (FR-915)"
                )
        return self


def context_digest(context: DiscoverContext) -> str:
    """A canonical digest over the packet the rest of the phase reads (DD10).

    Digesting the packet rather than hand-listing its parts follows
    brief_digest's reasoning: identical facts hit, new facts invalidate, and a
    field added to the context later cannot escape the key.

    Canonical because DiscoverContext is: build_context sorts every collection
    it emits and the model carries no dicts, which
    test_the_packet_is_order_independent already asserts as a byte-identical
    model_dump_json across input order. This hashes exactly those bytes.
    """
    return hashlib.sha256(context.model_dump_json().encode("utf-8")).hexdigest()
