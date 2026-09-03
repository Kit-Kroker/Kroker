from sdlc.core.models import (
    PipelineConfig,
    RoleConfig,
)
from sdlc.models import (
    ReviewFinding,
    ReviewReport,
    TaskResult,
)


def test_blocking_findings_filters_to_critical_and_high():
    r = ReviewReport(
        approve=False,
        findings=[
            ReviewFinding(assertion="a1", severity="critical", detail="boom"),
            ReviewFinding(assertion="a2", severity="high", detail="bad"),
            ReviewFinding(assertion="a3", severity="medium", detail="meh"),
            ReviewFinding(assertion="a4", severity="low", detail="nit"),
        ],
    )
    sev = [f.severity for f in r.blocking_findings]
    assert sev == ["critical", "high"]


def test_review_report_approve_defaults_clean():
    r = ReviewReport(approve=True)
    assert r.findings == []
    assert r.blocking_findings == []
    assert r.confidence is None


def test_role_config_proposer_needs_no_harness():
    rc = RoleConfig(kind="proposer", model="anthropic:glm-5.2")
    assert rc.harness is None
    assert rc.kind == "proposer"


def test_task_result_carries_optional_review():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.review is None


def test_review_enabled_defaults_true():
    assert PipelineConfig().review_enabled is True
