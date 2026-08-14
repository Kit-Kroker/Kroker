"""S3 -- backend entry points, the Contract tier.

Two rules carry the weight: BrownKit's "group by business operation, not
technical type", and P2-D1's fail-closed reading of D5.
"""
from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_BACKEND_ENTRY, Confidence, MemberKind, ScanSignalId,
)
from sdlc.assessment.scan.signals import entrypoints
from sdlc.measurement import CollectionState

FASTAPI = {
    "src/payments/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/api/payments')\n"
        "def create_payment():\n"
        "    ...\n"
        "\n"
        "@router.get('/api/payments/{payment_id}')\n"
        "def get_payment():\n"
        "    ...\n"
    ),
}


def _by_id(out):
    return {c.local_id: c for c in out.sources}


def test_fastapi_routes_become_http_route_members():
    out = entrypoints.evaluate(FASTAPI)
    pay = _by_id(out)["S3-payment"]
    values = {m.value for m in pay.members}
    assert "POST /api/payments" in values
    assert "GET /api/payments/{payment_id}" in values
    assert all(m.kind is MemberKind.HTTP_ROUTE for m in pay.members)


FLASK = {
    "src/app.py": (
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "\n"
        "@app.route('/api/payments', methods=['POST'])\n"
        "def create_payment():\n"
        "    ...\n"
        "\n"
        "@app.route('/api/payments/{id}', methods=['GET', 'POST'])\n"
        "def get_or_create():\n"
        "    ...\n"
        "\n"
        "@app.route('/health')\n"
        "def health():\n"
        "    ...\n"
    ),
}


def test_flask_methods_kwarg_is_read_not_synthesized_as_get():
    """Review finding 2: a POST route recorded as 'GET /path' is a false S3
    artifact in its own right, and downstream it turns every Flask write
    into a read, so ownership falls to the wrong rule. The kwarg is
    capturable evidence; capture it. A bare @route keeps Flask's own GET
    default; a mixed methods= list names its first declared method -- one
    of the route's true methods, never a guess."""
    out = entrypoints.evaluate(FLASK)
    payment = _by_id(out)["S3-payment"]
    values = {m.value for m in payment.members}
    assert "POST /api/payments" in values
    assert "GET /api/payments/{id}" in values
    health = _by_id(out)["S3-health"]
    assert {m.value for m in health.members} == {"GET /health"}


def test_routes_and_jobs_and_consumers_group_into_one_candidate():
    """D9's ported rule: PaymentController + PaymentSettlementJob +
    PaymentEventConsumer is ONE candidate, not three. Do not split by
    channel."""
    blobs = dict(FASTAPI)
    blobs["src/jobs/PaymentSettlementJob.py"] = (
        "from celery import shared_task\n"
        "@shared_task\n"
        "def settle_daily():\n"
        "    ...\n"
    )
    out = entrypoints.evaluate(blobs)
    assert set(_by_id(out)) == {"S3-payment"}
    kinds = {m.kind for m in _by_id(out)["S3-payment"].members}
    assert kinds == {MemberKind.HTTP_ROUTE, MemberKind.SCHEDULED_JOB}


def test_cross_channel_corroboration_contributes_high():
    blobs = dict(FASTAPI)
    blobs["src/jobs/PaymentSettlementJob.py"] = (
        "from celery import shared_task\n@shared_task\ndef settle():\n    ...\n")
    out = entrypoints.evaluate(blobs)
    assert _by_id(out)["S3-payment"].confidence_contribution is Confidence.HIGH


def test_a_single_entry_point_contributes_low():
    out = entrypoints.evaluate({
        "src/health.py": ("from fastapi import FastAPI\napp = FastAPI()\n"
                          "@app.get('/health')\ndef health():\n    ...\n")})
    assert list(_by_id(out).values())[0].confidence_contribution is \
        Confidence.LOW


def test_a_route_prefix_is_not_the_business_name():
    """/api/payments groups under 'payment', never under 'api'."""
    out = entrypoints.evaluate(FASTAPI)
    assert "S3-api" not in _by_id(out)
    assert "S3-payment" in _by_id(out)


def test_express_routes_are_extracted_without_a_toolchain_adapter():
    """D4: fingerprints live in the signal module, so a TS/JS repo is
    scannable before E-30b exists."""
    out = entrypoints.evaluate({
        "server/orders.js": ("const express = require('express')\n"
                             "const router = express.Router()\n"
                             "router.post('/orders', createOrder)\n")})
    assert "S3-order" in _by_id(out)


def test_click_commands_become_cli_command_members():
    """And 'cli.py' names the delivery channel, not the capability, so the
    candidate takes its parent directory -- E-48's guardrail applied at
    extraction time rather than left for the proposer."""
    out = entrypoints.evaluate({
        "src/billing/cli.py": ("import click\n"
                               "@click.command()\n"
                               "def reconcile():\n    ...\n")})
    assert "S3-billing" in _by_id(out)
    cand = _by_id(out)["S3-billing"]
    assert cand.members[0].kind is MemberKind.CLI_COMMAND
    assert cand.rule == "s3_cli_command"


