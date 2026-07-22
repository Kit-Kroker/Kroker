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


def test_report_from_malformed_is_zero_critical():
    r = report_from_sarif({"runs": [{"results": "x"}]})
    assert r.critical == 0 and r.findings == []
