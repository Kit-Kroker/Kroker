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
        return HarnessRunResult(harness=self.kind, exit_code=exit_code,
                                 summary=stdout[:4000])


@pytest.mark.asyncio
async def test_large_stderr_does_not_deadlock(tmp_path):
    # Writes well past the OS pipe buffer (64KB) to stderr while also
    # writing to stdout. Before the fix, nothing read stderr, so the child
    # blocks once its stderr pipe fills, and the run never finishes.
    script = (
        "import sys\n"
        "sys.stderr.write('e' * 200_000)\n"
        "sys.stderr.flush()\n"
        "print('done')\n"
    )
    harness = _PyHarness(script)
    result = await asyncio.wait_for(
        harness.run(HarnessRequest(prompt="x", cwd=str(tmp_path), timeout_s=10)),
        timeout=15,
    )
    assert result.exit_code == 0
    # Normalize CRLF: on Windows, `print()` writes "\r\n" via the child's
    # text-mode stdout; the behavior under test (stdout fully captured,
    # no deadlock) is unaffected by the platform's line-ending convention.
    assert result.summary.replace("\r\n", "\n") == "done\n"


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
    script = (
        "import sys\n"
        "sys.stderr.write('boom detail')\n"
        "sys.exit(1)\n"
    )
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


import json

from sdlc.harness.adapters import _log_live_event


def test_log_live_event_step_start_logged_at_info(caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    _log_live_event(json.dumps({"type": "step_start", "sessionID": "abc"}))
    assert any("step_start" in r.message and "abc" in r.message
               for r in caplog.records)


def test_log_live_event_step_finish_logs_tokens_and_cost(caplog):
    caplog.set_level(logging.INFO, logger="sdlc.harness.adapters")
    _log_live_event(json.dumps({
        "type": "step_finish", "sessionID": "abc",
        "part": {"tokens": {"input": 10, "output": 2}, "cost": 0.01},
    }))
    assert any("step_finish" in r.message and "input_tokens=10" in r.message
               for r in caplog.records)


def test_log_live_event_text_logged_at_debug_with_length_not_content(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    _log_live_event(json.dumps({
        "type": "text", "sessionID": "abc",
        "part": {"text": "some repo content that should not be logged verbatim"},
    }))
    messages = [r.message for r in caplog.records]
    assert any("chars=" in m for m in messages)
    assert not any("some repo content" in m for m in messages)


def test_log_live_event_ignores_non_json_and_unknown_type(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    _log_live_event("not json at all")             # must not raise
    _log_live_event(json.dumps({"type": "something_else"}))
    assert caplog.records == []


def test_log_live_event_ignores_non_dict_json(caplog):
    caplog.set_level(logging.DEBUG, logger="sdlc.harness.adapters")
    for line in ("42", "[1,2,3]", "true", "null"):
        _log_live_event(line)   # must not raise
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
