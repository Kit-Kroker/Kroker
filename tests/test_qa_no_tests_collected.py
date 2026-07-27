"""A task whose own scope doesn't add tests yet (e.g. an early module task
in a task-per-commit greenfield build, before the dedicated test-writing
tasks land) must not have its QA gate fail just because pytest collected
zero tests -- that's pytest exit code 5, distinct from exit code 1 (tests
ran and some failed), and scoring them identically makes such a task's gate
unpassable no matter what the agent writes (see bench-cat-cafe-monitoring
run 1785148730: T01-T07 all failed this way before T09 wrote the first
test)."""
import asyncio
import sys

from sdlc.activities import QAInput, run_test_suite


def _pytest_cmd(extra: str = "") -> str:
    return f'"{sys.executable}" -m pytest -q {extra}'.strip()


def test_no_tests_collected_is_a_vacuous_pass_not_a_failure(tmp_path):
    report = asyncio.run(run_test_suite(QAInput(
        worktree=str(tmp_path), test_cmd=_pytest_cmd())))
    assert report.tests_passed is True
    assert report.issues == []
    assert report.failing_tests == []


def test_a_real_test_failure_still_fails(tmp_path):
    (tmp_path / "test_x.py").write_text(
        "def test_x():\n    assert False\n", encoding="utf-8")
    report = asyncio.run(run_test_suite(QAInput(
        worktree=str(tmp_path), test_cmd=_pytest_cmd())))
    assert report.tests_passed is False
    assert report.issues


def test_passing_tests_still_pass(tmp_path):
    (tmp_path / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8")
    report = asyncio.run(run_test_suite(QAInput(
        worktree=str(tmp_path), test_cmd=_pytest_cmd())))
    assert report.tests_passed is True
    assert report.issues == []
