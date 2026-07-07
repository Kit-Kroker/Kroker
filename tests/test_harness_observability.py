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
