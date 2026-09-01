import asyncio
import sys

from sdlc.activities import LintInput, QAInput, run_lint, run_test_suite


def _sleep_cmd(seconds: float) -> str:
    # cross-platform: a short-lived Python process sleeping past the bound
    return f'"{sys.executable}" -c "import time; time.sleep({seconds})"'


def test_run_test_suite_times_out_on_hung_command(tmp_path):
    report = asyncio.run(
        run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_sleep_cmd(5), timeout_s=1))
    )
    assert report.tests_passed is False
    assert "timed out" in report.issues[0]


def test_run_test_suite_completes_normally_within_timeout(tmp_path):
    report = asyncio.run(
        run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_sleep_cmd(0), timeout_s=30))
    )
    assert report.tests_passed is True


def test_run_lint_times_out_on_hung_command(tmp_path):
    clean, detail = asyncio.run(
        run_lint(LintInput(worktree=str(tmp_path), lint_cmd=_sleep_cmd(5), timeout_s=1))
    )
    assert clean is False
    assert "timed out" in detail