def test_an_unfingerprinted_framework_fails_the_signal_closed():
    """P2-D1: extracting only the FastAPI half would hand E-47a a partial
    Contract tier at weight 0.55, which is what D5 forbids."""
    blobs = dict(FASTAPI)
    blobs["src/legacy/views.py"] = (
        "from django.http import JsonResponse\n"
        "def legacy_view(request):\n    return JsonResponse({})\n")
    out = entrypoints.evaluate(blobs)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "django" in out.row.collected.reason
    assert out.sources == []            # and nothing partial survives


def test_no_recognized_framework_is_a_gap_not_a_zero():
    """D5 literally: never an empty route list. 'This repo has no backend'
    and 'this backend uses something we cannot parse' are not
    distinguishable, and only one of them is safe to assert."""
    out = entrypoints.evaluate({"src/lib/math.py": "def add(a, b):\n    return a + b\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "no recognized backend framework" in out.row.collected.reason
    assert out.sources == []


def test_a_framework_mentioned_only_in_a_comment_or_string_is_not_detected():
    """Review finding 4 / P2-D1: detection keys fail-closed, so it must be as
    precise as extraction. A `# ported from django` comment, a string literal
    holding a marker, or the marker table itself must NOT cost a repo its
    whole Contract tier. Only an IMPORT counts."""
    blobs = {
        "src/notes.py": (
            "# this module was ported from django years ago\n"
            "MARKERS = ('from django', 'import django', 'org.springframework')\n"
            "note = \"see fastapi docs\"\n"
            "def add(a, b):\n    return a + b\n"),
    }
    supported, unsupported = entrypoints.detected(blobs)
    assert supported == set()
    assert unsupported == set()
    out = entrypoints.evaluate(blobs)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "no recognized backend framework" in out.row.collected.reason


def test_an_unfingerprinted_framework_imported_for_real_fails_closed():
    """The corollary: a real `from django` import DOES trip detection, so the
    repo loses its Contract tier until a fingerprint exists. This is the
    behaviour the comment/string test above must not weaken."""
    out = entrypoints.evaluate({
        "src/app.py": "from django.conf import settings\n"
                      "SECRET = settings.SECRET_KEY\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "django" in out.row.collected.reason


def test_the_row_reports_its_category_and_nothing_else():
    out = entrypoints.evaluate(FASTAPI)
    assert set(out.row.categories) == {C_BACKEND_ENTRY}
    assert out.row.signal is ScanSignalId.S3


def test_evidence_cites_the_file_and_line():
    out = entrypoints.evaluate(FASTAPI)
    ev = _by_id(out)["S3-payment"].evidence
    assert any(e.path == "src/payments/api.py" and e.lines for e in ev)


def test_a_bare_nestjs_decorator_with_no_path_is_a_miss_not_a_verb_candidate():
    """Review finding 2 / D5: NestJS `@Get()` (no path) extracts an empty
    value. Emitting it would build a 'GET ' member and group unrelated
    controllers under the HTTP verb. A route whose path we cannot read is a
    miss -- never a fabricated grouping at Contract-tier weight."""
    blobs = {
        "src/orders/orders.controller.ts": (
            "import { Controller, Get } from '@nestjs/common'\n"
            "@Controller('orders')\n"
            "export class OrdersController {\n"
            "  @Get()\n"
            "  list() {}\n"
            "}\n"),
        "src/users/users.controller.ts": (
            "import { Controller, Get, Post } from '@nestjs/common'\n"
            "@Controller('users')\n"
            "export class UsersController {\n"
            "  @Get()\n"
            "  list() {}\n"
            "  @Post()\n"
            "  create() {}\n"
            "}\n"),
    }
    out = entrypoints.evaluate(blobs)
    ids = set(_by_id(out))
    assert "S3-get" not in ids and "S3-post" not in ids
    # No member carries a bare verb with no route behind it.
    for cand in out.sources:
        for m in cand.members:
            assert m.value.split()[0] != m.value.strip()


def test_a_layer_parent_is_not_adopted_as_the_business_name():
    """Review finding 5: a layer/generic stem falls back to its ancestor, but
    the ancestor is re-checked -- 'server/index.js' and 'src/api/routes.py'
    must not become S3-server / S3-api, which contradict the rule that /api
    is a prefix, not a capability."""
    out = entrypoints.evaluate({
        "src/api/routes.py": (
            "from flask import Flask\napp = Flask(__name__)\n"
            "@app.route('/v1/')\ndef root():\n    ...\n"),
        "server/index.js": (
            "const express = require('express')\nconst app = express()\n"
            "app.get('/')\n"),
    })
    ids = set(_by_id(out))
    assert "S3-api" not in ids
    assert "S3-server" not in ids


def test_output_is_order_independent():
    """NFR-10: dict iteration order must not reach the artifact."""
    blobs = dict(FASTAPI)
    blobs["src/orders/api.py"] = (
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "@router.get('/orders')\ndef list_orders():\n    ...\n")
    a = entrypoints.evaluate(blobs)
    b = entrypoints.evaluate(dict(reversed(list(blobs.items()))))
    assert a.model_dump_json() == b.model_dump_json()
