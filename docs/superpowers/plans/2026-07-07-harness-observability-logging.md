# Harness Observability Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `src/sdlc/harness/adapters.py` runs diagnosable — fix the dead stderr pipe, log the stdout event stream live (not just after the process exits), log run lifecycle/summary info, and log parse failures that currently fail silently.

**Architecture:** All changes live in `src/sdlc/harness/adapters.py`, using a module-level `logging.getLogger(__name__)` (matching `src/sdlc/benchmarks/drift.py`'s existing convention). No new persistence, no `HarnessRunResult` model changes — everything is a log line. `run()` on the shared `CodingHarness` base class gets a concurrent stderr drain, a line-based stdout pump that logs each event as it streams, and start/timeout/summary/stderr-tail log lines. Both `ClaudeCodeHarness.parse()` and `OpenCodeHarness.parse()` get logging on their existing silent-failure branches.

**Tech Stack:** Python 3.14, asyncio subprocess, stdlib `logging`, pytest + `pytest-asyncio` (`@pytest.mark.asyncio`, already used elsewhere in this repo), `caplog` for log assertions.

## Global Constraints

- No new dependencies.
- No changes to `HarnessRunResult` (in `src/sdlc/models.py`) or `activities.py`.
- No new persistence (no jsonl/db) — structured log lines only.
- Never log the full prompt body (may be large or contain repo content) or full stdout/stderr beyond the existing `SUMMARY_MAX` (4000 chars) cap.
- Follow the existing module logger convention: `_log = logging.getLogger(__name__)` (see `src/sdlc/benchmarks/drift.py:18`).

---

### Task 1: Fix the dead stderr pipe + lifecycle logging in `run()`

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (imports at top; `CodingHarness.run()`, currently lines 90–130)
- Create: `tests/test_harness_observability.py`

**Interfaces:**
- Consumes: existing `CodingHarness` ABC, `HarnessRequest`, `context_window_for`, `build_env`, `SUMMARY_MAX` (all already in `adapters.py`).
- Produces: `CodingHarness.run()` keeps its existing signature and return type (`HarnessRunResult`) — this task changes internals and adds logging only, no interface change for Task 2/3 to consume beyond the module logger `_log` and constant `SUMMARY_MAX` which already exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_harness_observability.py`:

```python
import asyncio
import logging
import sys

import pytest

from sdlc.harness.adapters import CodingHarness, HarnessRequest
from sdlc.models import HarnessKind, HarnessRunResult


class _PyHarness(CodingHarness):
    """Runs a short Python script as the subprocess so these tests don't
    depend on the real claude/opencode CLIs being installed."""

    kind = HarnessKind.OPENCODE

    def __init__(self, script: str):
        self.script = script

    def build_cmd(self, req: HarnessRequest) -> list[str]:
        return [sys.executable, "-c", self.script]

    def parse(self, stdout: str, exit_code: int) -> HarnessRunResult:
        return HarnessRunResult(harness=self.kind, exit_code=exit_code, summary=stdout[:4000])


@pytest.mark.asyncio
async def test_large_stderr_does_not_deadlock(tmp_path):
    # Writes well past the OS pipe buffer (64KB) to stderr while also
    # writing to stdout. Before the fix, nothing read stderr, so the child
    # blocks once its stderr pipe fills, and the run never finishes.
    script = "import sys\nsys.stderr.write('e' * 200_000)\nsys.stderr.flush()\nprint('done')\n"
    harness = _PyHarness(script)
    result = await asyncio.wait_for(
        harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path), timeout_s=10)),
        timeout=15,
    )
    assert result.exit_code == 0
    assert result.summary == "done\n"


