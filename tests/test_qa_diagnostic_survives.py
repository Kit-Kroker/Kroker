"""The retry prompt must carry the traceback, and must say when the suite
stopped early.

Found by the P2 demonstration runs (2026-08-19). pytest orders its output
FAILURES (tracebacks) -> warnings summary -> short test summary info, and both
truncation points keep the TAIL: `run_test_suite` stores `out[-2000:]` and
`_fix_loop_issues` then takes `[-_TEST_OUTPUT_MAX:]` of that. On a repository
with heavy warning output the warnings survive and the tracebacks are thrown
away, so every retry prompt carried the failing test's NAME and nothing else.

Four consecutive tasks responded to that by attacking the named test file --
editing it, rewriting unrelated production code, then adding an
OSError-swallowing retry helper. Given no traceback, "make the named test stop
failing" is the only instruction the loop actually communicates.

`_fix_loop_issues`' own docstring records an earlier instance of this species
(bench-todo-api-greenfield-1785444047: 8 of 12 attempts burned while the real
ModuleNotFoundError was never shown), fixed by carrying the deterministic
output at all -- but the truncation-by-tail remained.

Second half: when pytest stops early (-x / --maxfail), `tests_passed=False` is
indistinguishable from a suite that ran to completion and failed. It is not the
same fact. Tests ordered after the stopping point did not run, and a task whose
own tests sort after an unrelated failure gets a verdict on evidence that was
never collected. This is the `measured: bool` discipline CoverageReport already
has (E-30), applied to QAReport.
"""

from __future__ import annotations

import asyncio
import sys

from sdlc.activities import QAInput, run_test_suite

# Appears in the traceback's source listing but NOT in pytest's one-line
# short-summary entry, so it discriminates "we kept the traceback" from
# "we kept the summary".
MARKER = "traceback_only_marker"


def _pytest_cmd(extra: str = "") -> str:
    return f'"{sys.executable}" -m pytest -q {extra}'.strip()


def _noisy_warnings(count: int = 30) -> str:
    """A module whose warnings summary is comfortably larger than the 2000
    character tail, emitted from `count` distinct locations so pytest cannot
    collapse them into one entry."""
    pad = "W" * 120
    return "import warnings\n" + "".join(
        f"def test_warn_{i}():\n    warnings.warn('{pad} {i}', UserWarning)\n" for i in range(count)
    )


def _failing_test() -> str:
    return f"def test_the_real_failure():\n    {MARKER} = 41\n    assert {MARKER} + 1 == 43\n"


def test_traceback_survives_a_large_warnings_summary(tmp_path):
    """The whole point: the diagnostic must not be crowded out by warnings."""
    (tmp_path / "test_aaa_noisy.py").write_text(_noisy_warnings(), encoding="utf-8")
    (tmp_path / "test_zzz_fail.py").write_text(_failing_test(), encoding="utf-8")

    report = asyncio.run(run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_pytest_cmd())))

    assert report.tests_passed is False
    blob = "\n".join(report.issues)
    assert MARKER in blob, (
        "the traceback was truncated away by the warnings summary; the retry "
        "prompt would carry the failing test's name and no diagnostic"
    )


def test_stopped_early_is_recorded_when_the_suite_aborts(tmp_path):
    """-x means later tests did not run. That is not the same fact as
    'they ran and failed', and the report has to be able to say so."""
    (tmp_path / "test_aaa_fail.py").write_text(_failing_test(), encoding="utf-8")
    (tmp_path / "test_zzz_ok.py").write_text(
        "def test_never_reached():\n    assert True\n", encoding="utf-8"
    )

    report = asyncio.run(
        run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_pytest_cmd("-x")))
    )

    assert report.tests_passed is False
    assert report.stopped_early is True, (
        "a suite aborted by -x left later tests unrun; reporting that "
        "identically to a completed red run is a gap reported as a verdict"
    )


def test_a_completed_failing_run_is_not_marked_stopped_early(tmp_path):
    """The discriminator has to discriminate."""
    (tmp_path / "test_x.py").write_text(_failing_test(), encoding="utf-8")

    report = asyncio.run(run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_pytest_cmd())))

    assert report.tests_passed is False
    assert report.stopped_early is False


def test_a_passing_run_is_not_marked_stopped_early(tmp_path):
    (tmp_path / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")

    report = asyncio.run(run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_pytest_cmd())))

    assert report.tests_passed is True
    assert report.stopped_early is False


def test_non_pytest_output_still_falls_back_to_the_tail(tmp_path):
    """FR-803: a contract may name any test command. A non-pytest command has
    no FAILURES section, and must keep today's behaviour rather than losing
    its output to a parser that found nothing."""
    script = (
        "import sys\nsys.stdout.write('custom runner: BUILD BROKEN at step 7\\n')\nsys.exit(1)\n"
    )
    (tmp_path / "runner.py").write_text(script, encoding="utf-8")

    report = asyncio.run(
        run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=f'"{sys.executable}" runner.py'))
    )

    assert report.tests_passed is False
    assert "BUILD BROKEN at step 7" in "\n".join(report.issues)


# --- the retry prompt itself -------------------------------------------------

from sdlc.models import QAReport  # noqa: E402
from sdlc.workflows.feature import _fix_loop_issues  # noqa: E402


def test_retry_prompt_says_the_suite_stopped_early():
    """The agent must be told the run was truncated. Otherwise it reads
    'these tests failed' as the whole story and starts fixing the one test it
    was shown -- which is exactly what four consecutive tasks did."""
    qa = QAReport(tests_passed=False, issues=[])
    qa_raw = QAReport(
        tests_passed=False,
        failing_tests=["tests/test_a.py::test_x"],
        issues=["E   assert 41 + 1 == 43"],
        stopped_early=True,
    )

    text = _fix_loop_issues(qa, qa_raw, None)

    assert "did not run" in text.lower(), (
        "a truncated suite must say so in the retry prompt; tests after the "
        "stopping point were never evidence"
    )


def test_retry_prompt_does_not_claim_truncation_on_a_complete_run():
    qa = QAReport(tests_passed=False, issues=[])
    qa_raw = QAReport(
        tests_passed=False,
        failing_tests=["tests/test_a.py::test_x"],
        issues=["E   assert 41 + 1 == 43"],
        stopped_early=False,
    )

    text = _fix_loop_issues(qa, qa_raw, None)

    assert "did not run" not in text.lower()


def test_traceback_reaches_the_retry_prompt_end_to_end(tmp_path):
    """The property that actually matters. There are TWO tail truncations
    between pytest and the agent -- the activity's and _fix_loop_issues' own
    -- so each half passing separately does not prove the prompt carries a
    diagnostic."""
    (tmp_path / "test_aaa_noisy.py").write_text(_noisy_warnings(), encoding="utf-8")
    (tmp_path / "test_zzz_fail.py").write_text(_failing_test(), encoding="utf-8")
    qa_raw = asyncio.run(run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_pytest_cmd())))

    text = _fix_loop_issues(QAReport(tests_passed=False, issues=[]), qa_raw, None)

    assert MARKER in text, (
        "the traceback survived the activity but not the prompt assembly; "
        "the agent is still being asked to fix something it cannot see"
    )
