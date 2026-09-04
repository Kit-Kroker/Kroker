from __future__ import annotations

import asyncio
import sys

import pytest

from sdlc.stages.qa.activities import LintInput, QAInput, run_lint, run_test_suite
from tests.conftest import _wait_for_pidfile_async, _wait_until_dead


def _sleep_cmd(seconds: float) -> str:
    # cross-platform: a short-lived Python process sleeping past the bound
    return f'"{sys.executable}" -c "import time; time.sleep({seconds})"'


# run_test_suite spawns via create_subprocess_shell, so this cmd string is
# parsed by a real OS shell (cmd.exe on Windows, /bin/sh on POSIX) before
# python ever sees it. Passing the grandchild-spawning logic as an inline
# python -c string through THAT shell layer means two quoting dialects
# apply in sequence -- not worth it. Write real .py files to tmp_path
# instead and pass arguments via argv (subprocess.Popen's list form quotes
# correctly on both platforms on its own); the shell command line then
# only needs to double-quote plain file paths, which both cmd.exe and sh
# parse identically.
_GRANDCHILD_SCRIPT = """\
import os, sys, time
with open(sys.argv[1], "w") as f:
    f.write(str(os.getpid()))
time.sleep(float(sys.argv[2]))
"""

_PARENT_SCRIPT = """\
import subprocess, sys, time
subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2], sys.argv[3]])
time.sleep(float(sys.argv[3]))
"""


def _write_script(tmp_path, name: str, content: str) -> str:
    p = tmp_path / name
    p.write_text(content)
    return str(p)


def _grandchild_sleep_cmd(tmp_path, pidfile: str, seconds: float) -> str:
    grandchild_script = _write_script(tmp_path, "grandchild.py", _GRANDCHILD_SCRIPT)
    parent_script = _write_script(tmp_path, "parent.py", _PARENT_SCRIPT)
    return f'"{sys.executable}" "{parent_script}" "{grandchild_script}" "{pidfile}" "{seconds}"'


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


def test_run_test_suite_timeout_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")

    async def _go():
        task = asyncio.ensure_future(
            run_test_suite(
                QAInput(
                    worktree=str(tmp_path),
                    test_cmd=_grandchild_sleep_cmd(tmp_path, pidfile, 60),
                    timeout_s=2,
                )
            )
        )
        grandchild_pid = await _wait_for_pidfile_async(pidfile)
        report = await task
        return grandchild_pid, report

    grandchild_pid, report = asyncio.run(_go())
    assert report.tests_passed is False
    _wait_until_dead(grandchild_pid)


def test_run_test_suite_cancelled_propagates_and_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")

    async def _go():
        task = asyncio.ensure_future(
            run_test_suite(
                QAInput(
                    worktree=str(tmp_path),
                    test_cmd=_grandchild_sleep_cmd(tmp_path, pidfile, 60),
                    timeout_s=30,
                )
            )
        )
        grandchild_pid = await _wait_for_pidfile_async(pidfile)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return grandchild_pid

    grandchild_pid = asyncio.run(_go())
    _wait_until_dead(grandchild_pid)
