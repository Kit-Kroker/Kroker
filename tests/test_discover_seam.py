"""The decompose() -> assign() seam (review finding 1's test-design gap).

The two modules were each unit-tested in isolation and the seam was never
exercised, which is how a fabricated object survived: the ownership tests
built L2Operations by hand -- object set by hand -- that decompose() would
never produce. These tests pipe one into the other, with members shaped
exactly as S3 emits them.
"""
from __future__ import annotations

from sdlc.assessment.discover.models import (
    EntityDeclaration, OwnershipOutcome, OwnershipVerb,
)
from sdlc.assessment.discover.operations import decompose
from sdlc.assessment.discover.ownership import assign
from sdlc.assessment.scan.models import CandidateMember, MemberKind
from sdlc.measurement import Measurement

MEASURED = Measurement.measured(1.0)
ORDERS = EntityDeclaration(name="orders", path="db/models/order.py", line=8)
PAYMENTS = EntityDeclaration(name="payments", path="db/models/pay.py", line=3)


def _m(kind: MemberKind, value: str, path: str, line: int):
    return CandidateMember(kind=kind, value=value, path=path, line=line)


def _seam(members, declarations, member_paths):
    operations = decompose(members, contract_collected=MEASURED).operations
    return assign(declarations, member_paths, operations,
                  schema_collected=MEASURED, contract_collected=MEASURED)


def _row(report, entity: str):
    return next(e for e in report.entities if e.entity == entity)


def test_a_cli_written_table_is_undirected_not_unclaimed():
    """The review's reproduced defect: orders touched only by a
    sync_orders CLI job resolved to UNCLAIMED, because decompose()'s
    object for the command was 'sync'. D8 exists to prevent exactly this
    reading -- a CLI-written table is not an untouched table."""
    report = _seam(
        {"BC-014": [_m(MemberKind.CLI_COMMAND, "sync_orders", "cli.py", 7)]},
        [ORDERS], {"BC-014": ["cli.py"]})
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.UNDIRECTED
    assert row.claimants == ("BC-014",)


def test_a_flask_shaped_post_route_owns_its_table():
    """S3 records Flask methods= routes truthfully since review finding 2;
    through the seam, the POST member decomposes to CREATE and the writer
    owns the table its declaration site does not cover."""
    report = _seam(
        {"BC-014": [_m(MemberKind.HTTP_ROUTE, "POST /api/payments",
                       "api/pay.py", 31)]},
        [PAYMENTS], {"BC-014": ["api/pay.py"]})
    row = _row(report, "payment")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-014"
    assert row.verb is OwnershipVerb.CREATES
    assert row.rule == "sole_writer"


def test_a_sole_reader_keeps_its_undirected_co_claimant():
    """A GET route on orders in one capability and a settle CLI job naming
    orders in another: the reader owns, and the row still shows the CLI's
    contact rather than erasing it (review finding 3, through the seam)."""
    report = _seam({
        "BC-007": [_m(MemberKind.HTTP_ROUTE, "GET /api/orders/{id}",
                      "api/orders.py", 12)],
        "BC-014": [_m(MemberKind.SCHEDULED_JOB, "settle_orders",
                      "jobs/settle.py", 3)],
    }, [ORDERS], {"BC-007": ["api/orders.py"], "BC-014": ["jobs/settle.py"]})
    row = _row(report, "order")
    assert row.outcome is OwnershipOutcome.OWNED
    assert row.owner == "BC-007"
    assert row.claimants == ("BC-007", "BC-014")
