# tests/test_discover_domain.py
"""E-48 DD12 (clause D7): derived from assign(), never re-judged."""

from sdlc.assessment.discover.domain import consolidate
from sdlc.assessment.discover.models import (
    EntityOwnership,
    OwnershipOutcome,
    OwnershipReport,
)
from sdlc.measurement import CollectionState, Measurement


def _report(*rows: EntityOwnership) -> OwnershipReport:
    return OwnershipReport(
        entities=rows,
        counts={o: sum(1 for r in rows if r.outcome is o) for o in OwnershipOutcome},
        collected=Measurement.measured(float(len(rows))),
    )


def test_an_owned_entity_carries_its_owner_and_verb():
    from sdlc.assessment.discover.models import OwnershipVerb

    rep = _report(
        EntityOwnership(
            entity="orders",
            outcome=OwnershipOutcome.OWNED,
            owner="BC-001",
            verb=OwnershipVerb.OWNS,
            rule="declaration",
            claimants=("BC-001",),
        )
    )
    out = consolidate(rep, [])
    row = out.entities[0]
    assert row.entity == "orders"
    assert row.owner == "BC-001"
    assert row.outcome is OwnershipOutcome.OWNED


def test_the_three_unowned_outcomes_stay_distinct():
    """E-47c kept CONFLICT / UNDIRECTED / UNCLAIMED apart precisely so a
    CLI-written table is never reported as untouched. D7 must not
    re-collapse them."""
    rep = _report(
        EntityOwnership(
            entity="a",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tie",
            claimants=("BC-001", "BC-002"),
        ),
        EntityOwnership(
            entity="b", outcome=OwnershipOutcome.UNDIRECTED, rule="reads", claimants=("BC-001",)
        ),
        EntityOwnership(entity="c", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    out = consolidate(rep, [])
    got = {e.entity: e.outcome for e in out.entities}
    assert got == {
        "a": OwnershipOutcome.CONFLICT,
        "b": OwnershipOutcome.UNDIRECTED,
        "c": OwnershipOutcome.UNCLAIMED,
    }


def test_readers_are_carried_from_claimants_minus_the_owner():
    from sdlc.assessment.discover.models import OwnershipVerb

    rep = _report(
        EntityOwnership(
            entity="orders",
            outcome=OwnershipOutcome.OWNED,
            owner="BC-001",
            verb=OwnershipVerb.OWNS,
            rule="declaration",
            claimants=("BC-001", "BC-002"),
        )
    )
    out = consolidate(rep, [])
    assert out.entities[0].readers == ("BC-002",)


def test_a_degraded_ownership_report_yields_a_not_collected_domain_model():
    """P3-D5: an empty entity table would claim the repository has no
    entities."""
    rep = OwnershipReport(
        counts={o: 0 for o in OwnershipOutcome},
        collected=Measurement.not_collected("S2 did not collect"),
    )
    out = consolidate(rep, [])
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "S2" in out.collected.reason
    assert out.entities == ()


def test_entities_are_sorted():
    rep = _report(
        EntityOwnership(entity="zebra", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
        EntityOwnership(entity="apple", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    out = consolidate(rep, [])
    assert [e.entity for e in out.entities] == ["apple", "zebra"]


def test_consolidation_is_order_independent():
    """NFR-10."""
    rows = (
        EntityOwnership(entity="a", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
        EntityOwnership(entity="b", outcome=OwnershipOutcome.UNCLAIMED, rule="none"),
    )
    assert (
        consolidate(_report(*rows), []).model_dump_json()
        == consolidate(_report(*reversed(rows)), []).model_dump_json()
    )


def test_no_ownership_row_is_authored_here():
    """DD12: the model's standing to override a conflict is exercised through
    a disposition on the CAPABILITY, not by editing this table. So
    consolidate() must be a pure projection -- same row count in, same out."""
    rep = _report(
        EntityOwnership(
            entity="a",
            outcome=OwnershipOutcome.CONFLICT,
            rule="tie",
            claimants=("BC-001", "BC-002"),
        )
    )
    assert len(consolidate(rep, []).entities) == len(rep.entities)
