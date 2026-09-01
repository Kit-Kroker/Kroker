"""E-47b: the report's validators, which are the artifact's real contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.models import (
    ACCOUNTED_FOR,
    BUCKET_PRECEDENCE,
    DEFAULT_COVERAGE_FLOOR,
    AttributionReport,
    FileAttribution,
    FileBucket,
    ReferenceGraph,
)
from sdlc.measurement import Measurement

EMPTY_GRAPH = ReferenceGraph(
    unresolved_relative_rate=Measurement.not_collected("no relative imports")
)


def _report(files, coverage, *, floor=DEFAULT_COVERAGE_FLOOR, meets=None, tripped=False):
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    if meets is None:
        meets = coverage.value is not None and coverage.value >= floor
    return AttributionReport(
        files=tuple(files),
        counts=counts,
        coverage=coverage,
        floor=floor,
        meets_floor=meets,
        dead_guard_tripped=tripped,
        graph=EMPTY_GRAPH,
    )


def test_precedence_is_declaration_order():
    assert BUCKET_PRECEDENCE == (
        FileBucket.MEMBER,
        FileBucket.INFRASTRUCTURE,
        FileBucket.ATTACHED,
        FileBucket.DEAD,
        FileBucket.UNCLASSIFIED,
    )
    assert ACCOUNTED_FOR == frozenset(BUCKET_PRECEDENCE[:3])


def test_member_must_cite_a_capability():
    with pytest.raises(ValidationError, match="must cite"):
        FileAttribution(path="a.py", bucket=FileBucket.MEMBER, rule="capability_member")


def test_dead_must_not_cite_a_capability():
    with pytest.raises(ValidationError, match="must not cite"):
        FileAttribution(
            path="a.py",
            bucket=FileBucket.DEAD,
            rule="no_static_inbound_reference",
            capabilities=("BC-001",),
        )


def test_capabilities_must_be_sorted_and_deduped():
    with pytest.raises(ValidationError, match="sorted"):
        FileAttribution(
            path="a.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-002", "BC-001"),
        )


def test_counts_must_agree_with_files():
    good = FileAttribution(
        path="a.py", bucket=FileBucket.MEMBER, rule="capability_member", capabilities=("BC-001",)
    )
    with pytest.raises(ValidationError, match="counts"):
        AttributionReport(
            files=(good,),
            counts={b: 0 for b in FileBucket},
            coverage=Measurement.measured(1.0),
            meets_floor=True,
            dead_guard_tripped=False,
            graph=EMPTY_GRAPH,
        )


def test_counts_must_carry_every_bucket_including_zeros():
    with pytest.raises(ValidationError, match="every bucket"):
        AttributionReport(
            files=(),
            counts={FileBucket.MEMBER: 0},
            coverage=Measurement.not_collected("no source files"),
            meets_floor=False,
            dead_guard_tripped=False,
            graph=EMPTY_GRAPH,
        )


def test_meets_floor_is_derived_not_assigned():
    files = [
        FileAttribution(
            path="a.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-001",),
        )
    ]
    with pytest.raises(ValidationError, match="derived"):
        _report(files, Measurement.measured(1.0), meets=False)


def test_not_collected_coverage_never_meets_the_floor():
    with pytest.raises(ValidationError, match="derived"):
        _report([], Measurement.not_collected("no capabilities"), meets=True)


def test_not_collected_coverage_with_meets_false_constructs():
    report = _report([], Measurement.not_collected("no capabilities"), meets=False)
    assert report.meets_floor is False


def test_exactly_the_floor_meets_it():
    files = [
        FileAttribution(
            path=f"m{i}.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-001",),
        )
        for i in range(9)
    ] + [FileAttribution(path="d.py", bucket=FileBucket.DEAD, rule="no_static_inbound_reference")]
    assert _report(files, Measurement.measured(0.90)).meets_floor is True


from sdlc.assessment.discover.models import (
    CONTRACT_KINDS,
    DIRECTED_VERBS,
    DecompositionReport,
    L2Operation,
    OperationVerb,
)
from sdlc.assessment.scan.models import EvidenceRef, MemberKind
from sdlc.measurement import CollectionState

OP = L2Operation(
    op_id="BC-014-OP-01",
    capability="BC-014",
    verb=OperationVerb.CREATE,
    name="create_payment",
    object="payment",
    binding="POST /api/payments",
    kind=MemberKind.HTTP_ROUTE,
    rule="http_post",
    entity_keys=("payment",),
    evidence=EvidenceRef(path="api/pay.py", lines="31"),
)


def test_entity_keys_are_asserted_sorted_never_repaired():
    """NFR-10: a producer emitting unsorted keys is a determinism bug;
    repairing it here would hide it (FileAttribution's rule)."""
    with pytest.raises(ValidationError, match="not sorted"):
        L2Operation(
            op_id="BC-014-OP-01",
            capability="BC-014",
            verb=OperationVerb.CREATE,
            name="create_payment",
            object="payment",
            binding="POST /api/payments",
            kind=MemberKind.HTTP_ROUTE,
            rule="http_post",
            entity_keys=("payment", "order"),
            evidence=EvidenceRef(path="api/pay.py", lines="31"),
        )


def test_contract_kinds_names_behaviour_not_data_or_structure():
    assert MemberKind.HTTP_ROUTE in CONTRACT_KINDS
    assert MemberKind.SCHEDULED_JOB in CONTRACT_KINDS
    for absent in (
        MemberKind.ENTITY_NAME,
        MemberKind.DB_TABLE,
        MemberKind.TEST_NAME,
        MemberKind.EXPORTED_SYMBOL,
        MemberKind.PACKAGE_PATH,
        MemberKind.FILE_PATH,
    ):
        assert absent not in CONTRACT_KINDS


def test_only_read_and_write_verbs_are_directed():
    assert OperationVerb.CREATE in DIRECTED_VERBS
    assert OperationVerb.READ in DIRECTED_VERBS
    for undirected in (
        OperationVerb.INVOKE,
        OperationVerb.SCHEDULE,
        OperationVerb.CONSUME,
        OperationVerb.RENDER,
    ):
        assert undirected not in DIRECTED_VERBS


def test_by_capability_carries_every_capability_including_zeros():
    report = DecompositionReport(
        operations=(OP,),
        by_capability={"BC-014": 1, "BC-021": 0},
        collected=Measurement.measured(1.0),
    )
    assert report.by_capability["BC-021"] == 0


def test_by_capability_counts_are_derived_from_operations():
    with pytest.raises(ValidationError, match="derived from operations"):
        DecompositionReport(
            operations=(OP,), by_capability={"BC-014": 7}, collected=Measurement.measured(1.0)
        )


def test_an_unmeasured_report_carries_no_operations():
    with pytest.raises(ValidationError, match="carries no payload"):
        DecompositionReport(
            operations=(OP,),
            by_capability={"BC-014": 1},
            collected=Measurement.not_collected("S3 did not collect"),
        )


def test_an_unmeasured_report_with_no_rows_is_valid():
    report = DecompositionReport(collected=Measurement.not_collected("S3 did not collect"))
    assert report.operations == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED


from sdlc.assessment.discover.models import (
    EntityOwnership,
    OwnershipOutcome,
    OwnershipReport,
    OwnershipVerb,
)


def _counts(*rows: EntityOwnership) -> dict[OwnershipOutcome, int]:
    return {o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome}


OWNED = EntityOwnership(
    entity="order",
    outcome=OwnershipOutcome.OWNED,
    owner="BC-014",
    verb=OwnershipVerb.OWNS,
    rule="declared_in_sole_member",
    claimants=("BC-014",),
)


def test_tracks_is_not_a_deterministic_verb():
    """D6: four relationships have a trigger; TRACKS has none, and it is
    reserved for E-48's proposer."""
    assert not hasattr(OwnershipVerb, "TRACKS")
    assert {v.value for v in OwnershipVerb} == {"owns", "creates", "manages", "reads"}


def test_an_owner_requires_the_owned_outcome():
    with pytest.raises(ValidationError, match="owner and verb are set"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            owner="BC-014",
            verb=OwnershipVerb.OWNS,
            rule="tied_writers",
            claimants=("BC-014", "BC-021"),
        )


def test_the_owned_outcome_requires_an_owner():
    with pytest.raises(ValidationError, match="owner and verb are set"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.OWNED,
            rule="sole_writer",
            claimants=("BC-014",),
        )


def test_a_conflict_needs_at_least_two_claimants():
    with pytest.raises(ValidationError, match="at least two claimants"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers",
            claimants=("BC-014",),
        )


def test_an_unclaimed_entity_names_no_claimants():
    with pytest.raises(ValidationError, match="names no claimants"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.UNCLAIMED,
            rule="no_claimant",
            claimants=("BC-014",),
        )


def test_claimants_are_asserted_sorted_never_repaired():
    with pytest.raises(ValidationError, match="not sorted"):
        EntityOwnership(
            entity="order",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tied_writers",
            claimants=("BC-021", "BC-014"),
        )


def test_counts_carry_every_outcome_including_zeros():
    report = OwnershipReport(
        entities=(OWNED,), counts=_counts(OWNED), collected=Measurement.measured(1.0)
    )
    assert report.counts[OwnershipOutcome.UNCLAIMED] == 0


def test_a_missing_outcome_key_is_rejected():
    with pytest.raises(ValidationError, match="every outcome"):
        OwnershipReport(
            entities=(OWNED,),
            counts={OwnershipOutcome.OWNED: 1},
            collected=Measurement.measured(1.0),
        )


def test_an_unmeasured_ownership_report_carries_no_rows():
    with pytest.raises(ValidationError, match="carries no payload"):
        OwnershipReport(
            entities=(OWNED,), counts=_counts(OWNED), collected=Measurement.not_collected("S2 gap")
        )
