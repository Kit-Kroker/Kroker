"""Split verdicts merge both reviewers' findings into the retry prompt."""

from sdlc.stages.qa.step import _fix_loop_issues
from sdlc.stages.review.models import (
    ReviewFinding,
    ReviewReport,
)


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
        findings=[
            ReviewFinding(assertion="A1", severity="high", detail=detail, suggested_fix="fix it")
        ],
    )


def test_adversary_none_reproduces_todays_output():
    review = _report(False, "primary finding")
    assert _fix_loop_issues(_QA(), _QARaw(), review, None) == _fix_loop_issues(
        _QA(), _QARaw(), review
    )


def test_both_reviewers_findings_reach_the_retry():
    issues = _fix_loop_issues(
        _QA(), _QARaw(), _report(True, "primary finding"), _report(False, "adversary finding")
    )
    assert "primary finding" in issues
    assert "adversary finding" in issues


def test_adversary_findings_alone_are_actionable():
    """The primary approved and produced nothing; the retry must still have
    an instruction, or the loop sends a bare dash."""
    issues = _fix_loop_issues(
        _QA(), _QARaw(), ReviewReport(approve=True), _report(False, "adversary finding")
    )
    assert "adversary finding" in issues
    assert issues.strip()


def test_low_severity_adversary_findings_are_not_blocking():
    """blocking_findings is critical/high only -- same rule as the primary."""
    adv = ReviewReport(
        approve=False,
        findings=[ReviewFinding(assertion="A1", severity="low", detail="nit", suggested_fix="")],
    )
    assert "nit" not in _fix_loop_issues(_QA(), _QARaw(), ReviewReport(approve=True), adv)


import pathlib

FEATURE_SRC = pathlib.Path("src/sdlc/workflows/feature.py")
TASK_HOST_SRC = pathlib.Path("src/sdlc/workflows/task_host.py")
STAGE_SRC = pathlib.Path("src/sdlc/stages/review/step.py")
CODE_SRC = pathlib.Path("src/sdlc/stages/code/step.py")


def _src() -> str:
    return (
        FEATURE_SRC.read_text(encoding="utf-8")
        + "\n"
        + TASK_HOST_SRC.read_text(encoding="utf-8")
        + "\n"
        + STAGE_SRC.read_text(encoding="utf-8")
        + "\n"
        + CODE_SRC.read_text(encoding="utf-8")
    )


def test_adversary_helper_exists_and_is_config_gated():
    src = _src()
    assert "async def _run_adversary" in src
    assert "cfg.adversarial_review_enabled" in src
    assert "t_adversary is not None" in src or "adversary_agent is None" in src


def test_success_predicate_is_unchanged():
    """The adversary gates INSIDE the block, never by widening the
    predicate -- same invariant test_deep_review_wiring.py protects."""
    assert "if task_passed and review_ok:" in _src()


def test_adversary_runs_only_on_the_approving_path():
    src = _src()
    call = src.find("await _run_adversary")
    if call == -1:
        call = src.find("await self._run_adversary")
    pred = src.find("if task_passed and review_ok:")
    assert pred != -1 and call > pred, "the adversary must be invoked inside the approving block"


def test_adversary_is_fail_open():
    """A failed lens counts as agreement -- it must never fail a task."""
    src = _src()
    idx = src.find("async def _run_adversary")
    body = src[idx : idx + 2600]
    assert "return None" in body
    assert "raise" not in body


def test_adversary_never_touches_the_session():
    """Clean-context: contract + diff + test output only. Reading the
    transcript is deep_review's job and would break decorrelation."""
    src = STAGE_SRC.read_text(encoding="utf-8")
    idx = src.find("async def run_adversary")
    body = src[idx : idx + 2600]
    assert "load_session" not in body
    assert "session_ref" not in body
    assert "run_coding_task" not in body


def test_cause_records_carry_no_fix_attempts():
    """One split must not count three times (spec 4.3)."""
    src = _src()
    for stage in ('stage="review"', 'stage="adversary"', 'stage="handoff"'):
        idx = src.find(stage)
        assert idx != -1, f"{stage} record is not emitted"
        assert "fix_attempts=0" in src[idx : idx + 700], f"{stage} must pass fix_attempts=0"


def test_handoff_is_fail_open_and_never_reaches_a_validator():
    src = _src()
    idx = src.find("async def _run_handoff")
    assert idx != -1
    body = src[idx : idx + 2600]
    assert "return fallback" in body
    # The handoff is passed to TaskResult (consumed by LATER tasks) and to
    # nothing else -- never into a review or QA call.
    assert "_run_review(" not in body
    assert "_run_adversary(" not in body


# --- review-defect regressions -------------------------------------------------


def test_adversary_receives_the_same_test_info_as_the_primary():
    """Identical information is what makes disagreement interpretable as model
    variance, not information asymmetry (spec 3.1). The adversary must see the
    full QAReport the primary sees -- not an issues-only digest that is empty
    on the approving path and biases it toward rejection."""
    src = STAGE_SRC.read_text(encoding="utf-8")
    adv = src[src.find("async def run_adversary") : src.find("async def run_deep_review")]
    assert "qa_raw.model_dump_json()" in src
    assert "Test output:" not in adv


def test_non_blocking_adversary_rejection_does_not_abandon_the_task():
    """A reject whose findings are all medium/low has no actionable instruction;
    it must be treated as agreement, not fall through to ``if not issues: break``
    which silently abandons a task that passed its gate. blocking_findings is
    actionable; the boolean alone is not -- same rule as the primary."""
    src = _src()
    idx = src.find("await _run_adversary")
    if idx == -1:
        idx = src.find("await self._run_adversary")
    assert idx != -1
    gate = src[idx : idx + 800]
    assert "not adversary.blocking_findings" in gate


def test_review_record_names_the_model_that_actually_ran():
    """The reviewer agent is built at import on the registry model and always
    RUNS that model (the call site's model arg is pricing-only); cfg.roles
    ['reviewer'] is dead config by design (registry-drives-every-role spec).
    So the record must use STAGE_MODELS.get('review'), never
    resolve_role_model -- which would credit an inert arm override."""
    src = _src()
    assert 'resolve_role_model(cfg, "review")' not in src


def test_adversary_never_runs_without_a_primary_reviewer():
    """The adversary is a SECOND opinion; it presupposes a first. When review
    is disabled (review is None) it must not run -- the primary reviewer is the
    sole designated blocking lens, which is the justification for this lens
    being fail-open."""
    src = _src()
    pred = src.find("if task_passed and review_ok:")
    call = src.find("await _run_adversary")
    if call == -1:
        call = src.find("await self._run_adversary")
    assert pred != -1 and call > pred
    assert "review is not None" in src[pred:call], (
        "the adversary must be guarded by primary-reviewer presence"
    )
