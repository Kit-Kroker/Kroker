"""QS2: coverage without running the suite (D12). A committed report when
there is one, BrownKit's tested_files/significant_files proxy when there is
not -- and never a bare percentage."""
from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_COVERAGE, Confidence, ScanSignalId, ScanUpstream, TestFileRecord,
    TestLevel,
)
from sdlc.assessment.scan.signals import coverage
from sdlc.measurement import CollectionState, Measurement

PATHS = ["src/payments/service.py", "src/payments/gateway.py",
         "src/payments/__init__.py", "tests/test_service.py"]

REPORT = """<?xml version="1.0" ?>
<coverage line-rate="0.75">
  <packages><package name="payments"><classes>
    <class filename="src/payments/service.py" line-rate="0.9"/>
    <class filename="src/payments/gateway.py" line-rate="0.2"/>
  </classes></package></packages>
</coverage>
"""


def _qs1_ok() -> ScanUpstream:
    return ScanUpstream(
        tests=[TestFileRecord(
            path="tests/test_service.py", level=TestLevel.UNIT,
            rule="qs1_unit_by_elimination", mapping_rule="naming_convention",
            covers=["src/payments/service.py"], confidence=Confidence.MEDIUM)],
        collected={ScanSignalId.QS1: Measurement.measured(1.0)})


def test_a_committed_report_is_read_per_file():
    out = coverage.evaluate(PATHS, {"coverage.xml": REPORT}, _qs1_ok())
    by_path = {r.path: r for r in out.coverage}
    assert by_path["src/payments/service.py"].covered.value == 90.0
    assert by_path["src/payments/service.py"].source == "report"
    assert by_path["src/payments/service.py"].tool == "cobertura"
    assert by_path["src/payments/service.py"].confidence is Confidence.HIGH


def test_the_proxy_is_used_when_no_report_is_committed():
    """BrownKit's own adaptation rule, and D12's consequence: running the
    suite would execute the assessed repository's code a second time."""
    out = coverage.evaluate(PATHS, {}, _qs1_ok())
    assert [r.scope for r in out.coverage] == ["package"]
    record = out.coverage[0]
    assert record.path == "src/payments"
    # one significant file of two is covered by a test (__init__.py is not
    # significant)
    assert record.covered.value == 50.0
    assert record.source == "proxy"
    assert record.confidence is Confidence.LOW


def test_the_proxy_is_unavailable_when_qs1_did_not_collect():
    """Section 5: a missing QS1 must not make QS2 read as zero coverage."""
    up = ScanUpstream(collected={
        ScanSignalId.QS1: Measurement.not_collected("QS1 timed out")})
    out = coverage.evaluate(PATHS, {}, up)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "QS1" in out.row.categories[C_COVERAGE].reason
    assert out.coverage == []


def test_a_report_is_used_even_when_qs1_degraded():
    """The report path does not depend on QS1 at all, so a QS1 failure must
    not suppress a coverage number the repository actually committed."""
    up = ScanUpstream(collected={
        ScanSignalId.QS1: Measurement.not_collected("QS1 timed out")})
    out = coverage.evaluate(PATHS, {"coverage.xml": REPORT}, up)
    assert out.row.collected.state is CollectionState.MEASURED
    assert all(r.source == "report" for r in out.coverage)


def test_a_non_finite_rate_is_unknown_not_measured():
    """The guard measure_coverage already carries, for the same reason: nan
    >= threshold is False, which fabricates a passing advisory."""
    bad = REPORT.replace('line-rate="0.9"', 'line-rate="nan"').replace(
        'line-rate="0.2"', 'line-rate="inf"')
    out = coverage.evaluate(PATHS, {"coverage.xml": bad}, _qs1_ok())
    assert out.row.categories[C_COVERAGE].state is CollectionState.UNKNOWN
    assert out.coverage == []


def test_an_unparseable_report_falls_back_to_the_proxy():
    out = coverage.evaluate(PATHS, {"coverage.xml": "<not xml"}, _qs1_ok())
    assert all(r.source == "proxy" for r in out.coverage)


def test_output_is_byte_identical_across_input_orderings():
    reference = coverage.evaluate(PATHS, {}, _qs1_ok()).model_dump_json()
    assert coverage.evaluate(list(reversed(PATHS)), {},
                             _qs1_ok()).model_dump_json() == reference
