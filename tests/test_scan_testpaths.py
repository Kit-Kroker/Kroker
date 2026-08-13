"""P3-D9: four signals ask the same 'is this a test path?' question. Four
copies would agree only by coincidence, which is why naming.py and sources.py
are sited once and declared as rule modules."""
from __future__ import annotations

import pytest

from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.testpaths import TEST_PATH_GLOBS, is_test_path


@pytest.mark.parametrize("path", [
    "tests/test_api.py",
    "src/app/test_service.py",
    "src/app/service_test.py",
    "conftest.py",
    "src/components/Button.test.tsx",
    "src/components/Button.spec.ts",
    "src/__tests__/render.js",
    "cypress/e2e/login.cy.ts",
    "internal/server/handler_test.go",
    "src/test/java/com/acme/OrderTest.java",
    "spec/models/user_spec.rb",
    "e2e/checkout.spec.ts",
])
def test_test_paths_are_recognized(path):
    assert is_test_path(path) is True


@pytest.mark.parametrize("path", [
    "src/app/service.py",
    "src/components/Button.tsx",
    "internal/server/handler.go",
    "contest.py",                 # not conftest.py
    "src/latest/index.ts",        # 'test' inside a word is not a test path
    "migrations/0001_init.sql",
])
def test_production_paths_are_not(path):
    assert is_test_path(path) is False


def test_the_four_consumers_all_declare_it_as_a_rule_module():
    """Without the declaration, adding a glob would change four signals'
    output while their memo keys stood still -- the D10 hazard."""
    module = "sdlc.assessment.scan.testpaths"
    for sid in (ScanSignalId.S2, ScanSignalId.QS1, ScanSignalId.QS2,
                ScanSignalId.QS3):
        assert module in SCAN_SIGNALS[sid].rule_modules, sid.value


def test_the_glob_table_is_not_empty():
    assert len(TEST_PATH_GLOBS) > 10
