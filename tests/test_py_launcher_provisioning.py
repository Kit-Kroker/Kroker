"""A contract's test/lint command may pin an interpreter via the Windows
`py -X.Y` launcher (mirroring an AGENTS.md-mandated stack). If that exact
version was never installed on this host, `py -X.Y` fails immediately with
a launcher error -- before the command's own install step ever runs -- so
a fully correct implementation reads back as a QA failure indistinguishable
from a real test failure. `_ensure_py_launcher_versions` closes that gap by
auto-provisioning any missing version first."""

import asyncio
import sys

import sdlc.stages.qa.activities as activities
from sdlc.stages.qa.activities import (
    _PY_LAUNCHER_VERSION_RE,
    LintInput,
    QAInput,
    _ensure_py_launcher_versions,
    run_lint,
    run_test_suite,
)


def _py_cmd(code: str) -> str:
    # cross-platform + avoids relying on a bare `python`/`py` on PATH
    return f'"{sys.executable}" -c "{code}"'


def test_regex_extracts_single_version():
    assert _PY_LAUNCHER_VERSION_RE.findall(
        "py -3.11 -m pip install -e .[dev] && py -3.11 -m pytest"
    ) == ["3.11", "3.11"]


def test_regex_extracts_multiple_distinct_versions():
    assert set(_PY_LAUNCHER_VERSION_RE.findall("py -3.11 -m pytest && py -3.9 -m mypy .")) == {
        "3.11",
        "3.9",
    }


def test_regex_ignores_commands_without_launcher_pin():
    assert _PY_LAUNCHER_VERSION_RE.findall("pytest -q --maxfail=25") == []


def test_noop_on_non_windows(monkeypatch):
    monkeypatch.setattr(activities.sys, "platform", "linux")
    calls = []

    async def fake_bounded_shell(cmd, cwd, timeout_s):
        calls.append(cmd)
        return 0, ""

    monkeypatch.setattr(activities, "_bounded_shell", fake_bounded_shell)

    note = asyncio.run(_ensure_py_launcher_versions("py -3.11 -m pytest", "."))

    assert note is None
    assert calls == []  # never even probed -- not this platform's launcher


def test_skips_install_when_version_already_available(monkeypatch):
    monkeypatch.setattr(activities.sys, "platform", "win32")
    calls = []

    async def fake_bounded_shell(cmd, cwd, timeout_s):
        calls.append(cmd)
        return 0, "Python 3.11.9"  # `py -3.11 --version` succeeds

    monkeypatch.setattr(activities, "_bounded_shell", fake_bounded_shell)

    note = asyncio.run(_ensure_py_launcher_versions("py -3.11 -m pytest", "."))

    assert note is None
    assert calls == ["py -3.11 --version"]  # probed once, never installed


def test_provisions_missing_version(monkeypatch):
    monkeypatch.setattr(activities.sys, "platform", "win32")
    calls = []

    async def fake_bounded_shell(cmd, cwd, timeout_s):
        calls.append(cmd)
        if "--version" in cmd:
            return 1, "[ERROR] No runtime installed that matches 3.11"
        return 0, "installed"

    monkeypatch.setattr(activities, "_bounded_shell", fake_bounded_shell)

    note = asyncio.run(_ensure_py_launcher_versions("py -3.11 -m pytest", "."))

    assert calls == ["py -3.11 --version", "py install 3.11"]
    assert note is not None
    assert "auto-provisioned" in note and "succeeded" in note


def test_reports_failed_provisioning_without_raising(monkeypatch):
    monkeypatch.setattr(activities.sys, "platform", "win32")

    async def fake_bounded_shell(cmd, cwd, timeout_s):
        return 1, "boom"

    monkeypatch.setattr(activities, "_bounded_shell", fake_bounded_shell)

    note = asyncio.run(_ensure_py_launcher_versions("py -3.11 -m pytest", "."))

    assert note is not None and "failed" in note


def test_run_test_suite_does_not_pollute_issues_on_a_passing_run(monkeypatch, tmp_path):
    """A provisioning note must never land in QAReport.issues on success --
    `quality_score` gates on `qa.tests_passed and not qa.issues`, so a
    non-empty issues list would silently flip a passing task to a fail."""

    async def fake_ensure(cmd, cwd):
        return "py -3.11 was not installed; auto-provisioned"

    monkeypatch.setattr(activities, "_ensure_py_launcher_versions", fake_ensure)

    report = asyncio.run(
        run_test_suite(QAInput(worktree=str(tmp_path), test_cmd=_py_cmd("pass"), timeout_s=30))
    )

    assert report.tests_passed is True
    assert report.issues == []


def test_run_test_suite_surfaces_provisioning_note_on_a_failing_run(monkeypatch, tmp_path):
    async def fake_ensure(cmd, cwd):
        return "py -3.11 was not installed; auto-provisioned"

    monkeypatch.setattr(activities, "_ensure_py_launcher_versions", fake_ensure)

    report = asyncio.run(
        run_test_suite(
            QAInput(
                worktree=str(tmp_path), test_cmd=_py_cmd("import sys; sys.exit(1)"), timeout_s=30
            )
        )
    )

    assert report.tests_passed is False
    assert report.issues[0] == "py -3.11 was not installed; auto-provisioned"


def test_run_lint_surfaces_provisioning_note_only_on_failure(monkeypatch, tmp_path):
    async def fake_ensure(cmd, cwd):
        return "py -3.11 was not installed; auto-provisioned"

    monkeypatch.setattr(activities, "_ensure_py_launcher_versions", fake_ensure)

    clean, detail = asyncio.run(
        run_lint(LintInput(worktree=str(tmp_path), lint_cmd=_py_cmd("pass"), timeout_s=30))
    )
    assert clean is True
    assert "auto-provisioned" not in detail

    clean, detail = asyncio.run(
        run_lint(
            LintInput(
                worktree=str(tmp_path), lint_cmd=_py_cmd("import sys; sys.exit(1)"), timeout_s=30
            )
        )
    )
    assert clean is False
    assert "auto-provisioned" in detail
