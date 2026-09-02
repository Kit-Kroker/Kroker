"""Shared subprocess-tree cleanup for C6: a timed-out or cancelled child
must not leave its own children behind.

Callers spawn with start_new_session=True (POSIX: real setsid(); Windows:
accepted and silently ignored -- CPython's Windows _execute_child receives
it as `unused_start_new_session`, verified directly against the installed
interpreter, not assumed). kill_process_tree() below is the only place
that knows how to reach the resulting group/tree.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys

_log = logging.getLogger(__name__)

_REAP_TIMEOUT_S = 5.0


async def kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """Kill `proc` and every process it (transitively) started. Tolerates
    a process that has already exited. Never raises -- always called from
    a cleanup path (TimeoutError/CancelledError handler) that must not
    have its original exception masked by a cleanup failure."""
    try:
        if sys.platform.startswith("win"):
            await _kill_windows(proc)
        else:
            await _kill_posix(proc)
    except Exception:
        _log.warning("kill_process_tree: cleanup failed for pid=%s", proc.pid, exc_info=True)

    try:
        await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)
    except TimeoutError:
        _log.warning(
            "kill_process_tree: pid=%s did not exit within %.0fs of kill",
            proc.pid,
            _REAP_TIMEOUT_S,
        )
    except Exception:
        pass


async def _kill_posix(proc: asyncio.subprocess.Process) -> None:
    if sys.platform == "win32":
        return
    pid = proc.pid
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return  # fully reaped already -- nothing left to reach

    if pgid in (os.getpgrp(), os.getpid()):
        # Spawned without start_new_session=True: shares our process
        # group. os.killpg here would SIGKILL the calling worker itself.
        # Fall back to the direct child only -- fail-to-leak, not
        # fail-to-kill-the-worker.
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
        return

    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGKILL)


async def _kill_windows(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return  # dead root -- taskkill /T can't walk a tree from it

    # taskkill.exe is a real executable in System32 (always on PATH), not
    # a .cmd/.bat shim -- CreateProcess resolves it via its own implicit
    # search, same as any other real .exe (see adapters.py's harness-spawn
    # comment on why .cmd shims specifically need shutil.which).
    tk = await asyncio.create_subprocess_exec(
        "taskkill",
        "/F",
        "/T",
        "/PID",
        str(proc.pid),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await tk.wait()  # best-effort: every exit code is tolerated (128 =
    # "not found" is the common already-exited race, not a failure)
