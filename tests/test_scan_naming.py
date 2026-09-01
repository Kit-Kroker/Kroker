"""D9: S3's grouping and S5's merge must share one normalizer. Two copies
would agree only by coincidence."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan.naming import (
    GENERIC_NAMES,
    LAYER_NAMES,
    LAYER_SUFFIXES,
    head_token,
    normalize,
    singularize,
)


@pytest.mark.parametrize(
    "word,expected",
    [
        ("payments", "payment"),
        ("categories", "category"),
        ("classes", "class"),
        ("boxes", "box"),
        ("batches", "batch"),
        ("dishes", "dish"),
        ("status", "status"),  # "ss" is not a plural marker
        ("address", "address"),
        ("api", "api"),
        ("s", "s"),  # too short to strip
    ],
)
def test_singularize(word, expected):
    assert singularize(word) == expected


@pytest.mark.parametrize(
    "name",
    [
        "PaymentController",
        "PaymentService",
        "PaymentRepository",
        "PaymentHandler",
        "payments",
        "payment_service",
        "Payments",
    ],
)
def test_the_payments_family_normalizes_to_one_token(name):
    """D9's worked example: PaymentController (S3) + payments/ (S1) must
    reach the same key or S5 cannot merge them."""
    assert normalize(name) == "payment"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("PaymentSettlementJob", "Payment"),
        ("PaymentEventConsumer", "Payment"),
        ("PaymentController", "Payment"),
        ("payment_settlement_job", "payment"),
        ("payments", "payments"),
        ("catcafe", "catcafe"),
        ("HTTPServer", "HTTP"),  # an acronym run is one token
    ],
)
def test_head_token(name, expected):
    assert head_token(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "PaymentController",
        "PaymentSettlementJob",
        "PaymentEventConsumer",
    ],
)
def test_the_three_channel_names_reach_one_merge_key(name):
    """BrownKit's rule verbatim: PaymentController + PaymentSettlementJob +
    PaymentEventConsumer is ONE candidate, not three. Suffix-stripping alone
    does not get there -- 'PaymentSettlementJob' loses only 'Job' and lands
    on 'paymentsettlement' -- so S3 groups on the HEAD token."""
    assert normalize(head_token(name)) == "payment"


def test_the_longest_suffix_wins_not_the_first_declared():
    """Declaration order must not decide behaviour: 'Utils' and 'Util' both
    match, and stripping the shorter one leaves a trailing 's'."""
    assert normalize("StringUtils") == "string"
    assert normalize("StringUtil") == "string"


def test_a_bare_suffix_is_not_stripped_to_nothing():
    """'Service' alone is the whole name; stripping it would yield ''."""
    assert normalize("Service") == "service"


def test_normalize_is_idempotent():
    for name in ("PaymentController", "payments", "OrderService"):
        assert normalize(normalize(name)) == normalize(name)


def test_dotted_layer_suffixes_merge_with_the_package_directory():
    """Review finding 3: a JS/TS stem like `users.controller` must reach the
    same key as S1's `users/` directory or D8 corroboration is unreachable for
    the JS/TS repos the docstring says Tier 0 receives. Without stripping '.',
    the suffix strip leaves a trailing dot: `users.` != `user`."""
    assert normalize("users.controller") == normalize("users") == "user"
    assert normalize("orders.service") == normalize("orders") == "order"


def test_the_name_tables_are_disjoint():
    """A word classified as both generic and layer would make S1's rule
    depend on check order (P2-D2)."""
    assert not (GENERIC_NAMES & LAYER_NAMES)


def test_every_layer_suffix_is_capitalized():
    """The suffixes are matched case-insensitively, but they are declared in
    the form they appear in source so the table reads as documentation."""
    for suffix in LAYER_SUFFIXES:
        assert suffix[0].isupper(), suffix


from sdlc.assessment.scan.naming import PATH_PREFIXES, route_object


def test_route_object_skips_prefixes_and_parameters():
    assert route_object("POST /api/v1/payments") == "payments"
    assert route_object("GET /api/payments/{id}") == "payments"
    assert route_object("GET /v2/orders/:id/items") == "orders"


def test_route_object_reads_a_method_less_value():
    """S4's FRONTEND_ROUTE members carry no method; the last whitespace
    field of a method-less value is the whole path."""
    assert route_object("/payments/:id") == "payments"


def test_route_object_returns_none_when_every_segment_is_a_prefix():
    assert route_object("GET /api/v1") is None
    assert route_object("GET /") is None


def test_route_object_returns_none_for_an_empty_or_blank_value():
    """The helper is public now, so its precondition is enforced, not
    assumed: S3 filters empty extracts today, but a second consumer (or a
    future S5 path) may not (review finding 6)."""
    assert route_object("") is None
    assert route_object("   ") is None


def test_route_object_keeps_segment_case():
    """The raw segment, not a key: callers reduce it themselves."""
    assert route_object("GET /Payments") == "Payments"


def test_path_prefixes_is_importable_and_populated():
    assert "api" in PATH_PREFIXES and "v1" in PATH_PREFIXES
