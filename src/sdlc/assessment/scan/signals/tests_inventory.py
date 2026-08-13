"""QS1 -- test inventory (FR-912). The computed half of an EXTENDED signal:
triage's baseline already counted test FILES (the inherited tests_present
category), and this adds the two facts a count cannot carry -- what LEVEL each
test is, and WHAT it covers.

The mapping is what QS2's proxy coverage is computed from, so an over-eager
mapping inflates a coverage number in a product that sells measurement. An
ambiguous match is therefore `unmapped`, never a guess.

Pure: paths and blobs in, records out.
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ..models import (
    C_TEST_LEVELS, C_TEST_MAPPING, C_TESTS_PRESENT, Confidence, ScanSignalId,
    ScanSignalResult, SignalOutput, SignalSource, TestFileRecord, TestLevel,
    family_of, inherited_pending,
)
from ..sources import SOURCE_EXTENSIONS
from ..testpaths import is_test_path

SIGNAL_ID = "QS1"
VERSION = 1

# (framework, signature). First match wins, so the table's order is the rule.
FRAMEWORKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("playwright", re.compile(r"@playwright/test|playwright\.config")),
    ("cypress", re.compile(r"\bcy\.\w+\(|cypress/support")),
    ("selenium", re.compile(r"\bselenium\b|webdriver")),
    ("k6", re.compile(r"from\s+['\"]k6['\"]")),
    ("locust", re.compile(r"\blocust\b|HttpUser")),
    ("pact", re.compile(r"\bpact\b", re.IGNORECASE)),
    ("vitest", re.compile(r"from\s+['\"]vitest['\"]")),
    ("jest", re.compile(r"@jest/globals|\bjest\.(?:mock|fn)\(")),
    ("mocha", re.compile(r"require\(['\"]mocha['\"]\)")),
    ("pytest", re.compile(r"(?m)^\s*(?:import\s+pytest\b|def\s+test_)")),
    ("unittest", re.compile(r"(?m)^\s*import\s+unittest\b")),
    ("junit", re.compile(r"import\s+org\.junit")),
    ("nunit", re.compile(r"using\s+NUnit")),
    ("xunit", re.compile(r"using\s+Xunit")),
    ("gotest", re.compile(r"(?m)^func\s+Test\w+\(")),
    ("rspec", re.compile(r"(?m)^\s*(?:RSpec\.)?describe\b")),
    ("phpunit", re.compile(r"PHPUnit\\Framework")),
)

# (level, rule, path regex or None, content regex or None). ORDERED: the
# strongest claim first, so an e2e test that also touches a database is e2e
# rather than integration.
_LEVEL_RULES: tuple[tuple[TestLevel, str, re.Pattern[str] | None,
                          re.Pattern[str] | None], ...] = (
    (TestLevel.MANUAL, "qs1_manual_test_plan",
     re.compile(r"(?i)(^|/)(docs/)?test[-_]?plans?/|\.md$"),
     re.compile(r"(?i)manual test")),
    (TestLevel.E2E, "qs1_e2e_marker",
     re.compile(r"(?i)(^|/)(e2e|cypress|playwright)/|\.cy\.[jt]sx?$"),
     re.compile(r"@playwright/test|\bcy\.\w+\(|\bselenium\b|webdriver")),
    (TestLevel.PERFORMANCE, "qs1_performance_marker",
     re.compile(r"(?i)(^|/)(perf|performance|load|bench)/"),
     re.compile(r"from\s+['\"]k6['\"]|\blocust\b|HttpUser|\bgatling\b")),
    (TestLevel.CONTRACT, "qs1_contract_marker",
     re.compile(r"(?i)(^|/)contracts?/"),
     re.compile(r"(?i)\bpact\b|spring-cloud-contract|schemathesis")),
    (TestLevel.INTEGRATION, "qs1_integration_marker",
     re.compile(r"(?i)(^|/)(integration|it)/"),
     re.compile(r"testcontainers|psycopg|sqlalchemy\.create_engine"
                r"|TestClient\(|supertest|requests\.(?:get|post)\("
                r"|docker|@SpringBootTest")),
)

_STEM_RULES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test_(?P<stem>.+)$"),
    re.compile(r"^(?P<stem>.+)_test$"),
    re.compile(r"^(?P<stem>.+)\.test$"),
    re.compile(r"^(?P<stem>.+)\.spec$"),
    re.compile(r"^(?P<stem>.+)\.cy$"),
    re.compile(r"^(?P<stem>.+)_spec$"),
    re.compile(r"^(?P<stem>.+)Tests?$"),
)


def _stem(path: str) -> str:
    """The subject's stem, derived from the test file's name."""
    base = posixpath.splitext(posixpath.basename(path))[0]
    for rule in _STEM_RULES:
        match = rule.match(base)
        if match:
            return match.group("stem")
    return base


def _framework(text: str) -> str:
    for name, signature in FRAMEWORKS:
        if signature.search(text):
            return name
    return ""


def _level(path: str, text: str) -> tuple[TestLevel, str]:
    for level, rule, path_rule, content_rule in _LEVEL_RULES:
        if (path_rule and path_rule.search(path)) or \
                (content_rule and content_rule.search(text)):
            return level, rule
    if _framework(text):
        return TestLevel.UNIT, "qs1_unit_by_elimination"
    # P3-D8: never default to unit. A test-shaped file no rule recognised is
    # a file we could not classify, and calling it a unit test inflates the
    # one number a QA report is read for.
    return TestLevel.UNKNOWN, "qs1_no_level_signature"


def _mapping(path: str, subjects: Mapping[str, list[str]]
             ) -> tuple[str, list[str], Confidence]:
    """(mapping_rule, covers, confidence) for one test file."""
    matches = subjects.get(_stem(path), [])
    if not matches:
        return "unmapped", [], Confidence.LOW
    here = [p for p in matches
            if posixpath.dirname(p) == posixpath.dirname(path)]
    if len(here) == 1:
        return "co_location", here, Confidence.HIGH
    if len(matches) == 1:
        return "naming_convention", list(matches), Confidence.MEDIUM
    # Two subjects with the same stem: guessing would inflate QS2's proxy for
    # whichever package won the coin toss.
    return "unmapped", [], Confidence.LOW


def evaluate(paths: Sequence[str],
             blobs: Mapping[str, str]) -> SignalOutput:
    """`paths` is every tracked path; `blobs` is path -> text for the test
    files that were read."""
    subjects: dict[str, list[str]] = {}
    for path in sorted(paths):
        if is_test_path(path) or not path.endswith(SOURCE_EXTENSIONS):
            continue
        subjects.setdefault(
            posixpath.splitext(posixpath.basename(path))[0], []).append(path)

    records: list[TestFileRecord] = []
    for path in sorted(p for p in paths if is_test_path(p)):
        text = blobs.get(path, "")
        level, rule = _level(path, text)
        mapping_rule, covers, confidence = _mapping(path, subjects)
        records.append(TestFileRecord(
            path=path, level=level, rule=rule, framework=_framework(text),
            covers=covers, mapping_rule=mapping_rule, confidence=confidence))

    records.sort(key=lambda r: r.path)
    levels = Measurement.measured(float(len(records)))
    mapped = Measurement.measured(
        float(sum(1 for r in records if r.mapping_rule != "unmapped")))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS1, family=family_of(ScanSignalId.QS1),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=levels,
            categories={C_TEST_LEVELS: levels, C_TEST_MAPPING: mapped,
                        C_TESTS_PRESENT: inherited_pending(C_TESTS_PRESENT)}),
        tests=records)
