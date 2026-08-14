"""FR-913 (E-47c): exactly one owner, or a surfaced conflict (D7/D8)."""
from __future__ import annotations

import random

from sdlc.assessment.discover.models import (
    EntityDeclaration, L2Operation, OperationVerb, OwnershipOutcome,
    OwnershipVerb,
)
from sdlc.assessment.discover.ownership import assign
from sdlc.assessment.scan.models import EvidenceRef, MemberKind
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)
ORDERS = EntityDeclaration(name="orders", path="db/models/order.py", line=8)


def _op(bc_id: str, verb: OperationVerb, obj: str, n: int = 1) -> L2Operation:
    return L2Operation(
        op_id=f"{bc_id}-OP-{n:02d}", capability=bc_id, verb=verb,
        name=f"{verb.value}_{obj}", object=obj,
        binding=f"{verb.value.upper()} /{obj}", kind=MemberKind.HTTP_ROUTE,
        rule="http_post", entity_keys=(obj,) if obj else (),
        evidence=EvidenceRef(path="api/a.py", lines="3"))


def _assign(decls, members, ops):
    return assign(decls, members, ops, schema_collected=MEASURED,
                  contract_collected=MEASURED)


def _row(report, entity: str):
    return next(e for e in report.entities if e.entity == entity)


