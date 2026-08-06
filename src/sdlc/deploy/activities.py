"""Deploy activities (E-67). The adapters produce command strings; this
module is the only place that runs them.

Split note: reading the current version is its OWN activity rather than a
step inside deploy_apply. If apply raises, the workflow must still hold the
prior version -- that is exactly the path where a rollback is needed.
"""
from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel
from temporalio import activity

from .adapters import resolve
from ..models import DeployConfig, DeployPlan

# A version probe or an apply that hangs must not sit on the activity's
# start_to_close_timeout doing nothing visible; these bound the subprocess
# itself so the failure is ours to report.
VERSION_TIMEOUT_S = 60
APPLY_TIMEOUT_S = 3600


class DeployActivityInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str


class CurrentVersionResult(BaseModel):
    version: str | None = None


class ApplyResult(BaseModel):
    endpoint: str = ""
    detail: str = ""


async def _run(cmd: str, cwd: str, env: dict[str, str],
               timeout_s: int) -> tuple[int, str]:
    """Run `cmd` in `cwd` with `env` layered over the worker's own. Returns
    (returncode, combined output). Never raises on a nonzero exit -- callers
    decide what a failure means."""
    proc = await asyncio.create_subprocess_shell(
        cmd, cwd=cwd, env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout_s}s"
    return proc.returncode or 0, out_b.decode(errors="replace")[-4000:]


@activity.defn
async def deploy_current_version(
        inp: DeployActivityInput) -> CurrentVersionResult:
    """Best-effort read of what is running now, BEFORE anything changes.

    A failed or empty probe is not an error: it means we have no rollback
    target, which the DeployReport states plainly rather than pretending a
    rollback is available."""
    adapter = resolve(inp.cfg)
    code, out = await _run(adapter.current_version_cmd(inp.plan),
                           inp.repo_path, adapter.env(inp.plan),
                           VERSION_TIMEOUT_S)
    if code != 0:
        activity.logger.info("version probe failed (%s): %s", code, out[-200:])
        return CurrentVersionResult(version=None)
    return CurrentVersionResult(version=out.strip() or None)


@activity.defn
async def deploy_apply(inp: DeployActivityInput) -> ApplyResult:
    """Bring plan.version up. A zero exit means something is running -- the
    smoke checks, not this activity, decide whether it works."""
    if not inp.plan.frozen:
        # Non-retryable by construction: retrying cannot make it frozen.
        raise ValueError(
            "refusing to apply a DeployPlan that is not frozen "
            "(it must be frozen at the plan gate)")
    adapter = resolve(inp.cfg)
    code, out = await _run(adapter.apply_cmd(inp.plan), inp.repo_path,
                           adapter.env(inp.plan), APPLY_TIMEOUT_S)
    if code != 0:
        raise RuntimeError(f"deploy failed ({code}): {out[-2000:]}")
    return ApplyResult(endpoint=adapter.endpoint(inp.plan), detail=out[-2000:])
