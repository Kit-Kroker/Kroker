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
    report = decompose({"BC-014": [_m(MemberKind.HTTP_ROUTE, "TRACE /debug")]},
                       contract_collected=MEASURED)
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
        contract_collected=MEASURED)
    assert report.operations[0].object == "payment"
    assert report.operations[0].verb is OperationVerb.RENDER


def test_an_underivable_object_is_empty_and_named_by_its_verb():
    report = decompose({"BC-014": [_m(MemberKind.HTTP_ROUTE, "GET /api/v1")]},
                       contract_collected=MEASURED)
    assert report.operations[0].object == ""
    assert report.operations[0].name == "read"


def test_non_contract_kinds_yield_no_operations():
    """D4, and a MEASURED zero -- not a gap."""
    report = decompose(
        {"BC-009": [_m(MemberKind.EXPORTED_SYMBOL, "parse"),
                    _m(MemberKind.TEST_NAME, "test_parse"),
                    _m(MemberKind.DB_TABLE, "orders")]},
        contract_collected=MEASURED)
    assert report.operations == ()
    assert report.by_capability == {"BC-009": 0}
    assert report.collected.state is CollectionState.MEASURED


def test_op_ids_are_positional_and_capability_scoped():
    report = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    assert [o.op_id for o in report.operations] == [
        "BC-014-OP-01", "BC-014-OP-02", "BC-014-OP-03", "BC-014-OP-04"]


def test_a_degraded_contract_tier_yields_no_rows():
    """D9/FR-915: S3 failing closed must not read as a capability with no
    operations."""
    report = decompose({"BC-014": PAYMENTS},
                       contract_collected=Measurement.not_collected(
                           "S3 reported not_collected"))
    assert report.operations == ()
    assert report.collected.state is CollectionState.NOT_COLLECTED
    assert "S3" in report.collected.reason


def test_output_is_byte_identical_across_input_order():
    """NFR-10, asserted in this module's own test file."""
    shuffled = list(PAYMENTS)
    random.Random(20260814).shuffle(shuffled)
    first = decompose({"BC-014": PAYMENTS}, contract_collected=MEASURED)
    second = decompose({"BC-014": shuffled}, contract_collected=MEASURED)
    assert first.model_dump_json() == second.model_dump_json()
