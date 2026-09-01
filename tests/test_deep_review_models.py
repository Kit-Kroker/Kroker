from sdlc.models import (
    DeepReviewReport,
    IntegrityFlag,
    PipelineConfig,
    ReviewFinding,
    TaskResult,
)


def test_cheat_detected_true_iff_flags_present():
    clean = DeepReviewReport()
    assert clean.approve is True
    assert clean.cheat_detected is False
    flagged = DeepReviewReport(
        integrity_flags=[
            IntegrityFlag(
                kind="oracle_peeking",
                detail="read oracle/",
                evidence="file_read oracle/test_app.py",
            )
        ]
    )
    assert flagged.cheat_detected is True


def test_report_is_evidence_first():
    # Field order is the SGR contract: evidence before verdict. plan_deviations
    # (E-83) is evidence-first too, so it sits with the evidence group.
    fields = list(DeepReviewReport.model_fields)
    assert fields == [
        "findings",
        "integrity_flags",
        "plan_deviations",
        "summary",
        "approve",
        "confidence",
    ]


def test_report_reuses_review_finding():
    r = DeepReviewReport(findings=[ReviewFinding(assertion="a1", severity="low", detail="nit")])
    assert r.findings[0].severity == "low"


def test_task_result_carries_optional_deep_review():
    tr = TaskResult(task_id="t1", status="done", attempts=1, branch="b")
    assert tr.deep_review is None


def test_deep_review_disabled_by_default():
    assert PipelineConfig().deep_review_enabled is False
