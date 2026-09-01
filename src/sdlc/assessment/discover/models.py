"""FR-913 (E-47b): capability coverage and orphan classification contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as capability/models.py
and assessment/models.py must not: a dependency here would appear as a
reviewable import.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement
from ..scan.models import EvidenceRef, MemberKind

DEFAULT_COVERAGE_FLOOR = 0.90
DEAD_GUARD_MAX_UNRESOLVED = 0.10


class FileBucket(StrEnum):
    """Declaration order IS precedence order (see BUCKET_PRECEDENCE), so
    there is no second list to disagree with this one -- PHASE_ORDER's rule.
    """

    MEMBER = "member"
    INFRASTRUCTURE = "infrastructure"
    ATTACHED = "attached"
    DEAD = "dead"
    UNCLASSIFIED = "unclassified"


BUCKET_PRECEDENCE: tuple[FileBucket, ...] = tuple(FileBucket)

# D4: a file counts FOR coverage when the assessment can say what it is.
ACCOUNTED_FOR: frozenset[FileBucket] = frozenset(
    {FileBucket.MEMBER, FileBucket.INFRASTRUCTURE, FileBucket.ATTACHED}
)

# Only these two buckets name capabilities. A dead file citing one, or an
# attached file citing none, is a contradiction the type should not express.
CITES_CAPABILITIES: frozenset[FileBucket] = frozenset({FileBucket.MEMBER, FileBucket.ATTACHED})


class FileAttribution(BaseModel):
    """One file's verdict, carrying the rule that produced it.

    Frozen, so `capabilities` is asserted sorted rather than sorted in place:
    a producer that emits discovery order is a determinism bug (NFR-10), and
    silently repairing it here would hide that.
    """

    model_config = {"frozen": True}
    path: str
    bucket: FileBucket
    rule: str
    detail: str = ""
    capabilities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _capabilities_match_bucket(self) -> FileAttribution:
        cites = self.bucket in CITES_CAPABILITIES
        if cites and not self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must cite at least one "
                f"capability -- it is defined by its relation to one"
            )
        if not cites and self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must not cite capabilities "
                f"(got {self.capabilities}) -- an orphan by definition "
                f"belongs to none"
            )
        return self

    @model_validator(mode="after")
    def _capabilities_are_sorted(self) -> FileAttribution:
        if list(self.capabilities) != sorted(set(self.capabilities)):
            raise ValueError(
                f"capabilities {self.capabilities} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class UnresolvedEdge(BaseModel):
    """An import we saw and could not turn into an edge. `relative` is the
    field the dead guard reads: a dotted import matching nothing is an
    external package, but a RELATIVE one is extractor failure (D6)."""

    model_config = {"frozen": True}
    source_path: str
    target: str  # the raw module string, verbatim
    form: str  # "python_relative", "js_bare", ...
    reason: str  # "no_matching_path" | "ambiguous_suffix"
    relative: bool


class ReferenceGraph(BaseModel):
    edges: tuple[tuple[str, str], ...] = ()  # (importer, imported)
    unresolved: tuple[UnresolvedEdge, ...] = ()
    parsed: tuple[str, ...] = ()  # extractor covers these
    unparsed: tuple[str, ...] = ()  # extension not in the table
    unresolved_relative_rate: Measurement


class AttributionReport(BaseModel):
    files: tuple[FileAttribution, ...] = ()
    counts: dict[FileBucket, int] = Field(default_factory=dict)
    coverage: Measurement  # the ratio, or not_collected
    floor: float = DEFAULT_COVERAGE_FLOOR
    meets_floor: bool
    dead_guard_tripped: bool = False
    graph: ReferenceGraph
    skipped: tuple[str, ...] = ()  # blobs that could not be read

    @model_validator(mode="after")
    def _counts_agree_with_files(self) -> AttributionReport:
        missing = [b.value for b in FileBucket if b not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every bucket, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for bucket in FileBucket:
            actual = sum(1 for f in self.files if f.bucket is bucket)
            if self.counts[bucket] != actual:
                raise ValueError(
                    f"counts[{bucket.value}]={self.counts[bucket]} but "
                    f"{actual} file(s) carry that bucket -- counts are "
                    f"derived from files, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _meets_floor_is_derived(self) -> AttributionReport:
        """Derived, never assigned, so a deserialized payload cannot disagree
        with its own arithmetic. A not_collected coverage NEVER meets the
        floor: an assessment that could not measure must not read as one that
        measured and passed (FR-915)."""
        expected = (
            self.coverage.state is CollectionState.MEASURED
            and self.coverage.value is not None
            and self.coverage.value >= self.floor
        )
        if self.meets_floor != expected:
            raise ValueError(
                f"meets_floor={self.meets_floor} does not match the derived "
                f"{expected} for coverage={self.coverage.state.value} "
                f"floor={self.floor} -- meets_floor is derived, "
                f"never assigned"
            )
        return self


# D4. An operation is something the system DOES, reachable from outside the
# capability. The other half of this pairing is E-48's MemberKind ->
# SignalTier map; NEITHER may be derived from the other, because two uses of
# the word "contract" that agree only by coincidence is precisely the defect
# PipelineConfig.roles' boot-time mirror assertion exists to prevent.
CONTRACT_KINDS: frozenset[MemberKind] = frozenset(
    {
        MemberKind.HTTP_ROUTE,
        MemberKind.CLI_COMMAND,
        MemberKind.GRPC_METHOD,
        MemberKind.SCHEDULED_JOB,
        MemberKind.QUEUE_TOPIC,
        MemberKind.FRONTEND_ROUTE,
    }
)

# Kinds whose value is a URL path. head_token("/users/:id") is "/users/:id",
# so these MUST go through naming.route_object before being reduced.
ROUTE_SHAPED_KINDS: frozenset[MemberKind] = frozenset(
    {
        MemberKind.HTTP_ROUTE,
        MemberKind.FRONTEND_ROUTE,
    }
)


class OperationVerb(StrEnum):
    """What an operation does.

    NOT OwnershipVerb (D6). That describes a capability's relationship to an
    entity -- a different subject -- and collapsing the two reads plausibly
    right up to the point where an operation's CREATE is mistaken for an
    ownership CREATES.
    """

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    INVOKE = "invoke"  # CLI command, gRPC method -- direction unknown
    SCHEDULE = "schedule"  # cron/job -- direction unknown
    CONSUME = "consume"  # queue topic -- direction unknown
    RENDER = "render"  # frontend route -- direction unknown


WRITE_VERBS: frozenset[OperationVerb] = frozenset(
    {OperationVerb.CREATE, OperationVerb.UPDATE, OperationVerb.DELETE}
)
READ_VERBS: frozenset[OperationVerb] = frozenset({OperationVerb.READ})

# Ownership rules 2 and 3 consider ONLY these. An operation whose direction we
# cannot read proves contact and nothing else; counting it as a read would
# invent evidence (D8's UNDIRECTED outcome exists for exactly this case).
DIRECTED_VERBS: frozenset[OperationVerb] = WRITE_VERBS | READ_VERBS


class L2Operation(BaseModel):
    """One thing a capability does, resolving 1:1 to a byte range at the
    pinned commit (D3) -- which is why SC-7 holds trivially here."""

    model_config = {"frozen": True}
    op_id: str  # "BC-014-OP-03", assessment-local (D5)
    capability: str  # bc_id
    verb: OperationVerb
    name: str  # "create_payment"
    object: str  # "payment"; "" when underivable (see below)
    binding: str  # "POST /api/payments", verbatim
    kind: MemberKind
    rule: str  # the mapping rule that fired
    # The entity keys this operation can CLAIM CONTACT on, and the only
    # thing assign() matches against. Route-shaped kinds contribute exactly
    # their object: only HTTP routes carry directed verbs, so their match
    # must stay strict -- a loose route match could fabricate a writer.
    # Every other kind contributes the reduction of each separator token of
    # its binding: those kinds are undirected by construction (D6), so the
    # most a loose token match can produce is an UNDIRECTED claimant, never
    # an owner (review finding 1).
    entity_keys: tuple[str, ...] = ()
    evidence: EvidenceRef

    @model_validator(mode="after")
    def _entity_keys_are_sorted(self) -> L2Operation:
        """Asserted, not repaired: a producer emitting unsorted keys is a
        determinism bug (NFR-10), and fixing it here would hide it. This is
        FileAttribution._capabilities_are_sorted's rule."""
        if list(self.entity_keys) != sorted(set(self.entity_keys)):
            raise ValueError(
                f"entity_keys {self.entity_keys} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class DecompositionReport(BaseModel):
    operations: tuple[L2Operation, ...] = ()
    by_capability: dict[str, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_are_derived(self) -> DecompositionReport:
        for bc_id, claimed in self.by_capability.items():
            actual = sum(1 for o in self.operations if o.capability == bc_id)
            if claimed != actual:
                raise ValueError(
                    f"by_capability[{bc_id}]={claimed} but {actual} "
                    f"operation(s) carry it -- counts are derived from "
                    f"operations, never assigned"
                )
        unlisted = sorted({o.capability for o in self.operations} - set(self.by_capability))
        if unlisted:
            raise ValueError(
                f"operations name capabilities absent from by_capability "
                f"({unlisted}) -- an absent key and a zero count are "
                f"different claims and only one of them is true"
            )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> DecompositionReport:
        if self.collected.state is not CollectionState.MEASURED and self.operations:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.operations)} operation(s) are present -- a "
                f"decomposition that did not happen has no rows (FR-915)"
            )
        return self


