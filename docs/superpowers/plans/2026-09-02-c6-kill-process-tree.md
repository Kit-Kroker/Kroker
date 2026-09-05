# C6: Kill The Whole Process Tree On Timeout/Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a harness run or a bounded shell command times out or is cancelled, kill every process it started — not just the direct child — so orphaned grandchildren stop burning tokens, holding worktree CWDs open, and writing into trees whose diff has already been measured.

**Architecture:** One new shared helper, `kill_process_tree()`, that POSIX-kills a process group (`os.killpg`) or Windows-kills a process tree (`taskkill /F /T`) given an `asyncio.subprocess.Process`. Five existing call sites each get one added spawn kwarg (`start_new_session=True`) and one added exception handler (`except asyncio.CancelledError`) alongside their existing `except TimeoutError`, both now routing through the shared helper instead of a bare `proc.kill()`.

**Tech Stack:** Python 3.11+ `asyncio.subprocess`, stdlib `os`/`signal` (POSIX), Windows `taskkill.exe` invoked as a subprocess. No new dependencies.

**Spec:** No separate spec file — this plan was settled directly during a brainstorming session with the user, with per-decision consensus from a `plan-advisor` agent and a full independent design review from a `plan-reviewer` agent (both consulted via `herdr agent prompt` in this repo's planning tab). The originating defect is tracked as row **C6** in `docs/external-ideas-2026-09.md`.

## Global Constraints

- Both platforms matter: dev is Windows 11, CI is Linux docker. Every behavioral claim in this plan about Windows subprocess semantics was verified directly on the Windows dev box (Python 3.14) before being written down — do not re-derive it from memory, the numbers are in Task 1's notes.
- `kill_process_tree()` must **never raise**. It is always called from a cleanup path (a `TimeoutError` or `CancelledError` handler) that must not have its original exception masked by a cleanup failure.
- `asyncio.CancelledError` must always propagate (`raise`), never be swallowed into a normal return value — even at call sites whose sibling `TimeoutError` branch returns a value instead of raising.
- No new third-party dependencies (no `psutil`). Liveness checks in tests use a small stdlib-only cross-platform helper.
- Keep the existing `create_worktree` `.N` path fallback (`activities.py` `_ensure_worktree`) — it is defense in depth for Defender/Search-Indexer transient locks, which are independent of this fix. Its docstring gets updated, not its behavior.
- Known residual gap to document, not fix: `taskkill /T` walks a live parent→child snapshot. A grandchild spawned detached (its own console) or a case where an intermediate process dies first can still escape. Windows Job Objects would close this airtight; that is explicitly out of scope for this plan.
- Out of scope, and say so explicitly if a reviewer asks: `triage/gitread.py`'s `Popen` (spawns no children — not this defect), and the several unbounded `subprocess.run` call sites (`_git`, worktree ops, `gh pr create` in `activities.py`) — those hang without *any* timeout at all, which is a different defect than "the timeout fired but didn't kill enough."

---

## File Structure

- **Create:** `src/sdlc/process.py` — `kill_process_tree()` and its two platform-specific internals. Top-level (not nested under `harness/`) because 2 of the 5 call sites live outside the `harness/` subpackage and the helper has no harness-specific knowledge.
- **Create:** `tests/test_process.py` — direct unit tests of `kill_process_tree()`.
- **Modify:** `tests/conftest.py` — add a shared `_pid_alive(pid)` test helper (stdlib-only, cross-platform), reused by `test_process.py`, `test_harness_observability.py`, and `test_qa_timeout.py`.
- **Modify:** `src/sdlc/harness/adapters.py` — `CodingHarness.run()`: add `start_new_session=True` to its `create_subprocess_exec` call; add `except asyncio.CancelledError` alongside the existing `except TimeoutError`/`except Exception`, all three now calling `kill_process_tree()`.
- **Modify:** `tests/test_harness_observability.py` — add one grandchild-death regression test.
- **Modify:** `src/sdlc/activities.py` — `run_test_suite`, `run_lint`, `_bounded_shell`: add `start_new_session=True` to each `create_subprocess_shell` call; add `except asyncio.CancelledError` alongside each existing `except TimeoutError`. Also update `_ensure_worktree`'s docstring.
- **Modify:** `tests/test_qa_timeout.py` — add one grandchild-death regression test and one `CancelledError`-propagation test (both against `run_test_suite`).
- **Modify:** `src/sdlc/deploy/activities.py` — `_run()`: same spawn-kwarg and exception-handler change as above. No new dedicated test (see Task 4's rationale).
- **Modify:** `docs/external-ideas-2026-09.md` — update the C6 row's status once shipped.

---

### Task 1: `kill_process_tree()` helper + its unit tests

**Files:**
- Create: `src/sdlc/process.py`
- Modify: `tests/conftest.py` (add `_pid_alive`)
- Test: `tests/test_process.py`

**Interfaces:**
- Produces: `async def kill_process_tree(proc: asyncio.subprocess.Process) -> None` — importable as `from sdlc.process import kill_process_tree`. Never raises. Safe to call on a process that has already exited.
- Produces (conftest): `_pid_alive(pid: int) -> bool` in `tests/conftest.py`, importable by other test modules as `from tests.conftest import _pid_alive` — this matches how other test files in this repo already import helpers from conftest (e.g. `tests/test_worktree_idempotency.py:25` does `from tests.conftest import run_git`).

**Design notes carried into the code (from the plan-advisor / plan-reviewer consensus — write these as comments where indicated, don't re-derive them):**

- **POSIX kill order matters.** Resolve `os.getpgid(proc.pid)` *before* checking `proc.returncode`. `asyncio`'s child watcher can set `returncode` asynchronously (independent of an explicit `await proc.wait()`), so by the time cleanup runs the child may already be a zombie — but a zombie's pgid is still readable until it's reaped, and its process-group siblings (grandchildren) are very much still alive and killable. Checking `returncode` first and fast-returning would leak exactly the grandchildren this fix exists to kill. Only `ProcessLookupError` from `os.getpgid` itself means "fully reaped already, nothing reachable, done."
- **Self-kill guard.** If `os.getpgid(proc.pid)` equals our own `os.getpgrp()` or `os.getpid()`, the process was spawned without `start_new_session=True` (shares our process group) — `os.killpg` there would `SIGKILL` the calling worker process itself. Guard against this and fall back to killing only the direct child (`os.kill(pid, signal.SIGKILL)`), tolerating `ProcessLookupError`. This is a fail-to-leak-one-child safety net, not expected to trigger once all 5 call sites pass the new kwarg — but it protects any future call site that forgets it.
- **Windows fast-return is fine, POSIX fast-return is not.** On Windows, if `proc.returncode is not None` the root is already dead and `taskkill /T` cannot walk a tree from a PID that no longer exists in the process snapshot — so fast-returning there loses nothing. This asymmetry with POSIX is deliberate; don't unify the two paths.
- **`taskkill` invocation.** Spawn `taskkill /F /T /PID <pid>` via `asyncio.create_subprocess_exec` (not `subprocess.run` — stay async, don't block the event loop) with `stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL`. The common case is the child already exited by the time this runs (`taskkill` exits 128, "ERROR: The process ... not found"); without the `DEVNULL` redirects that text spills onto the worker's console from what is supposed to be a silent cleanup path. Tolerate every exit code — this call is always best-effort. `taskkill.exe` is a real executable in `System32` (always on `PATH`), not a `.cmd`/`.bat` shim, so it resolves via `CreateProcess`'s own implicit search exactly the way `adapters.py`'s existing harness-spawn comment already documents for real `.exe` files — no `shutil.which` needed (that workaround is specifically for npm's `.cmd` shims).
- **Final bounded reap, both platforms.** After the platform-specific kill, always do `await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)` (use `_REAP_TIMEOUT_S = 5.0`) inside a `try/except`. This confirms the direct child actually died (reaping it, avoiding a POSIX zombie) and gives tests a deterministic point to synchronize on. If it times out, log a `WARNING` with the pid so an operator can chase a survivor — but still don't raise.
- **Never raises, ever.** Wrap the platform dispatch itself in `try/except Exception: log.warning(..., exc_info=True)`. This function is only ever called from a handler for an exception that must not be masked.

**Windows liveness detail for the test helper (get this right, it will be copied elsewhere):** `os.kill(pid, 0)` on Windows does **not** mean "check if alive" the way it does on POSIX. `signal.CTRL_C_EVENT == 0`, so `os.kill(pid, 0)` sends a `CTRL_C_EVENT` via `GenerateConsoleCtrlEvent`, which only affects processes sharing the caller's console/process group and neither reliably checks liveness nor reliably kills. `_pid_alive` must branch: POSIX uses `os.kill(pid, 0)` (the real null-signal existence check, catching `ProcessLookupError` → dead, `PermissionError` → alive-but-not-ours); Windows shells out to `tasklist /FI "PID eq <pid>" /NH` and checks whether the pid string appears in stdout.

- [ ] **Step 1: Add the shared test liveness helper to `tests/conftest.py`**

Add near the top of `tests/conftest.py` (after the existing imports, before `run_git`):

```python
import sys


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check for a test to assert a process died.

    NOT os.kill(pid, 0) on Windows: signal.CTRL_C_EVENT == 0, so that call
    sends a console-control event (GenerateConsoleCtrlEvent) rather than
    checking existence, and only affects processes sharing the caller's
    console/process group -- neither a safe probe nor a reliable kill.
    """
    if sys.platform.startswith("win"):
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
```

- [ ] **Step 2: Write the failing tests in `tests/test_process.py`**

```python
"""Unit tests for kill_process_tree — the shared cleanup helper for C6
(kill the whole process tree on timeout/cancellation)."""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

from tests.conftest import _pid_alive
from sdlc.process import kill_process_tree


def _spawn_grandchild_script(pidfile: str) -> str:
    """A python -c script: spawns a grandchild that writes ITS OWN pid to
    `pidfile` and sleeps, then the parent (this script) also sleeps. Used
    to prove kill_process_tree kills descendants, not just the direct
    child. The grandchild writing its own pidfile (rather than the parent
    writing it) means the test can wait for the grandchild to actually
    exist before acting -- no timing luck."""
    return (
        "import subprocess, sys, time\n"
        "gc = subprocess.Popen([sys.executable, '-c', "
        '\'import os,time; open(r"{pidfile}","w").write(str(os.getpid())); time.sleep(60)\'])\n'
        "time.sleep(60)\n"
    ).format(pidfile=pidfile)


def _wait_for_pidfile(path: str, timeout_s: float = 10.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if os.path.exists(path):
            content = open(path).read().strip()
            if content:
                return int(content)
        time.sleep(0.05)
    raise TimeoutError(f"grandchild never wrote {path}")


def _wait_until_dead(pid: int, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    raise AssertionError(f"pid {pid} still alive after {timeout_s}s")


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_process.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.process'`

- [ ] **Step 4: Implement `src/sdlc/process.py`**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_process.py -v`
Expected: PASS — 2 passed + 1 skipped on Windows (the POSIX-guard test is skipped there); 3 passed on Linux

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/process.py tests/test_process.py tests/conftest.py
git commit -m "feat(process): add kill_process_tree helper (C6)"
```

---

### Task 2: Wire into `harness/adapters.py`'s `CodingHarness.run()`

**Files:**
- Modify: `src/sdlc/harness/adapters.py:248` (spawn), `:292-307` (except block)
- Test: `tests/test_harness_observability.py`

**Interfaces:**
- Consumes: `kill_process_tree(proc: asyncio.subprocess.Process) -> None` from Task 1 (`from ..process import kill_process_tree`).
- Consumes (test): `_pid_alive` from `tests/conftest.py` (Task 1).

**Current code at `harness/adapters.py:248-256`:**

```python
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=req.cwd,
            env=build_env(req.env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10_000_000,  # opencode text events can exceed the 64KB
            # default StreamReader line limit
        )
```

**Current code at `harness/adapters.py:292-307`:**

```python
        start = time.monotonic()
        try:
            stdout_b, stderr_s, _ = await asyncio.wait_for(
                asyncio.gather(_pump(), _pump_stderr(), proc.wait()),
                timeout=req.timeout_s,
            )
        except TimeoutError:
            proc.kill()
            _log.warning("harness timeout kind=%s cwd=%s cmd=%s", self.kind.value, req.cwd, cmd)
            raise
        except Exception:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise
```

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_harness_observability.py` (needs `import os`, `import time` at top alongside the existing `import sys`; add `from tests.conftest import _pid_alive`):

```python
def _wait_for_pidfile(path: str, timeout_s: float = 10.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if os.path.exists(path):
            content = open(path).read().strip()
            if content:
                return int(content)
        time.sleep(0.05)
    raise TimeoutError(f"grandchild never wrote {path}")


def _wait_until_dead(pid: int, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    raise AssertionError(f"pid {pid} still alive after {timeout_s}s")


@pytest.mark.asyncio
async def test_timeout_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")
    script = (
        "import subprocess, sys, time\n"
        "gc = subprocess.Popen([sys.executable, '-c', "
        '\'import os,time; open(r"{pidfile}","w").write(str(os.getpid())); time.sleep(60)\'])\n'
        "time.sleep(60)\n"
    ).format(pidfile=pidfile)
    harness = _PyHarness(script)
    run_task = asyncio.ensure_future(
        harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path), timeout_s=2))
    )
    grandchild_pid = _wait_for_pidfile(pidfile)

    with pytest.raises(asyncio.TimeoutError):
        await run_task

    _wait_until_dead(grandchild_pid)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_harness_observability.py::test_timeout_kills_grandchild -v`
Expected: FAIL — the grandchild is still alive after the timeout (assertion error from `_wait_until_dead`), proving the current `proc.kill()`-only behavior leaks it.

- [ ] **Step 3: Apply the fix**

Add the import at the top of `harness/adapters.py` (alongside the existing relative imports):

```python
from ..process import kill_process_tree
```

Change the spawn call (`:248-256`) to add one kwarg:

```python
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=req.cwd,
            env=build_env(req.env),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=10_000_000,  # opencode text events can exceed the 64KB
            # default StreamReader line limit
            start_new_session=True,  # C6: makes the whole tree killable as
            # a POSIX process group; a documented no-op on Windows
        )
```

Change the except block (`:292-307`) to:

```python
        start = time.monotonic()
        try:
            stdout_b, stderr_s, _ = await asyncio.wait_for(
                asyncio.gather(_pump(), _pump_stderr(), proc.wait()),
                timeout=req.timeout_s,
            )
        except TimeoutError:
            await asyncio.shield(kill_process_tree(proc))
            _log.warning("harness timeout kind=%s cwd=%s cmd=%s", self.kind.value, req.cwd, cmd)
            raise
        except asyncio.CancelledError:
            # Temporal activity cancellation. shield() so a second cancel
            # landing mid-cleanup can't abort the kill before it completes.
            await asyncio.shield(kill_process_tree(proc))
            raise
        except Exception:
            await asyncio.shield(kill_process_tree(proc))
            raise
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_harness_observability.py -v`
Expected: all PASS, including `test_timeout_kills_grandchild`

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_harness_observability.py
git commit -m "fix(harness): kill the whole process tree on run() timeout/cancel (C6)"
```

---

### Task 3: Wire into `activities.py`'s three shell sites

**Files:**
- Modify: `src/sdlc/activities.py:730` (`run_test_suite` spawn), `:739-741` (its except block)
- Modify: `src/sdlc/activities.py:847` (`run_lint` spawn), `:853-855` (approx — its except block, symmetric to `run_test_suite`'s)
- Modify: `src/sdlc/activities.py:1083` (`_bounded_shell` spawn), `:1086-1088` (its except block)
- Test: `tests/test_qa_timeout.py`

**Interfaces:**
- Consumes: `kill_process_tree` from Task 1 (`from .process import kill_process_tree` — `activities.py` is top-level in `sdlc/`).
- Consumes (test): `_pid_alive` from `tests/conftest.py` (Task 1).

**Current code, `run_test_suite` (`activities.py:730-751`):**

```python
    proc = await asyncio.create_subprocess_shell(
        inp.test_cmd,
        cwd=inp.worktree,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return QAReport(
            tests_passed=False,
            failing_tests=[],
            issues=[
                f"test command timed out after {inp.timeout_s}s "
                f"(cmd: {inp.test_cmd!r}) — likely hung on a "
                "long-running process (e.g. a dev server) rather "
                "than exiting after a one-shot test run"
            ],
        )
```

**Current code, `run_lint` (`activities.py:847-858`):**

```python
    proc = await asyncio.create_subprocess_shell(
        inp.lint_cmd,
        cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return False, (f"lint command timed out after {inp.timeout_s}s (cmd: {inp.lint_cmd!r})")
```

**Current code, `_bounded_shell` (`activities.py:1083-1092`):**

```python
    proc = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"command timed out after {timeout_s}s (cmd: {cmd!r})"
```

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_qa_timeout.py` (needs `import os`, `import time` at top alongside existing `import asyncio`, `import sys`; add `from tests.conftest import _pid_alive`):

```python
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


def _wait_for_pidfile(path: str, timeout_s: float = 10.0) -> int:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if os.path.exists(path):
            content = open(path).read().strip()
            if content:
                return int(content)
        time.sleep(0.05)
    raise TimeoutError(f"grandchild never wrote {path}")


def _wait_until_dead(pid: int, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    raise AssertionError(f"pid {pid} still alive after {timeout_s}s")


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
        grandchild_pid = _wait_for_pidfile(pidfile)
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
        grandchild_pid = _wait_for_pidfile(pidfile)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return grandchild_pid

    grandchild_pid = asyncio.run(_go())
    _wait_until_dead(grandchild_pid)
```

Add `import pytest` to `tests/test_qa_timeout.py`'s imports if not already present (check the file — it currently has none; the new `pytest.raises` call needs it).

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_qa_timeout.py -v`
Expected: `test_run_test_suite_timeout_kills_grandchild` FAILS (grandchild survives); `test_run_test_suite_cancelled_propagates_and_kills_grandchild` FAILS or hangs (today nothing catches `CancelledError` in `run_test_suite`, so cancellation isn't handled at all — if it hangs, interrupt and confirm by reading `run_test_suite`'s current source that no `except asyncio.CancelledError` exists).

- [ ] **Step 3: Apply the fix**

Add the import at the top of `activities.py` (alongside the existing `.harness.adapters` import):

```python
from .process import kill_process_tree
```

`run_test_suite` (`:730-751`) becomes:

```python
    proc = await asyncio.create_subprocess_shell(
        inp.test_cmd,
        cwd=inp.worktree,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return QAReport(
            tests_passed=False,
            failing_tests=[],
            issues=[
                f"test command timed out after {inp.timeout_s}s "
                f"(cmd: {inp.test_cmd!r}) — likely hung on a "
                "long-running process (e.g. a dev server) rather "
                "than exiting after a one-shot test run"
            ],
        )
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
```

`run_lint` (`:847-858`) becomes:

```python
    proc = await asyncio.create_subprocess_shell(
        inp.lint_cmd,
        cwd=inp.worktree,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return False, (f"lint command timed out after {inp.timeout_s}s (cmd: {inp.lint_cmd!r})")
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
```

`_bounded_shell` (`:1083-1092`) becomes:

```python
proc = await asyncio.create_subprocess_shell(
    cmd,
    cwd=cwd,
    env=env,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
    start_new_session=True,  # C6: whole tree killable as a group
)
try:
    out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
except TimeoutError:
    await asyncio.shield(kill_process_tree(proc))
    return -1, f"command timed out after {timeout_s}s (cmd: {cmd!r})"
except asyncio.CancelledError:
    await asyncio.shield(kill_process_tree(proc))
    raise
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_qa_timeout.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full existing QA/lint activity test coverage to confirm no regression**

Run: `pytest tests/test_qa_timeout.py tests/test_gate_timeout_action.py -v`
Expected: all PASS (this catches any test elsewhere that depended on the exact prior QAReport/tuple shape on timeout — it hasn't changed, but confirm it)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/activities.py tests/test_qa_timeout.py
git commit -m "fix(activities): kill the whole process tree on QA/lint/shell timeout+cancel (C6)"
```

---

### Task 4: Wire into `deploy/activities.py`'s `_run()`

**Files:**
- Modify: `src/sdlc/deploy/activities.py:65` (spawn), `:74-77` (except block)

**Interfaces:**
- Consumes: `kill_process_tree` from Task 1 (`from ..process import kill_process_tree` — `deploy/` is a subpackage of `sdlc/`).

**Why no new dedicated test here:** this is the same `create_subprocess_shell` + `proc.kill()`-only pattern already proven and covered by Task 1's direct unit tests of `kill_process_tree` and Task 3's end-to-end grandchild/cancellation regression tests against `run_test_suite`. Duplicating an identical grandchild-spawn integration test a third time for this site would test the call-site wiring pattern, not new behavior — the existing `tests/test_deploy_activities.py` suite already exercises `_run()`'s ordinary success/failure/timeout paths and will catch any wiring mistake (wrong import, wrong variable name) as an import or `NameError` failure.

**Current code (`deploy/activities.py:61-78`):**

```python
async def _run(cmd: str, cwd: str, env: dict[str, str], timeout_s: int) -> tuple[int, str]:
    """Run `cmd` in `cwd` with `env` layered over the worker's own. Returns
    (returncode, combined output). Never raises on a nonzero exit -- callers
    decide what a failure means."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout_s}s"
    return proc.returncode or 0, out_b.decode(errors="replace")[-4000:]
```

- [ ] **Step 1: Apply the fix**

Add the import at the top of `deploy/activities.py` (alongside the existing `.adapters` import):

```python
from ..process import kill_process_tree
```

Replace the function body:

```python
async def _run(cmd: str, cwd: str, env: dict[str, str], timeout_s: int) -> tuple[int, str]:
    """Run `cmd` in `cwd` with `env` layered over the worker's own. Returns
    (returncode, combined output). Never raises on a nonzero exit -- callers
    decide what a failure means."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return 124, f"timed out after {timeout_s}s"
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
    return proc.returncode or 0, out_b.decode(errors="replace")[-4000:]
```

- [ ] **Step 2: Run the existing deploy activities suite to confirm no regression**

Run: `pytest tests/test_deploy_activities.py tests/test_deploy_stage.py tests/test_deploy_compose_integration.py -v`
Expected: all PASS, unchanged from before this task

- [ ] **Step 3: Commit**

```bash
git add src/sdlc/deploy/activities.py
git commit -m "fix(deploy): kill the whole process tree on _run() timeout+cancel (C6)"
```

---

### Task 5: Documentation updates

**Files:**
- Modify: `src/sdlc/activities.py:216-222` (`_ensure_worktree` docstring)
- Modify: `docs/external-ideas-2026-09.md` (C6 row)

**Current docstring text (`activities.py:216-222`):**

```python
    Windows-only failure mode: if a stale ``path`` is held open by another
    process (WinError 32 — typically an orphan coding-agent subprocess
    whose CWD is the worktree, or a Defender real-time scan), no in-process
    API can move or delete it. We fall back to ``path.1``, ``path.2``, ...
    up to ``max_alt`` so the activity can still succeed; the orphaned dir
    is left behind for the OS / a later janitor to clean up once the lock
    holder releases.
    """
```

- [ ] **Step 1: Update the docstring**

```python
    Windows-only failure mode: if a stale ``path`` is held open by another
    process (WinError 32), no in-process API can move or delete it. We
    fall back to ``path.1``, ``path.2``, ... up to ``max_alt`` so the
    activity can still succeed; the orphaned dir is left behind for the
    OS / a later janitor to clean up once the lock holder releases.

    An orphan coding-agent subprocess holding the CWD open was the main
    cause of this — fixed at the root by ``kill_process_tree``
    (``src/sdlc/process.py``, C6), which now kills every process a timed-
    out or cancelled harness/shell run started, not just the direct
    child. This fallback stays as defense in depth for the remaining
    cause: a Defender/Search-Indexer real-time scan transiently holding a
    handle during its scan of a newly-populated worktree dir.
    """
```

- [ ] **Step 2: Update the C6 row in `docs/external-ideas-2026-09.md`**

Find the C6 row (currently `| C6 | ... | 🔴 **Live defect** | ... |`) and change its Status cell to `✅ **Fixed**`, and append one sentence to its "Where it lands" cell noting the shared helper: `— fixed via src/sdlc/process.py::kill_process_tree, wired into all 5 spawn sites (the 4 named here plus deploy/activities.py:65, found during implementation)`.

Also update the callout block immediately below the table (currently starting `> **C6 is not from a source.**`) — after its existing text, add: `Fixed 2026-09-02: see src/sdlc/process.py.`

- [ ] **Step 3: Commit**

```bash
git add src/sdlc/activities.py docs/external-ideas-2026-09.md
git commit -m "docs: point C6's worktree fallback comment and backlog row at the fix"
```

---

### Task 6: Full-suite regression check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`
Expected: all PASS, same failure count as `main` before this branch (there are ~122 known pre-existing mypy errors per this repo's dev-tooling baseline, unrelated to this change and out of scope — don't chase those; only pytest failures matter here).

- [ ] **Step 2: Note the platform gap for the reviewer**

This plan's regression tests (grandchild-death, cancellation) were designed and must pass locally on Windows. CI runs Linux docker — the POSIX branch in `src/sdlc/process.py` (`_kill_posix`, including the self-kill guard test in `tests/test_process.py`) only actually executes there, not on the Windows dev box. Call this out explicitly when requesting review: Windows coverage is real (ran locally), POSIX coverage is code-reviewed plus will be proven by CI on this branch's first push, not proven by a local run.

- [ ] **Step 3: Final commit if anything was touched during verification**

```bash
git status  # confirm clean, or add/commit any fixup
```
