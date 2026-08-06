"""SARIF -> SecurityReport normalizer seam (ADR-15 security, FR-108)."""
import pytest

from sdlc.toolchain.sarif import findings_from_sarif, report_from_sarif

WELL_FORMED = {
    "runs": [{
        "results": [
            {"level": "error", "ruleId": "py.eval",
             "message": {"text": "use of eval"},
             "locations": [{"physicalLocation": {
                 "artifactLocation": {"uri": "app/x.py"}}}]},
            {"level": "warning", "ruleId": "py.shell",
             "message": {"text": "shell=True"}},
        ]
    }]
}


def test_wellformed_maps_severity_and_fields():
    fs = findings_from_sarif(WELL_FORMED)
    assert len(fs) == 2
    assert fs[0].severity == "critical" and fs[0].rule == "py.eval"
    assert fs[0].path == "app/x.py" and "eval" in fs[0].detail
    assert fs[1].severity == "high" and fs[1].path == ""


def test_report_counts_critical():
    r = report_from_sarif(WELL_FORMED)
    assert r.critical == 1 and len(r.findings) == 2


@pytest.mark.parametrize("bad", [
    {}, None, "nope", {"runs": "x"}, {"runs": [1, 2]},
    {"runs": [{"results": "x"}]}, {"runs": [{"results": [42]}]},
])
def test_malformed_sarif_is_failsafe_empty(bad):
    assert findings_from_sarif(bad) == []


def test_report_from_malformed_is_not_collected_not_clean():
    """The defect: critical=0 from a broken document was byte-identical to a
    clean scan, and security_no_critical is an ABSOLUTE check."""
    from sdlc.measurement import CollectionState
    r = report_from_sarif({"runs": [{"results": "x"}]})
    assert r.state is CollectionState.NOT_COLLECTED
    assert r.critical == 0 and r.findings == []


def test_report_from_well_formed_is_measured():
    from sdlc.measurement import CollectionState
    assert report_from_sarif(WELL_FORMED).state is CollectionState.MEASURED


def test_report_from_unparseable_results_is_not_collected():
    """results IS a list (so the doc is well-formed) but every entry is
    unparseable garbage -> the scan output is unreadable, NOT a clean
    zero-critical scan. This is the conflation one level deeper than the
    malformed-document case (code review #2)."""
    from sdlc.measurement import CollectionState
    r = report_from_sarif({"runs": [{"results": [42, "garbage", None]}]})
    assert r.state is CollectionState.NOT_COLLECTED
    assert r.critical == 0 and r.findings == []


def test_report_from_empty_results_is_measured_clean():
    """A scan that ran and found nothing (empty results list) is MEASURED --
    the distinction the #2 fix preserves: 'found nothing' != 'read nothing'."""
    from sdlc.measurement import CollectionState
    r = report_from_sarif({"runs": [{"results": []}]})
    assert r.state is CollectionState.MEASURED
    assert r.critical == 0


def test_report_from_partially_unparseable_results_is_measured():
    """A mix of one parseable and one garbage entry still read as a scan that
    ran -- we salvaged a finding, so it is not NOT_COLLECTED."""
    from sdlc.measurement import CollectionState
    r = report_from_sarif({"runs": [{"results": [
        {"level": "error", "ruleId": "x", "message": {"text": "x"}}, 42] }]})
    assert r.state is CollectionState.MEASURED
    assert len(r.findings) == 1