class OwnershipVerb(StrEnum):
    """A capability's relationship to an entity. NOT OperationVerb (D6).

    TRACKS is deliberately absent. The other four have a deterministic
    trigger; TRACKS means something closer to "holds a reference for
    lifecycle purposes", which no static signal here distinguishes from
    READS. Emitting it would put a judgment call behind a code-computed
    label -- the exact defect this port exists to remove from BrownKit's
    prose gates. It is reserved for E-48's proposer.
    """

    OWNS = "owns"
    CREATES = "creates"
    MANAGES = "manages"
    READS = "reads"


class OwnershipOutcome(StrEnum):
    """D8: three non-owned outcomes, deliberately not one.

    Collapsing them would repeat coverage_pct's defect. A CLI-written table
    reported as UNCLAIMED tells a customer nothing touches data their job
    writes nightly -- a different and worse claim than "we cannot read the
    direction of the thing that touches it".
    """

    OWNED = "owned"
    CONFLICT = "conflict"  # 2+ tied claimants; E-48 picks
    UNDIRECTED = "undirected"  # claimants, none with readable direction
    UNCLAIMED = "unclaimed"  # nothing in the capability set touches it


class EntityDeclaration(BaseModel):
    """D2: what assign() needs from S2, WITHOUT importing a signal.

    discover/ imports scan RULE modules and never a signal: a signal is a
    producer with a memo key and a version, and depending on one here would
    make this package part of that signal's hashed surface. E-48 adapts S2's
    TableDecl at the call site, where both are already in scope.
    """

    model_config = {"frozen": True}
    name: str
    path: str
    line: int


