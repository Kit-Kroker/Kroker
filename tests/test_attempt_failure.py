"""026 T019 (FR-021, data-model rows 16-18): every failed task attempt says why.

`attempt_failure(qa_raw, qa, drift, review_ok, review, report_only=())` is
pure. It returns None on a derived pass, and otherwise an AttemptFailure:

- checks: an ORDERED subset of ("tests", "qa", "drift", "review", "lint",
  "no_feedback"). The order is fixed, not the order the checks were hit.
  "no_feedback" comes LAST, and only when the failed attempt's summary text
  is empty, so the record never claims a failure with nothing behind it.
- summary: the text the dev was shown. It is the `_fix_loop_issues` text,
  joined to the drift note with the step's "\\n- " separator, cut to 500 chars.

Imports of the new names happen inside each test, so each test fails on its
own with the ImportError, instead of the whole module failing to collect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import HarnessKind
from sdlc.measurement import CollectionState
from sdlc.stages.code.freeze import _drift_note
from sdlc.stages.qa.models import QAReport
from sdlc.stages.qa.step import _fix_loop_issues
from sdlc.toolchain.lint_scope import LintFinding, ScopedLintReport
from sdlc.vcs import DriftReport

T = datetime(2026, 11, 18, 10, tzinfo=UTC)
ORDER = ("tests", "qa", "drift", "review", "lint", "no_feedback")


def _attempt_failure():
    from sdlc.stages.code.attempt_failure import attempt_failure

    return attempt_failure


def _lint(*paths: str) -> ScopedLintReport:
    return ScopedLintReport(
        state=CollectionState.MEASURED,
        introduced=[LintFinding(rule="I001", path=p, line=f"import {p}") for p in paths],
    )


def _review(*blocking: tuple[str, str, str]):
    """A reviewer output stand-in: `blocking` is (severity, assertion, detail)."""
    return SimpleNamespace(
        blocking_findings=[
            SimpleNamespace(severity=s, assertion=a, detail=d) for s, a, d in blocking
        ]
    )


CLEAN_QA = SimpleNamespace(issues=[], failing_tests=[])
CLEAN_RAW = QAReport(tests_passed=True, failing_tests=[], issues=[])
CLEAN_DRIFT = DriftReport()


def _expected_summary(qa, qa_raw, review, drift, limit=500) -> str:
    """The step's join: the assembled issues, then the drift note, "\\n- "
    between them, empties dropped, then truncated. Built from the real helpers
    so the test pins the composition, not a copy of their text."""
    base = _fix_loop_issues(qa, qa_raw, review)
    note = _drift_note(drift) if drift.found else ""
    return "\n- ".join(x for x in (base, note) if x)[:limit]


# --- None on a pass -------------------------------------------------------------


def test_a_derived_pass_returns_none():
    af = _attempt_failure()
    assert af(CLEAN_RAW, CLEAN_QA, CLEAN_DRIFT, True, None) is None


def test_a_pass_with_a_lint_finding_in_report_only_paths_returns_none():
    af = _attempt_failure()
    raw = CLEAN_RAW.model_copy(update={"lint": _lint("tests/test_x.py")})
    assert af(raw, CLEAN_QA, CLEAN_DRIFT, True, None, ("tests/**",)) is None


# --- single checks ------------------------------------------------------------


def test_a_rejected_review_alone_is_checked_as_review_with_its_findings():
    af = _attempt_failure()
    review = _review(("high", "ac1", "not done right"))
    failure = af(CLEAN_RAW, CLEAN_QA, CLEAN_DRIFT, False, review)
    assert failure is not None
    assert failure.checks == ["review"]
    assert failure.summary == _expected_summary(CLEAN_QA, CLEAN_RAW, review, CLEAN_DRIFT)
    assert "not done right" in failure.summary


def test_drift_alone_is_checked_as_drift_and_carries_the_drift_note():
    af = _attempt_failure()
    drift = DriftReport(fence_paths=["tests/test_a.py"])
    failure = af(CLEAN_RAW, CLEAN_QA, drift, True, None)
    assert failure is not None
    assert failure.checks == ["drift"]
    assert _drift_note(drift) in failure.summary
    assert failure.summary == _expected_summary(CLEAN_QA, CLEAN_RAW, None, drift)


def test_a_lint_finding_outside_report_only_is_checked_as_lint():
    af = _attempt_failure()
    raw = CLEAN_RAW.model_copy(update={"lint": _lint("app.py")})
    failure = af(raw, CLEAN_QA, CLEAN_DRIFT, True, None, ())
    assert failure is not None
    assert failure.checks == ["lint"]
    assert "I001 app.py:" in failure.summary


def test_qa_issues_with_passing_tests_are_checked_as_qa():
    af = _attempt_failure()
    qa = SimpleNamespace(issues=["the contract says X, the diff does Y"], failing_tests=[])
    failure = af(CLEAN_RAW, qa, CLEAN_DRIFT, True, None)
    assert failure is not None
    assert failure.checks == ["qa"]
    assert "the contract says X" in failure.summary


def test_failing_tests_are_checked_as_tests_with_the_test_output():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=["test_x"], issues=["boom"])
    failure = af(raw, CLEAN_QA, CLEAN_DRIFT, True, None)
    assert failure is not None
    assert failure.checks == ["tests"]
    assert "boom" in failure.summary


# --- ordering -----------------------------------------------------------------


def test_several_checks_are_listed_in_the_fixed_order_not_the_hit_order():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=[], issues=[], lint=_lint("app.py"))
    qa = SimpleNamespace(issues=["qa says no"], failing_tests=[])
    drift = DriftReport(fence_paths=["tests/test_a.py"])
    review = _review(("high", "ac1", "nope"))
    failure = af(raw, qa, drift, False, review)
    assert failure is not None
    assert failure.checks == ["tests", "qa", "drift", "review", "lint"]


def test_tests_qa_drift_lint_without_review_keep_the_fixed_order():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=[], issues=["t"], lint=_lint("app.py"))
    qa = SimpleNamespace(issues=["q"], failing_tests=[])
    drift = DriftReport(fence_paths=["tests/test_a.py"])
    failure = af(raw, qa, drift, True, None)
    assert failure.checks == ["tests", "qa", "drift", "lint"]


def test_checks_are_always_an_ordered_subset_of_the_six():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=[], issues=[], lint=_lint("app.py"))
    qa = SimpleNamespace(issues=["q"], failing_tests=[])
    failure = af(raw, qa, DriftReport(fence_paths=["x"]), False, _review(("h", "a", "d")))
    assert failure.checks == [c for c in ORDER if c in failure.checks]
    assert set(failure.checks) <= set(ORDER)


# --- no_feedback --------------------------------------------------------------


def test_failing_tests_with_nothing_to_say_are_no_feedback_last():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=[], issues=[])
    failure = af(raw, CLEAN_QA, CLEAN_DRIFT, True, None)
    assert failure is not None
    assert failure.checks == ["tests", "no_feedback"]
    assert failure.summary == ""


def test_a_rejected_review_with_no_findings_is_review_then_no_feedback():
    af = _attempt_failure()
    failure = af(CLEAN_RAW, CLEAN_QA, CLEAN_DRIFT, False, _review())
    assert failure is not None
    assert failure.checks == ["review", "no_feedback"]
    assert failure.summary == ""


def test_no_feedback_never_joins_when_the_summary_has_text():
    af = _attempt_failure()
    failure = af(CLEAN_RAW, CLEAN_QA, DriftReport(fence_paths=["tests/a.py"]), True, None)
    assert "no_feedback" not in failure.checks


# --- summary: the step's text, bounded ----------------------------------------


def test_summary_is_the_fix_loop_text_joined_to_the_drift_note():
    af = _attempt_failure()
    review = _review(("high", "ac1", "not done right"))
    drift = DriftReport(fence_paths=["tests/test_a.py"])
    failure = af(CLEAN_RAW, CLEAN_QA, drift, False, review)
    assert failure.summary == _expected_summary(CLEAN_QA, CLEAN_RAW, review, drift)
    assert "not done right" in failure.summary
    assert _drift_note(drift) in failure.summary


def test_summary_is_cut_to_500_characters_and_is_the_prefix_of_the_full_text():
    af = _attempt_failure()
    qa = SimpleNamespace(issues=["x" * 200] * 5, failing_tests=[])
    full = _expected_summary(qa, CLEAN_RAW, None, CLEAN_DRIFT, limit=10_000)
    assert len(full) > 500
    failure = af(CLEAN_RAW, qa, CLEAN_DRIFT, True, None)
    assert len(failure.summary) == 500
    assert failure.summary == full[:500]


# --- record fields: legacy loads, new carries ---------------------------------


def _record(**overrides) -> dict:
    """The smallest valid code-stage BenchmarkRecord, as its JSON dict. Built
    from the model (not hand-written JSON) so the shape tracks the schema."""
    rec = BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id="c1",
        scope=BenchmarkScope.TASK_ATTEMPT,
        stage="code",
        task_id="t1",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=T, ended_at=T + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL,
    )
    d = rec.model_dump(mode="json")
    d.pop("failure", None)  # a pre-026 record has no such key at all
    d.update(overrides)
    return d


def test_a_legacy_record_without_failure_loads_with_none():
    d = _record()
    assert "failure" not in d
    loaded = BenchmarkRecord.model_validate(d)
    assert loaded.failure is None


def test_a_record_with_failure_round_trips_the_attempt_failure():
    from sdlc.benchmarks.models import AttemptFailure

    d = _record(failure={"checks": ["tests", "no_feedback"], "summary": ""})
    loaded = BenchmarkRecord.model_validate(d)
    assert loaded.failure == AttemptFailure(checks=["tests", "no_feedback"], summary="")
    assert loaded.error is None  # the reason rides `failure`, never `error`
    again = BenchmarkRecord.model_validate_json(loaded.model_dump_json())
    assert again.failure == loaded.failure


@pytest.mark.parametrize("checks", [["tests", "qa", "drift", "review", "lint", "no_feedback"]])
def test_the_full_check_vocabulary_is_accepted(checks):
    from sdlc.benchmarks.models import AttemptFailure

    assert AttemptFailure(checks=checks, summary="s").checks == checks


# --- chaos / edge cases (026 T019, chaos QA) --------------------------------
#
# Drift channels: an UNAVAILABLE backstop (available=False) is not a finding.
# The step's pass rule already ignores it (`not drift.found`), so the record
# must not carry a "drift" check or the TEST-FREEZE note for it. The note's
# own wording ("Test drift was NOT checked") therefore never reaches a failed
# attempt's record. That gap is flagged in the report, not pinned away here.


def _unavailable() -> DriftReport:
    return DriftReport(available=False, unavailable_reason="ls-files failed")


def test_edge_summary_of_exactly_500_chars_is_kept_whole():
    af = _attempt_failure()
    text = "x" * 500
    qa = SimpleNamespace(issues=[text], failing_tests=[])
    failure = af(CLEAN_RAW, qa, CLEAN_DRIFT, True, None)
    assert failure.summary == text
    assert len(failure.summary) == 500


def test_edge_summary_of_501_chars_is_the_plain_500_prefix_with_no_marker():
    """[:500] semantics: the 501st character is dropped, and no ellipsis or
    marker is appended (the dev's text is cut, not decorated)."""
    af = _attempt_failure()
    text = "a" * 499 + "b" + "c"  # 501 chars; the cut lands on the 'b'
    qa = SimpleNamespace(issues=[text], failing_tests=[])
    failure = af(CLEAN_RAW, qa, CLEAN_DRIFT, True, None)
    assert len(failure.summary) == 500
    assert failure.summary == "a" * 499 + "b"
    assert "…" not in failure.summary and "..." not in failure.summary


def test_edge_unavailable_drift_is_no_check_and_no_note_on_a_failed_attempt():
    af = _attempt_failure()
    raw = QAReport(tests_passed=False, failing_tests=[], issues=["boom"])
    failure = af(raw, CLEAN_QA, _unavailable(), True, None)
    assert failure is not None
    assert failure.checks == ["tests"]
    assert "drift" not in failure.checks
    assert "BACKSTOP UNAVAILABLE" not in failure.summary
    assert "NOT checked" not in failure.summary


def test_edge_unavailable_drift_alone_leaves_a_clean_attempt_passing():
    """available=False is not found=True: the same rule as the step's
    `task_passed`, so a clean attempt with the backstop down still passes."""
    af = _attempt_failure()
    assert af(CLEAN_RAW, CLEAN_QA, _unavailable(), True, None) is None


def test_edge_an_approved_review_ignores_its_blocking_findings():
    """review_ok is the step's verdict. An approved review never fails the
    task through this function, even if its object lists findings."""
    af = _attempt_failure()
    approved_with_findings = _review(("high", "ac1", "a complaint the reviewer still approved"))
    assert af(CLEAN_RAW, CLEAN_QA, CLEAN_DRIFT, True, approved_with_findings) is None


def test_edge_a_rejected_review_with_no_object_is_review_then_no_feedback():
    af = _attempt_failure()
    failure = af(CLEAN_RAW, CLEAN_QA, CLEAN_DRIFT, False, None)
    assert failure is not None
    assert failure.checks == ["review", "no_feedback"]
    assert failure.summary == ""


def test_edge_fenced_lint_finding_passes_through_attempt_failure():
    """The fence is applied in classification, not only in _lint_ok: the same
    MEASURED finding passes when it sits under report_only, and fails as a
    lint check when it does not."""
    af = _attempt_failure()
    raw = CLEAN_RAW.model_copy(update={"lint": _lint("tests/test_x.py")})
    assert af(raw, CLEAN_QA, CLEAN_DRIFT, True, None, ("tests/**",)) is None

    failure = af(raw, CLEAN_QA, CLEAN_DRIFT, True, None, ())
    assert failure is not None
    assert failure.checks == ["lint"]
