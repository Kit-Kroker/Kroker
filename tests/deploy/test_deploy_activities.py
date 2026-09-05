"""E-67 activities. These execute the pure adapters' command strings; the
adapters themselves stay subprocess-free."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from sdlc.core.models import (
    DeployConfig,
)
from sdlc.stages.deploy.activities import (
    ApplyResult,
    CurrentVersionResult,
    DeployActivityInput,
    _run,
    deploy_apply,
    deploy_current_version,
)
from sdlc.stages.deploy.models import DeployPlan
from tests.conftest import _wait_for_pidfile_async, _wait_until_dead


def _inp(tmp_path, **cfg_over) -> DeployActivityInput:
    cfg = DeployConfig(adapter="script", **cfg_over)
    return DeployActivityInput(
        plan=DeployPlan(environment="staging", version="v2"), cfg=cfg, repo_path=str(tmp_path)
    )


@pytest.mark.asyncio
async def test_current_version_returns_trimmed_stdout(tmp_path):
    inp = _inp(tmp_path, commands={"version": "echo   v1  "})
    assert (await deploy_current_version(inp)) == CurrentVersionResult(version="v1")


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax (bare echo)")
async def test_empty_stdout_means_nothing_is_deployed_yet(tmp_path):
    """First-ever deploy: there is no prior version, and None says so."""
    inp = _inp(tmp_path, commands={"version": "echo"})
    assert (await deploy_current_version(inp)).version is None


@pytest.mark.asyncio
async def test_failing_version_probe_is_not_fatal(tmp_path):
    """A target with no `make version` target must not break the deploy --
    it only means we cannot roll back, which the report states plainly."""
    inp = _inp(tmp_path, commands={"version": "exit 3"})
    assert (await deploy_current_version(inp)).version is None


@pytest.mark.asyncio
async def test_apply_returns_the_endpoint_on_success(tmp_path):
    inp = _inp(tmp_path, commands={"deploy": "echo shipped"}, base_url="http://localhost:1234")
    result = await deploy_apply(inp)
    assert isinstance(result, ApplyResult)
    assert result.endpoint == "http://localhost:1234"


@pytest.mark.asyncio
async def test_apply_raises_on_a_nonzero_exit(tmp_path):
    inp = _inp(tmp_path, commands={"deploy": "exit 1"})
    with pytest.raises(RuntimeError, match="deploy failed"):
        await deploy_apply(inp)


@pytest.mark.asyncio
async def test_apply_refuses_an_unfrozen_plan(tmp_path):
    """Catches 'someone edited the plan after the gate' (spec §7)."""
    from temporalio.exceptions import ApplicationError

    inp = _inp(tmp_path, commands={"deploy": "echo shipped"})
    inp.plan.frozen = False
    with pytest.raises(ApplicationError, match="frozen"):
        await deploy_apply(inp)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax (printf)")
async def test_apply_exports_the_plan_environment(tmp_path):
    out = tmp_path / "env.txt"
    inp = _inp(tmp_path, commands={"deploy": f'printf "%s" "$DEPLOY_VERSION" > "{out.as_posix()}"'})
    await deploy_apply(inp)
    assert out.read_text().strip() == "v2"


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


@pytest.mark.asyncio
async def test_run_timeout_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")
    cmd = _grandchild_sleep_cmd(tmp_path, pidfile, 60)
    task = asyncio.ensure_future(_run(cmd, str(tmp_path), {}, timeout_s=2))
    grandchild_pid = await _wait_for_pidfile_async(pidfile)
    code, out = await task
    assert code == 124
    assert "timed out" in out
    _wait_until_dead(grandchild_pid)


@pytest.mark.asyncio
async def test_run_cancelled_propagates_and_kills_grandchild(tmp_path):
    pidfile = str(tmp_path / "grandchild.pid")
    cmd = _grandchild_sleep_cmd(tmp_path, pidfile, 60)
    task = asyncio.ensure_future(_run(cmd, str(tmp_path), {}, timeout_s=30))
    grandchild_pid = await _wait_for_pidfile_async(pidfile)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    _wait_until_dead(grandchild_pid)
