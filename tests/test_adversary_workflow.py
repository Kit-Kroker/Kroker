"""Split verdicts merge both reviewers' findings into the retry prompt."""
from sdlc.models import ReviewFinding, ReviewReport
from sdlc.workflows.feature import _fix_loop_issues


class _QA:
    issues: list = []
    failing_tests: list = []


class _QARaw:
    tests_passed = True
    issues: list = []
    failing_tests: list = []


def _report(approve, detail):
    return ReviewReport(
        approve=approve,
        findings=[ReviewFinding(assertion="A1", severity="high",
                                detail=detail, suggested_fix="fix it")],
    )


def test_adversary_none_reproduces_todays_output():
    review = _report(False, "primary finding")
    assert (_fix_loop_issues(_QA(), _QARaw(), review, None)
            == _fix_loop_issues(_QA(), _QARaw(), review))


def test_both_reviewers_findings_reach_the_retry():
    issues = _fix_loop_issues(_QA(), _QARaw(), _report(True, "primary finding"),
                              _report(False, "adversary finding"))
    assert "primary finding" in issues
    assert "adversary finding" in issues


def test_adversary_findings_alone_are_actionable():
    """The primary approved and produced nothing; the retry must still have
    an instruction, or the loop sends a bare dash."""
    issues = _fix_loop_issues(_QA(), _QARaw(), ReviewReport(approve=True),
                              _report(False, "adversary finding"))
    assert "adversary finding" in issues
    assert issues.strip()


def test_low_severity_adversary_findings_are_not_blocking():
    """blocking_findings is critical/high only -- same rule as the primary."""
    adv = ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="A1", severity="low",
                                detail="nit", suggested_fix="")],
    )
    assert "nit" not in _fix_loop_issues(_QA(), _QARaw(),
                                         ReviewReport(approve=True), adv)


import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def _src() -> str:
    return SRC.read_text(encoding="utf-8")


def test_adversary_helper_exists_and_is_config_gated():
    src = _src()
    assert "async def _run_adversary" in src
    assert "cfg.adversarial_review_enabled" in src
    assert "t_adversary is not None" in src


def test_success_predicate_is_unchanged():
    """The adversary gates INSIDE the block, never by widening the
    predicate -- same invariant test_deep_review_wiring.py protects."""
    assert "if task_passed and review_ok:" in _src()


def test_adversary_runs_only_on_the_approving_path():
    src = _src()
    call = src.find("await self._run_adversary")
    pred = src.find("if task_passed and review_ok:")
    assert pred != -1 and call > pred, (
        "the adversary must be invoked inside the approving block")


def test_adversary_is_fail_open():
    """A failed lens counts as agreement -- it must never fail a task."""
    src = _src()
    idx = src.find("async def _run_adversary")
    body = src[idx: idx + 2600]
    assert "return None" in body
    assert "raise" not in body


def test_adversary_never_touches_the_session():
    """Clean-context: contract + diff + test output only. Reading the
    transcript is deep_review's job and would break decorrelation."""
    src = _src()
    idx = src.find("async def _run_adversary")
    body = src[idx: idx + 2600]
    assert "load_session" not in body
    assert "session_ref" not in body
    assert "run_coding_task" not in body


def test_cause_records_carry_no_fix_attempts():
    """One split must not count three times (spec 4.3)."""
    src = _src()
    for stage in ('stage="review"', 'stage="adversary"', 'stage="handoff"'):
        idx = src.find(stage)
        assert idx != -1, f"{stage} record is not emitted"
        assert "fix_attempts=0" in src[idx: idx + 700], (
            f"{stage} must pass fix_attempts=0")


def test_handoff_is_fail_open_and_never_reaches_a_validator():
    src = _src()
    idx = src.find("async def _run_handoff")
    assert idx != -1
    body = src[idx: idx + 2600]
    assert "return fallback" in body
    # The handoff is passed to TaskResult (consumed by LATER tasks) and to
    # nothing else -- never into a review or QA call.
    assert "_run_review(" not in body
    assert "_run_adversary(" not in body
