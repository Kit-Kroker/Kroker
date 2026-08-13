"""QS1: every test file, its level, and what it covers. The mapping is what
QS2's proxy is computed from, so an over-eager mapping inflates a coverage
number -- which is why an ambiguous match is `unmapped`, not a guess."""
from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_TEST_LEVELS, C_TEST_MAPPING, C_TESTS_PRESENT, TestLevel,
)
from sdlc.assessment.scan.signals import tests_inventory
from sdlc.measurement import CollectionState

PATHS = [
    "src/payments/service.py",
    "src/payments/gateway.py",
    "tests/test_service.py",
    "tests/integration/test_gateway.py",
    "e2e/checkout.spec.ts",
    "src/web/Button.tsx",
    "src/web/Button.test.tsx",
]
BLOBS = {
    "tests/test_service.py": (
        "import pytest\n"
        "from payments.service import settle\n"
        "def test_settle():\n    assert settle(1)\n"),
    "tests/integration/test_gateway.py": (
        "import pytest, psycopg\n"
        "def test_gateway_writes():\n    ...\n"),
    "e2e/checkout.spec.ts": (
        "import { test, expect } from '@playwright/test';\n"
        "test('checkout', async ({ page }) => {});\n"),
    "src/web/Button.test.tsx": (
        "import { describe, it } from 'vitest';\n"
        "describe('Button', () => { it('renders', () => {}) });\n"),
}


def test_every_test_file_is_inventoried():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    assert {r.path for r in out.tests} == {
        "tests/test_service.py", "tests/integration/test_gateway.py",
        "e2e/checkout.spec.ts", "src/web/Button.test.tsx"}


def test_levels_are_classified_by_the_strongest_signal_first():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    level = {r.path: r.level for r in out.tests}
    assert level["e2e/checkout.spec.ts"] is TestLevel.E2E
    assert level["tests/integration/test_gateway.py"] is TestLevel.INTEGRATION
    assert level["tests/test_service.py"] is TestLevel.UNIT
    assert level["src/web/Button.test.tsx"] is TestLevel.UNIT


def test_frameworks_are_recorded_when_a_signature_matches():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    framework = {r.path: r.framework for r in out.tests}
    assert framework["tests/test_service.py"] == "pytest"
    assert framework["e2e/checkout.spec.ts"] == "playwright"
    assert framework["src/web/Button.test.tsx"] == "vitest"


def test_a_test_with_no_signature_is_unknown_not_unit():
    out = tests_inventory.evaluate(
        ["tests/test_mystery.py"], {"tests/test_mystery.py": "x = 1\n"})
    assert out.tests[0].level is TestLevel.UNKNOWN
    assert out.tests[0].rule == "qs1_no_level_signature"


def test_the_naming_convention_maps_a_test_to_its_subject():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    by_path = {r.path: r for r in out.tests}
    assert by_path["tests/test_service.py"].covers == ["src/payments/service.py"]
    assert by_path["tests/test_service.py"].mapping_rule == "naming_convention"


def test_a_co_located_test_prefers_its_own_directory():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    button = next(r for r in out.tests if r.path == "src/web/Button.test.tsx")
    assert button.covers == ["src/web/Button.tsx"]
    assert button.mapping_rule == "co_location"


def test_an_ambiguous_match_is_unmapped_rather_than_a_guess():
    """Two `service.py` files and one `test_service.py`: guessing would
    inflate QS2's proxy for whichever package won the coin toss."""
    paths = ["src/a/service.py", "src/b/service.py", "tests/test_service.py"]
    out = tests_inventory.evaluate(paths, {"tests/test_service.py": "import pytest\ndef test_x(): ...\n"})
    record = out.tests[0]
    assert record.mapping_rule == "unmapped"
    assert record.covers == []


def test_both_computed_categories_report_and_the_inherited_one_is_pending():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    assert out.row.categories[C_TEST_LEVELS].state is CollectionState.MEASURED
    assert out.row.categories[C_TEST_MAPPING].state is CollectionState.MEASURED
    # D7: the workflow folds this one in; the activity must still declare it.
    pending = out.row.categories[C_TESTS_PRESENT]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason


def test_a_repository_with_no_tests_is_a_measured_zero():
    out = tests_inventory.evaluate(["src/a.py"], {})
    assert out.row.categories[C_TEST_LEVELS].value == 0.0
    assert out.tests == []