def test_declaration_site_confers_ownership():
    report = _assign([ORDERS], {"BC-014": ["db/models/order.py"]}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-014"
    assert row.verb is OwnershipVerb.OWNS
    assert row.rule == "declared_in_sole_member"


def test_declaration_outranks_a_different_sole_writer():
    """The precedence claim itself (D7)."""
    report = _assign([ORDERS], {"BC-014": ["db/models/order.py"]},
                     [_op("BC-021", OperationVerb.CREATE, "order")])
    row = _row(report, "order")
    assert row.owner == "BC-014"
    assert row.rule == "declared_in_sole_member"


def test_a_sole_writer_owns_when_the_declaring_file_is_unattributed():
    report = _assign([ORDERS], {"BC-014": ["api/orders.py"]},
                     [_op("BC-014", OperationVerb.CREATE, "order")])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-014"
    assert row.verb is OwnershipVerb.CREATES


def test_mixed_writes_read_as_manages_not_creates():
    report = _assign([ORDERS], {}, [
        _op("BC-014", OperationVerb.CREATE, "order", 1),
        _op("BC-014", OperationVerb.DELETE, "order", 2)])
    assert _row(report, "order").verb is OwnershipVerb.MANAGES


def test_a_sole_reader_owns_when_nothing_writes():
    report = _assign([ORDERS], {}, [_op("BC-007", OperationVerb.READ, "order")])
    row = _row(report, "order")
    assert row.owner == "BC-007"
    assert row.verb is OwnershipVerb.READS
    assert row.rule == "sole_reader"


def test_a_reader_never_outranks_a_writer():
    report = _assign([ORDERS], {}, [
        _op("BC-014", OperationVerb.CREATE, "order", 1),
        _op("BC-007", OperationVerb.READ, "order", 2)])
    assert _row(report, "order").owner == "BC-014"


def test_tied_writers_surface_a_conflict():
    report = _assign([ORDERS], {}, [
        _op("BC-021", OperationVerb.CREATE, "order", 1),
        _op("BC-014", OperationVerb.UPDATE, "order", 2)])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.CONFLICT
    assert row.owner is None
    assert row.claimants == ("BC-014", "BC-021")
    assert row.rule == "tied_writers"


def test_a_shared_declaration_file_surfaces_a_conflict():
    report = _assign([ORDERS],
                     {"BC-014": ["db/models/order.py"],
                      "BC-021": ["db/models/order.py"]}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.CONFLICT
    assert row.rule == "declared_in_shared_file"


def test_clustered_declarations_in_different_files_are_tied_declarers():
    """Review finding 5: 'declared_in_shared_file' is only true when the
    SAME file is attributed to 2+ capabilities. orders in one capability's
    file and order_items in another's is a tie across files; a rule name
    that misstates the evidence cannot be cited."""
    report = _assign(
        [ORDERS,
         EntityDeclaration(name="order_items", path="db/other.py", line=3)],
        {"BC-014": ["db/models/order.py"], "BC-021": ["db/other.py"]}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.CONFLICT
    assert row.claimants == ("BC-014", "BC-021")
    assert row.rule == "tied_declarers"


def test_rule_1_lists_every_toucher_not_just_the_declarer():
    """Review finding 3: D7 accepts the shared-models limitation because
    E-48's proposer has standing to override it -- but only if the row
    shows the capability that lost. A declaration-site owner with a
    different sole writer carries both as claimants, each backed by the
    evidence beside them."""
    report = _assign([ORDERS], {"BC-014": ["db/models/order.py"]},
                     [_op("BC-021", OperationVerb.CREATE, "order")])
    row = _row(report, "order")
    assert row.owner == "BC-014"
    assert row.rule == "declared_in_sole_member"
    assert row.claimants == ("BC-014", "BC-021")
    assert len(row.evidence) == 2      # one declaration, one operation


def test_a_directed_winner_does_not_erase_undirected_contact():
    """Review finding 3: rules 2/3 dropped undirected touchers, so the row
    understated contact and claimants disagreed with evidence."""
    report = _assign([ORDERS], {}, [
        _op("BC-014", OperationVerb.CREATE, "order", 1),
        _op("BC-033", OperationVerb.INVOKE, "order", 2)])
    row = _row(report, "order")
    assert row.owner == "BC-014"
    assert row.claimants == ("BC-014", "BC-033")


def test_an_undirected_claimant_is_not_unclaimed():
    """D8: a CLI-written table must not read as untouched."""
    report = _assign([ORDERS], {}, [_op("BC-014", OperationVerb.INVOKE, "order")])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.UNDIRECTED
    assert row.claimants == ("BC-014",)
    assert row.rule == "undirected_only"


def test_an_untouched_entity_is_unclaimed():
    report = _assign([ORDERS], {}, [])
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.UNCLAIMED
    assert row.claimants == ()


def test_declarations_reduce_to_one_row_per_entity_key():
    """order_items and orders share a key, as S2's _cluster_key intends."""
    report = _assign(
        [ORDERS, EntityDeclaration(name="order_items", path="db/m.py", line=2)],
        {}, [])
    assert [e.entity for e in report.entities] == ["order"]


def test_known_limitation_a_shared_models_package_grants_blanket_ownership():
    """D7, pinned rather than caveated. Every declaration lives in one
    capability's files, so rule 1 hands it the whole schema. E-48's proposer
    is the layer with standing to override this; a change to the rule should
    move this test rather than surprise a customer."""
    decls = [ORDERS,
             EntityDeclaration(name="payments", path="db/models/pay.py", line=3),
             EntityDeclaration(name="users", path="db/models/user.py", line=5)]
    report = _assign(decls, {"BC-002": ["db/models/order.py",
                                        "db/models/pay.py",
                                        "db/models/user.py"]}, [])
    assert {e.owner for e in report.entities} == {"BC-002"}
    assert report.counts[OwnershipOutcome.OWNED] == 3


def test_a_degraded_schema_signal_yields_no_rows():
    report = assign([ORDERS], {}, [],
                    schema_collected=Measurement.not_collected("S2 gap"),
                    contract_collected=MEASURED)
    assert report.entities == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S2" in report.collected.reason


def test_a_degraded_contract_signal_yields_no_rows():
    """Without S3 every entity would fall to the declaration rule -- a
    weaker answer in the identical shape, which is what FR-915 forbids."""
    report = assign([ORDERS], {"BC-014": ["db/models/order.py"]}, [],
                    schema_collected=MEASURED,
                    contract_collected=Measurement.not_collected("S3 gap"))
    assert report.entities == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S3" in report.collected.reason


def test_a_not_collected_report_still_carries_every_outcome_count():
    report = assign([ORDERS], {}, [],
                    schema_collected=Measurement.not_collected("S2 gap"),
                    contract_collected=MEASURED)
    assert set(report.counts) == set(OwnershipOutcome)
    assert sum(report.counts.values()) == 0


def test_output_is_byte_identical_across_input_order():
    """NFR-10, in this module's own test file."""
    decls = [ORDERS,
             EntityDeclaration(name="payments", path="db/models/pay.py", line=3)]
    ops = [_op("BC-021", OperationVerb.CREATE, "payment", 1),
           _op("BC-014", OperationVerb.READ, "order", 2)]
    members = {"BC-014": ["db/models/order.py"], "BC-002": ["x.py"]}
    shuffled_decls, shuffled_ops = list(decls), list(ops)
    rng = random.Random(20260814)
    rng.shuffle(shuffled_decls)
    rng.shuffle(shuffled_ops)
    first = _assign(decls, members, ops)
    second = _assign(shuffled_decls, dict(reversed(list(members.items()))),
                     shuffled_ops)
    assert first.model_dump_json() == second.model_dump_json()