@pytest.mark.asyncio
async def test_lifecycle_summary_logged(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    harness = _PyHarness("print('hi')")
    await harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path)))
    assert any("harness done" in r.message for r in caplog.records)
    assert any("exit_code=0" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_stderr_logged_as_warning_on_failure(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    script = "import sys\nsys.stderr.write('boom detail')\nsys.exit(1)\n"
    harness = _PyHarness(script)
    result = await harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path)))
    assert result.exit_code == 1
    assert any("boom detail" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_timeout_logs_warning(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    script = "import time\ntime.sleep(5)\n"
    harness = _PyHarness(script)
    with pytest.raises(asyncio.TimeoutError):
        await harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path), timeout_s=1))
    assert any("harness timeout" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness_observability.py -v`
Expected: `test_large_stderr_does_not_deadlock` times out (or hangs — if it hangs past your patience, `Ctrl-C` and note this confirms the bug); the logging tests FAIL with no matching records (no logging exists yet).

- [ ] **Step 3: Add the module logger and `time` import**

In `src/sdlc/harness/adapters.py`, add to the imports (after the existing `import shutil` at line 20):

```python
import time
import logging
```

and after the existing `SUMMARY_MAX = 4000` line (line 26), add:

```python
_log = logging.getLogger(__name__)
```

- [ ] **Step 4: Rewrite `CodingHarness.run()`**

Replace the entire `run()` method (currently lines 90–130) with:

```python
async def run(self, req: HarnessRequest, heartbeat=None) -> HarnessRunResult:
    cmd = self.build_cmd(req)
    # Resolve via PATH — Windows npm shims are .cmd files that
    # CreateProcess can't find without an explicit extension.
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd[0] = resolved
    _log.debug(
        "harness start kind=%s model=%s session_id=%s cwd=%s",
        self.kind.value,
        req.model,
        req.session_id,
        req.cwd,
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=req.cwd,
        env=build_env(req.env),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=10_000_000,  # opencode text events can exceed the 64KB
        # default StreamReader line limit
    )

    async def _pump() -> bytes:
        chunks: list[bytes] = []
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if heartbeat:
                heartbeat()  # keep the Temporal activity alive
        return b"".join(chunks)

    async def _pump_stderr() -> str:
        # Drained concurrently with stdout — an unread stderr pipe can
        # fill its OS buffer and deadlock the child if it writes enough.
        chunks: list[bytes] = []
        size = 0
        assert proc.stderr is not None
        while True:
            chunk = await proc.stderr.read(65536)
            if not chunk:
                break
            if size < SUMMARY_MAX:
                chunks.append(chunk)
                size += len(chunk)
        return b"".join(chunks).decode(errors="replace")[:SUMMARY_MAX]

    start = time.monotonic()
    try:
        stdout_b, stderr_s, _ = await asyncio.wait_for(
            asyncio.gather(_pump(), _pump_stderr(), proc.wait()),
            timeout=req.timeout_s,
        )
    except asyncio.TimeoutError:
        proc.kill()
        _log.warning("harness timeout kind=%s cwd=%s cmd=%s", self.kind.value, req.cwd, cmd)
        raise
    duration_s = time.monotonic() - start

    result = self.parse(stdout_b.decode(errors="replace"), proc.returncode or 0)
    if result.context_window is None:
        result.context_window = context_window_for(req.model)

    _log.info(
        "harness done kind=%s exit_code=%s session_id=%s "
        "duration_s=%.1f input_tokens=%s output_tokens=%s cost_usd=%s",
        self.kind.value,
        result.exit_code,
        result.session_id,
        duration_s,
        result.input_tokens,
        result.output_tokens,
        result.cost_usd,
    )
    if result.exit_code != 0 or stderr_s:
        _log.warning(
            "harness stderr kind=%s exit_code=%s stderr=%s",
            self.kind.value,
            result.exit_code,
            stderr_s,
        )
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_harness_observability.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Run the full existing harness test suite to check for regressions**

Run: `pytest tests/test_harness_parse.py tests/test_harness_result.py -v`
Expected: all PASS unchanged (this task didn't touch `parse()` or `build_cmd()`).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_harness_observability.py
git commit -m "fix(harness): drain stderr concurrently, log run lifecycle"
```

---

### Task 2: Live stdout event-stream logging

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`_pump()` inside `CodingHarness.run()`; add a new module-level function `_log_live_event`)
- Modify: `tests/test_harness_observability.py`

**Interfaces:**
- Consumes: `_log` (module logger from Task 1), `json` (already imported at top of `adapters.py`).
- Produces: `_log_live_event(line: str) -> None` — a pure, non-raising module-level function. No other task depends on it beyond this one; it's called only from `_pump()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_harness_observability.py`:

```python
import json

from sdlc.harness.adapters import _log_live_event


def test_log_live_event_step_start_logged_at_info(caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    _log_live_event(json.dumps({"type": "step_start", "sessionID": "abc"}))
    assert any("step_start" in r.message and "abc" in r.message for r in caplog.records)


def test_log_live_event_step_finish_logs_tokens_and_cost(caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    _log_live_event(
        json.dumps(
            {
                "type": "step_finish",
                "sessionID": "abc",
                "part": {"tokens": {"input": 10, "output": 2}, "cost": 0.01},
            }
        )
    )
    assert any(
        "step_finish" in r.message and "input_tokens=10" in r.message for r in caplog.records
    )


def test_log_live_event_text_logged_at_debug_with_length_not_content(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    _log_live_event(
        json.dumps(
            {
                "type": "text",
                "sessionID": "abc",
                "part": {"text": "some repo content that should not be logged verbatim"},
            }
        )
    )
    messages = [r.message for r in caplog.records]
    assert any("chars=" in m for m in messages)
    assert not any("some repo content" in m for m in messages)


def test_log_live_event_ignores_non_json_and_unknown_type(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    _log_live_event("not json at all")  # must not raise
    _log_live_event(json.dumps({"type": "something_else"}))
    assert caplog.records == []


@pytest.mark.asyncio
async def test_run_logs_events_as_they_stream(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    script = (
        "import json\n"
        "print(json.dumps({'type': 'step_start', 'sessionID': 's1'}))\n"
        "print(json.dumps({'type': 'step_finish', 'sessionID': 's1', "
        "'part': {'tokens': {'input': 5, 'output': 1}, 'cost': 0.0}}))\n"
    )
    harness = _PyHarness(script)
    await harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path)))
    messages = [r.message for r in caplog.records]
    assert any("step_start" in m for m in messages)
    assert any("step_finish" in m for m in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness_observability.py -v`
Expected: the new tests FAIL with `ImportError`/`AttributeError` (`_log_live_event` does not exist yet).

- [ ] **Step 3: Add `_log_live_event` and wire it into `_pump()`**

In `src/sdlc/harness/adapters.py`, add this module-level function directly above the `CodingHarness` class definition (before `class CodingHarness(ABC):`):

```python
def _log_live_event(line: str) -> None:
    """Best-effort live logging of one opencode --format json event line as
    it streams. Never raises: a line that doesn't parse (e.g. Claude Code's
    single final JSON payload, which isn't line-delimited) is silently
    skipped — parse-time failure logging is handled separately in parse()."""
    line = line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return
    ev_type = ev.get("type")
    session_id = ev.get("sessionID") or ev.get("session_id")
    if ev_type == "step_start":
        _log.info("harness step_start session_id=%s", session_id)
    elif ev_type == "step_finish":
        part = ev.get("part") or {}
        tokens = part.get("tokens") or {}
        _log.info(
            "harness step_finish session_id=%s input_tokens=%s output_tokens=%s cost_usd=%s",
            session_id,
            tokens.get("input"),
            tokens.get("output"),
            part.get("cost"),
        )
    elif ev_type == "text":
        part = ev.get("part") or {}
        _log.debug("harness text session_id=%s chars=%d", session_id, len(part.get("text") or ""))
```

Then, inside `run()`, replace the `_pump()` function body (added in Task 1) with a line-based read that calls it:

```python
async def _pump() -> bytes:
    chunks: list[bytes] = []
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        chunks.append(line)
        _log_live_event(line.decode(errors="replace"))
        if heartbeat:
            heartbeat()  # keep the Temporal activity alive
    return b"".join(chunks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harness_observability.py -v`
Expected: all tests PASS, including the 4 from Task 1 (regression check).

- [ ] **Step 5: Run the full existing harness test suite to check for regressions**

Run: `pytest tests/test_harness_parse.py tests/test_harness_result.py -v`
Expected: all PASS unchanged (`readline()` reconstructs the same byte stream `parse()` consumes; only how it's chunked while reading changed).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_harness_observability.py
git commit -m "feat(harness): log opencode's stdout event stream live"
```

---

### Task 3: Parse-failure logging in both adapters

**Files:**
- Modify: `src/sdlc/harness/adapters.py` (`OpenCodeHarness.parse()`, currently lines 208–244; `ClaudeCodeHarness.parse()`, currently lines 154–171)
- Modify: `tests/test_harness_parse.py`

**Interfaces:**
- Consumes: `_log` (module logger from Task 1). No new functions produced; this task only adds log calls on existing silent branches inside `parse()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_harness_parse.py`:

```python
import logging


def test_opencode_parse_logs_debug_on_malformed_line(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    events = "\n".join(
        [
            "not valid json",
            json.dumps(
                {"type": "step_finish", "sessionID": "s", "part": {"tokens": {}, "cost": 0.0}}
            ),
        ]
    )
    OpenCodeHarness().parse(events, 0)
    assert any("not valid json" in r.message for r in caplog.records)


def test_opencode_parse_logs_warning_when_nothing_parses(caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    OpenCodeHarness().parse("not json at all", 1)
    assert any("parsed_any" in r.message or "no events parsed" in r.message for r in caplog.records)


def test_claude_parse_logs_warning_on_decode_failure(caplog):
    caplog.set_level(logging.WARNING, logger="sdlc.harness.adapters")
    ClaudeCodeHarness().parse("not json at all", 1)
    assert any(
        "decode" in r.message.lower() or "fallback" in r.message.lower() for r in caplog.records
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness_parse.py -v`
Expected: the 3 new tests FAIL (no matching log records — logging doesn't exist on these branches yet).

- [ ] **Step 3: Add logging to `OpenCodeHarness.parse()`**

In `src/sdlc/harness/adapters.py`, in `OpenCodeHarness.parse()`, change:

```python
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                continue
            parsed_any = True
```

to:

```python
            try:
                ev = json.loads(ln)
            except json.JSONDecodeError:
                _log.debug("opencode parse: skipping malformed line: %s", ln)
                continue
            parsed_any = True
```

and change:

```python
        summary = "\n".join(text_parts) if parsed_any else stdout
```

to:

```python
if not parsed_any:
    _log.warning(
        "opencode parse: no events parsed from stdout "
        "(parsed_any=False); falling back to raw stdout"
    )
summary = "\n".join(text_parts) if parsed_any else stdout
```

- [ ] **Step 4: Add logging to `ClaudeCodeHarness.parse()`**

In `src/sdlc/harness/adapters.py`, in `ClaudeCodeHarness.parse()`, change:

```python
        except (json.JSONDecodeError, IndexError):
            summary = stdout
```

to:

```python
        except (json.JSONDecodeError, IndexError):
            _log.warning("claude parse: JSON decode failed, falling back "
                         "to raw stdout as summary")
            summary = stdout
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_harness_parse.py -v`
Expected: all tests PASS (existing + 3 new).

- [ ] **Step 6: Run the full test suite for this module to check for regressions**

Run: `pytest tests/test_harness_parse.py tests/test_harness_result.py tests/test_harness_observability.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/harness/adapters.py tests/test_harness_parse.py
git commit -m "fix(harness): log silent parse-failure fallbacks in both adapters"
```

---

## Final Verification

- [ ] Run the complete test suite: `pytest -q`
- [ ] Expected: all tests PASS, no regressions in any other module.
