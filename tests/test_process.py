"""Unit tests for kill_process_tree — the shared cleanup helper for C6
(kill the whole process tree on timeout/cancellation)."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from sdlc.process import kill_process_tree
from tests.conftest import _pid_alive, _wait_for_pidfile, _wait_until_dead


def _spawn_grandchild_script(pidfile: str) -> str:
    """A python -c script: spawns a grandchild that writes ITS OWN pid to
    `pidfile` and sleeps, then the parent (this script) also sleeps. Used
    to prove kill_process_tree kills descendants, not just the direct
    child. The grandchild writing its own pidfile (rather than the parent
    writing it) means the test can wait for the grandchild to actually
    exist before acting -- no timing luck."""
    pidfile_str = pidfile.replace("\\", "/")
    return (
        "import subprocess, sys, time\n"
        "gc = subprocess.Popen([sys.executable, '-c', "
        f'\'import os,time; open("{pidfile_str}","w").\''
        "'write(str(os.getpid())); time.sleep(60)'])\n"
        "time.sleep(60)\n"
    )


@pytest.mark.asyncio
async def test_kill_process_tree_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _spawn_grandchild_script(pidfile),
        start_new_session=True,
    )
    grandchild_pid = _wait_for_pidfile(pidfile)
    assert _pid_alive(grandchild_pid)

    await kill_process_tree(proc)

    _wait_until_dead(grandchild_pid)


@pytest.mark.asyncio
async def test_kill_process_tree_on_already_exited_process_is_quiet(tmp_path):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "pass",
        start_new_session=True,
    )
    await proc.wait()
    await kill_process_tree(proc)  # must not raise


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX process-group guard only")
@pytest.mark.asyncio
async def test_kill_process_tree_does_not_killpg_when_sharing_our_group(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "killpg", lambda *a: calls.append(("killpg", a)))
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
    )  # no start_new_session -- shares our process group on purpose

    await kill_process_tree(proc)

    assert calls == []  # the guard must have skipped killpg entirely
    _wait_until_dead(proc.pid)