class EntityOwnership(BaseModel):
    model_config = {"frozen": True}
    entity: str
    outcome: OwnershipOutcome
    owner: str | None = None
    verb: OwnershipVerb | None = None
    rule: str
    claimants: tuple[str, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()

    @model_validator(mode="after")
    def _owner_matches_outcome(self) -> EntityOwnership:
        owned = self.outcome is OwnershipOutcome.OWNED
        if owned != (self.owner is not None and self.verb is not None):
            raise ValueError(
                f"owner and verb are set IFF outcome is owned -- got "
                f"outcome={self.outcome.value} owner={self.owner} "
                f"verb={self.verb}. A row that names an owner and calls "
                f"itself a conflict is not a weaker claim, it is two claims"
            )
        return self

    @model_validator(mode="after")
    def _claimants_match_outcome(self) -> EntityOwnership:
        if self.outcome is OwnershipOutcome.CONFLICT and len(self.claimants) < 2:
            raise ValueError(
                f"outcome=conflict needs at least two claimants, got "
                f"{self.claimants} -- one claimant is not a contest"
            )
        if self.outcome is OwnershipOutcome.UNCLAIMED and self.claimants:
            raise ValueError(f"outcome=unclaimed names no claimants, got {self.claimants}")
        if (
            self.outcome in (OwnershipOutcome.OWNED, OwnershipOutcome.UNDIRECTED)
            and not self.claimants
        ):
            raise ValueError(
                f"outcome={self.outcome.value} requires at least one "
                f"claimant -- it is defined by something touching the entity"
            )
        return self

    @model_validator(mode="after")
    def _claimants_are_sorted(self) -> EntityOwnership:
        """Asserted, not repaired: a producer emitting discovery order is a
        determinism bug (NFR-10), and fixing it here would hide it. This is
        FileAttribution._capabilities_are_sorted's rule."""
        if list(self.claimants) != sorted(set(self.claimants)):
            raise ValueError(
                f"claimants {self.claimants} are not sorted and deduped -- "
                f"discovery order must not reach the artifact"
            )
        return self


class OwnershipReport(BaseModel):
    entities: tuple[EntityOwnership, ...] = ()
    counts: dict[OwnershipOutcome, int] = Field(default_factory=dict)
    collected: Measurement

    @model_validator(mode="after")
    def _counts_agree_with_entities(self) -> OwnershipReport:
        """AttributionReport._counts_agree_with_files, verbatim in intent."""
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
                    f"{actual} entit(ies) carry it -- counts are derived "
                    f"from entities, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _unmeasured_carries_no_payload(self) -> OwnershipReport:
        if self.collected.state is not CollectionState.MEASURED and self.entities:
            raise ValueError(
                f"collected={self.collected.state.value} carries no payload, "
                f"but {len(self.entities)} entit(ies) are present -- an "
                f"ownership map that did not happen has no rows (FR-915)"
            )
        return self
