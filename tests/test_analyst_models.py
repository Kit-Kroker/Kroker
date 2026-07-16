"""AnalysisReport / CriterionTrace / CoverageReport contracts + config field."""
from sdlc.models import (
    AnalysisReport, CoverageReport, CriterionTrace, PipelineConfig, ReviewFinding,
)


def test_criterion_trace_defaults_to_no_tests():
    t = CriterionTrace(task_id="t1", criterion="GET /hello returns 200")
    assert t.tests == []


def test_analysis_report_defaults_are_empty():
    r = AnalysisReport()
    assert r.traceability == []
    assert r.findings == []
    assert r.summary == ""
    assert r.confidence is None


def test_analysis_report_carries_findings_and_traces():
    r = AnalysisReport(
        traceability=[CriterionTrace(task_id="t1", criterion="c1", tests=["test_c1"])],
        findings=[ReviewFinding(assertion="c1", severity="low", detail="nit")],
        summary="ok", confidence=0.9)
    assert r.traceability[0].tests == ["test_c1"]
    assert r.findings[0].severity == "low"


def test_coverage_report_unmeasured():
    c = CoverageReport(measured=False)
    assert c.diff_pct is None


def test_pipeline_config_coverage_threshold_defaults_off():
    assert PipelineConfig().coverage_threshold == 0.0
