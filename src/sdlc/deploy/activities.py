"""Deploy activities (E-67). The adapters produce command strings; this
module is the only place that runs them.

Split note: reading the current version is its OWN activity rather than a
step inside deploy_apply. If apply raises, the workflow must still hold the
prior version -- that is exactly the path where a rollback is needed.
"""

from __future__ import annotations

import asyncio
import os
import urllib.error
import urllib.request

from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ..models import (
    DeployConfig,
    DeployPlan,
    SmokeCheckResult,
    SmokeState,
)
from .adapters import resolve

# A version probe or an apply that hangs must not sit on the activity's
# start_to_close_timeout doing nothing visible; these bound the subprocess
# itself so the failure is ours to report.
VERSION_TIMEOUT_S = 60
APPLY_TIMEOUT_S = 3600


def _safe_heartbeat(*args) -> None:
    """activity.heartbeat() outside a real Temporal activity execution
    context (e.g. a plain-async-function test call) raises RuntimeError --
    swallow that so a liveness signal never breaks the activity. Mirrors
    benchmarks/oracle.py's _safe_heartbeat for the same reason."""
    try:
        activity.heartbeat(*args)
    except Exception:
        pass


class DeployActivityInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str


class CurrentVersionResult(BaseModel):
    version: str | None = None


class ApplyResult(BaseModel):
    endpoint: str = ""
    detail: str = ""


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


@activity.defn
async def deploy_current_version(inp: DeployActivityInput) -> CurrentVersionResult:
    """Best-effort read of what is running now, BEFORE anything changes.

    A failed or empty probe is not an error: it means we have no rollback
    target, which the DeployReport states plainly rather than pretending a
    rollback is available."""
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.current_version_cmd(inp.plan),
        inp.repo_path,
        adapter.env(inp.plan),
        VERSION_TIMEOUT_S,
    )
    if code != 0:
        activity.logger.info("version probe failed (%s): %s", code, out[-200:])
        return CurrentVersionResult(version=None)
    return CurrentVersionResult(version=out.strip() or None)


@activity.defn
async def deploy_apply(inp: DeployActivityInput) -> ApplyResult:
    """Bring plan.version up. A zero exit means something is running -- the
    smoke checks, not this activity, decide whether it works."""
    if not inp.plan.frozen:
        # Non-retryable: retrying cannot make a plan frozen. A bare ValueError
        # would be retried under APPLY_ACT -- ApplicationError(non_retryable)
        # is what actually stops Temporal retrying.
        raise ApplicationError(
            "refusing to apply a DeployPlan that is not frozen "
            "(it must be frozen at the plan gate)",
            non_retryable=True,
        )
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.apply_cmd(inp.plan), inp.repo_path, adapter.env(inp.plan), APPLY_TIMEOUT_S
    )
    if code != 0:
        raise RuntimeError(f"deploy failed ({code}): {out[-2000:]}")
    return ApplyResult(endpoint=adapter.endpoint(inp.plan), detail=out[-2000:])


class SmokeCheckInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    endpoint: str


class SmokeCheckOutput(BaseModel):
    # Wrapped rather than a bare list: activity payloads round-trip through
    # the pydantic data converter more predictably as a model.
    results: list[SmokeCheckResult] = []


class RollbackInput(BaseModel):
    plan: DeployPlan
    cfg: DeployConfig
    repo_path: str
    to_version: str


def _http_once(url: str, expect_status: int, timeout_s: int) -> SmokeCheckResult | None:
    """Returns None if the request could not be made at all (caller decides
    whether that is 'not ready yet' or 'errored')."""
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code  # a response IS an evaluation
    except Exception:
        return None  # no response: we learned nothing
    return SmokeCheckResult(
        name="",
        state=(SmokeState.PASSED if status == expect_status else SmokeState.FAILED),
        detail=("" if status == expect_status else f"expected {expect_status}, got {status}"),
    )


async def _await_readiness(url: str, timeout_s: int) -> None:
    """Poll until the endpoint answers at all, or the budget runs out. A
    container that just started is not yet a broken one."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        _safe_heartbeat("awaiting readiness")
        if await asyncio.to_thread(_http_once, url, 200, 5) is not None:
            return
        await asyncio.sleep(1)


@activity.defn
async def smoke_check(inp: SmokeCheckInput) -> SmokeCheckOutput:
    """Run every check exactly once and return a result for each.

    NEVER raises on an assertion failure: the workflow decides what a failure
    means. Retrying a smoke check would mask the very signal being collected,
    which is why this activity is registered with maximum_attempts=1 and does
    its own readiness polling instead.
    """
    adapter = resolve(inp.cfg)
    env = adapter.env(inp.plan)
    http_checks = [c for c in inp.plan.smoke_checks if c.kind == "http"]
    if http_checks and inp.endpoint:
        await _await_readiness(
            inp.endpoint.rstrip("/") + "/" + http_checks[0].path.lstrip("/"),
            inp.cfg.readiness_timeout_s,
        )

    results: list[SmokeCheckResult] = []
    for check in inp.plan.smoke_checks:
        _safe_heartbeat(check.name)
        if check.kind == "http":
            if not inp.endpoint:
                # No endpoint configured (e.g. a script-adapter deploy with
                # no base_url). The check cannot be evaluated and must not
                # read as a failure -- skipping it (not erroring) is what
                # keeps D-7's "make deploy" target working.
                activity.logger.info("skipping http check %r: no endpoint configured", check.name)
                continue
            url = inp.endpoint.rstrip("/") + "/" + check.path.lstrip("/")
            outcome = await asyncio.to_thread(_http_once, url, check.expect_status, check.timeout_s)
            if outcome is None:
                results.append(
                    SmokeCheckResult(
                        name=check.name,
                        state=SmokeState.ERRORED,
                        detail=f"no response from {url} within {check.timeout_s}s",
                    )
                )
            else:
                results.append(outcome.model_copy(update={"name": check.name}))
            continue

        code, out = await _run(check.command, inp.repo_path, env, check.timeout_s)
        if code == 124:
            results.append(SmokeCheckResult(name=check.name, state=SmokeState.ERRORED, detail=out))
        elif code != 0:
            results.append(
                SmokeCheckResult(
                    name=check.name, state=SmokeState.FAILED, detail=f"exit {code}: {out[-500:]}"
                )
            )
        else:
            results.append(SmokeCheckResult(name=check.name, state=SmokeState.PASSED))
    return SmokeCheckOutput(results=results)


@activity.defn
async def deploy_rollback(inp: RollbackInput) -> None:
    """Restore `to_version`. Raises on failure so Temporal's retry policy
    gets its chance -- this is the safety operation, and a failed rollback is
    the worst outcome in the system."""
    adapter = resolve(inp.cfg)
    code, out = await _run(
        adapter.rollback_cmd(inp.plan, inp.to_version),
        inp.repo_path,
        adapter.env(inp.plan, version=inp.to_version),
        APPLY_TIMEOUT_S,
    )
    if code != 0:
        raise RuntimeError(f"rollback failed ({code}): {out[-2000:]}")
