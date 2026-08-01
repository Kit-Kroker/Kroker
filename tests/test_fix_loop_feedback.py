"""The per-task fix loop gates on `qa_raw.tests_passed` (the subprocess exit
code) but built its retry prompt from the LLM QA's own fields only. When the
clean-context QA judged the diff contract-compliant while pytest was red, the
agent received `Previous attempt has issues. Fix them:\n- ` with nothing after
the dash, and spent its remaining attempts re-confirming the stack directive
(see bench-todo-api-greenfield-1785444047: 8 of 12 attempts burned this way,
while the deterministic ModuleNotFoundError that actually failed the gate was
never shown to it)."""
from sdlc.models import QAReport, ReviewFinding, ReviewReport
from sdlc.workflows.feature import _fix_loop_issues


def _review(*findings: ReviewFinding) -> ReviewReport:
    return ReviewReport(approve=not findings, findings=list(findings))


def test_llm_qa_issues_are_forwarded():
    qa = QAReport(tests_passed=False, issues=["assertion 2 unmet: no 404 path"])
    issues = _fix_loop_issues(qa, QAReport(tests_passed=True), None)
    assert "assertion 2 unmet: no 404 path" in issues


def test_deterministic_test_output_is_forwarded_when_llm_qa_is_silent():
    """The gate anchors on qa_raw; the prompt must carry the same evidence."""
    qa = QAReport(tests_passed=True, issues=[])
    qa_raw = QAReport(tests_passed=False,
                      issues=["E   ModuleNotFoundError: No module named 'fastapi'"])
    issues = _fix_loop_issues(qa, qa_raw, None)
    assert "ModuleNotFoundError" in issues


def test_deterministic_failing_tests_are_forwarded_without_issue_text():
    qa_raw = QAReport(tests_passed=False,
                      failing_tests=["tests/test_app.py::test_delete"])
    issues = _fix_loop_issues(QAReport(tests_passed=True), qa_raw, None)
    assert "tests/test_app.py::test_delete" in issues


def test_both_judges_are_combined_not_shadowed():
    qa = QAReport(tests_passed=False, issues=["assertion 3 unmet"])
    qa_raw = QAReport(tests_passed=False, issues=["1 failed, 40 passed"])
    issues = _fix_loop_issues(qa, qa_raw, None)
    assert "assertion 3 unmet" in issues
    assert "1 failed, 40 passed" in issues


def test_review_blocking_findings_still_included():
    review = _review(ReviewFinding(severity="high", assertion="a1",
                                   detail="unchecked index"))
    issues = _fix_loop_issues(QAReport(tests_passed=True),
                              QAReport(tests_passed=True), review)
    assert "unchecked index" in issues


def test_green_deterministic_run_contributes_nothing():
    """A passing qa_raw must not inject noise into an LLM-QA-only rejection."""
    qa = QAReport(tests_passed=False, issues=["assertion 1 unmet"])
    qa_raw = QAReport(tests_passed=True, issues=[], failing_tests=[])
    assert _fix_loop_issues(qa, qa_raw, None) == "assertion 1 unmet"


def test_no_actionable_feedback_yields_empty_string():
    """Neither judge has anything to say, yet the task was marked failed —
    a harness bug, not a task to re-attempt. Callers branch on this."""
    issues = _fix_loop_issues(QAReport(tests_passed=True),
                              QAReport(tests_passed=False), None)
    assert issues == ""


def test_test_output_is_bounded():
    qa_raw = QAReport(tests_passed=False, issues=["x" * 50_000])
    assert len(_fix_loop_issues(QAReport(tests_passed=True), qa_raw, None)) < 3_000
