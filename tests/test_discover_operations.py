"""FR-913 (E-47c): one operation per contract member, each resolving to a
byte range at the pinned commit (D3)."""

from __future__ import annotations

import random

from sdlc.assessment.discover.models import OperationVerb
from sdlc.assessment.discover.operations import decompose
from sdlc.assessment.scan.models import CandidateMember, MemberKind
from sdlc.measurement import CollectionState, Measurement

MEASURED = Measurement.measured(1.0)


def _m(kind: MemberKind, value: str, path: str = "api/pay.py", line: int = 1):
    return CandidateMember(kind=kind, value=value, path=path, line=line)


PAYMENTS = [
    _m(MemberKind.HTTP_ROUTE, "POST /api/payments", line=31),
    _m(MemberKind.HTTP_ROUTE, "GET /api/payments/{id}", line=47),
    _m(MemberKind.HTTP_ROUTE, "DELETE /api/payments/{id}", line=62),
    _m(MemberKind.SCHEDULED_JOB, "settle_nightly", "jobs/settle.py", 12),
]


def test_each_contract_member_becomes_its_own_operation():
    """D3: no clustering. Four members, four operations."""
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    assert len(report.operations) == 4
    assert report.by_capability == {"BC-014": 4}


def test_every_operation_carries_its_own_byte_range():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    located = {(o.evidence.path, o.evidence.lines) for o in report.operations}
    assert ("api/pay.py", "31") in located
    assert ("jobs/settle.py", "12") in located
    assert len(located) == 4


def test_http_methods_map_to_verbs():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    by_binding = {o.binding: o.verb for o in report.operations}
    assert by_binding["POST /api/payments"] is OperationVerb.CREATE
    assert by_binding["GET /api/payments/{id}"] is OperationVerb.READ
    assert by_binding["DELETE /api/payments/{id}"] is OperationVerb.DELETE
    assert by_binding["settle_nightly"] is OperationVerb.SCHEDULE


def test_an_unrecognized_method_is_invoke_not_dropped():
    report = decompose(
        {"BC-014": [_m(MemberKind.HTTP_ROUTE, "TRACE /debug")]}, contract_collected=MEASURED
    )
    assert len(report.operations) == 1
    assert report.operations[0].verb is OperationVerb.INVOKE
    assert report.operations[0].rule == "unrecognized_http_method"


def test_operations_are_named_verb_object():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    names = {o.name for o in report.operations}
    assert "create_payment" in names
    assert "read_payment" in names


def test_a_frontend_route_reduces_through_route_object():
    """A raw URL through head_token would reduce to garbage."""
    report = decompose(
        {"BC-014": [_m(MemberKind.FRONTEND_ROUTE, "/payments/:id", "app.tsx")]},
        contract_collected=MEASURED,
    )
    assert report.operations[0].object == "payment"
    assert report.operations[0].verb is OperationVerb.RENDER


def test_an_underivable_object_is_empty_and_named_by_its_verb():
    report = decompose(
        {"BC-014": [_m(MemberKind.HTTP_ROUTE, "GET /api/v1")]}, contract_collected=MEASURED
    )
    assert report.operations[0].object == ""
    assert report.operations[0].name == "read"


def test_a_non_route_object_is_empty_because_no_deterministic_rule_exists():
    """Review finding 1: head_token on a command name returns the VERB
    ('create_payment' -> 'create'), which assign() would then match against
    entity keys -- garbage stated as evidence. A CLI name is verb-first, a
    topic is entity-first, a job name may carry no entity at all, so there
    is no single-position rule; object stays "" and entity_keys carries the
    contact surface instead. The operation's own name IS the command name."""
    report = decompose(
        {
            "BC-014": [
                _m(MemberKind.CLI_COMMAND, "sync_orders", "cli.py", 4),
                _m(MemberKind.QUEUE_TOPIC, "orders.created", "mq.py", 9),
                _m(MemberKind.SCHEDULED_JOB, "settle_nightly", "jobs/settle.py", 12),
            ]
        },
        contract_collected=MEASURED,
    )
    by_binding = {o.binding: o for o in report.operations}
    for op in report.operations:
        assert op.object == ""
    assert by_binding["sync_orders"].name == "sync_orders"
    assert by_binding["orders.created"].name == "orders.created"
    assert by_binding["settle_nightly"].name == "settle_nightly"
    # Contact keys: every separator token of the binding, reduced. This is
    # what lets a CLI-written table reach UNDIRECTED instead of UNCLAIMED.
    assert by_binding["sync_orders"].entity_keys == ("order", "sync")
    assert by_binding["orders.created"].entity_keys == ("created", "order")
    assert by_binding["settle_nightly"].entity_keys == ("nightly", "settle")


def test_route_object_matching_stays_strict():
    """Only HTTP routes carry directed verbs, so only they can make an
    ownership claim; their keys stay exactly the route object -- loose
    token matching is reserved for the undirected kinds, where the worst
    outcome is an extra UNDIRECTED claimant, never a fabricated owner."""
    report = decompose(
        {
            "BC-014": [
                _m(MemberKind.HTTP_ROUTE, "GET /orders/{id}/items"),
            ]
        },
        contract_collected=MEASURED,
    )
    op = report.operations[0]
    assert op.object == "order"
    assert op.entity_keys == ("order",)


def test_non_contract_kinds_yield_no_operations():
    """D4, and a MEASURED zero -- not a gap."""
    report = decompose(
        {
            "BC-009": [
                _m(MemberKind.EXPORTED_SYMBOL, "parse"),
                _m(MemberKind.TEST_NAME, "test_parse"),
                _m(MemberKind.DB_TABLE, "orders"),
            ]
        },
        contract_collected=MEASURED,
    )
    assert report.operations == ()
    assert report.by_capability == {"BC-009": 0}
    assert report.collected.state is CollectionState.MEASURED


def test_op_ids_are_positional_and_capability_scoped():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    assert [o.op_id for o in report.operations] == [
        "BC-014-OP-01",
        "BC-014-OP-02",
        "BC-014-OP-03",
        "BC-014-OP-04",
    ]


def test_a_degraded_contract_tier_yields_no_rows():
    """D9/FR-915: S3 failing closed must not read as a capability with no
    operations."""
    report = decompose(
        {"BC-014": PAYMENTS},
        contract_collected=Measurement.not_collected("S3 reported not_collected"),
    )
    assert report.operations == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S3" in report.collected.reason


def test_a_degraded_report_names_no_capability_counts():
    """Review finding 7: by_capability[bc]=0 is a MEASURED claim ('exposes
    zero operations'); under a gap the dict must be empty, not zero-filled
    -- the absent-key-vs-zero distinction FR-915 is made of."""
    report = decompose(
        {"BC-014": PAYMENTS},
        contract_collected=Measurement.not_collected("S3 reported not_collected"),
    )
    assert report.by_capability == {}


def test_output_is_byte_identical_across_input_order():
    """NFR-10, asserted in this module's own test file."""
    shuffled = list(PAYMENTS)
    random.Random(20260814).shuffle(shuffled)
    first = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    second = decompose({"BC-014": shuffled}, contract_collected=MEASURED)
    assert first.model_dump_json() == second.model_dump_json()
