"""SC-5's sibling: an absolute floor that could not be measured must not be
silently satisfied."""

from sdlc.gate import (
    ABSOLUTE_FLOOR,
    CheckClass,
    build_check,
    evaluate_quality_gate,
)
from sdlc.measurement import CollectionState
from sdlc.stages.qa.models import SecurityReport


def _checks(report: SecurityReport):
    return [
        build_check(
            "security_scan_collected",
            report.state is CollectionState.MEASURED,
            CheckClass.ABSOLUTE,
            detail=report.reason or "scan ran",
        ),
        build_check(
            "security_no_critical",
            report.critical == 0,
            CheckClass.ABSOLUTE,
            detail=f"{report.critical} critical finding(s)",
        ),
    ]


def test_collection_check_is_in_the_absolute_floor():
    """ABSOLUTE_FLOOR forces the classification regardless of what a caller
    requests. A collection check outside it could be downgraded to advisory
    at a call site, which is the same bypass by another route."""
    assert "security_scan_collected" in ABSOLUTE_FLOOR


def test_a_caller_cannot_downgrade_the_collection_check():
    c = build_check("security_scan_collected", False, CheckClass.ADVISORY)
    assert c.classification is CheckClass.ABSOLUTE


def test_not_collected_scan_blocks_on_its_own_check():
    report = SecurityReport(
        critical=0, state=CollectionState.NOT_COLLECTED, reason="sarif unparseable"
    )
    result = evaluate_quality_gate(_checks(report))
    assert "security_scan_collected" in result.blocking
    assert "security_no_critical" not in result.blocking


def test_measured_clean_scan_passes_both(required_checks):
    report = SecurityReport(critical=0, state=CollectionState.MEASURED)
    others = [
        c
        for c in required_checks()
        if c.name not in {"security_scan_collected", "security_no_critical"}
    ]
    assert evaluate_quality_gate(others + _checks(report)).blocking == []
