"""D-3 made executable: an unreachable service is `errored`, never a pass."""

from __future__ import annotations

import os

import pytest

from sdlc.core.models import (
    DeployConfig,
)
from sdlc.deploy.activities import (
    RollbackInput,
    SmokeCheckInput,
    deploy_rollback,
    smoke_check,
)
from sdlc.stages.deploy.models import (
    DeployPlan,
    SmokeCheck,
    SmokeState,
)


def _inp(tmp_path, checks, endpoint="http://127.0.0.1:1", **cfg_over):
    cfg = DeployConfig(adapter="script", readiness_timeout_s=1, **cfg_over)
    return SmokeCheckInput(
        plan=DeployPlan(environment="staging", version="v2", smoke_checks=checks),
        cfg=cfg,
        repo_path=str(tmp_path),
        endpoint=endpoint,
    )


@pytest.mark.asyncio
async def test_no_checks_yields_no_results(tmp_path):
    out = await smoke_check(_inp(tmp_path, []))
    assert out.results == []


@pytest.mark.asyncio
async def test_http_checks_skipped_when_endpoint_is_empty(tmp_path):
    """F1: a script-adapter deploy has no endpoint. An http check against an
    empty endpoint cannot be evaluated and must not read as a failure (which
    would roll back every script deploy). It is skipped, not errored."""
    out = await smoke_check(
        _inp(
            tmp_path,
            [
                SmokeCheck(name="health", kind="http", path="/health"),
                SmokeCheck(name="ok", kind="command", command="exit 0"),
            ],
            endpoint="",
        )
    )
    # the http check is omitted; the command check still runs and passes
    assert [r.name for r in out.results] == ["ok"]
    assert out.results[0].state is SmokeState.PASSED


@pytest.mark.asyncio
async def test_passing_command_check(tmp_path):
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="ok", kind="command", command="exit 0")])
    )
    assert out.results[0].state is SmokeState.PASSED


@pytest.mark.asyncio
async def test_failing_command_check_is_failed_not_errored(tmp_path):
    """The assertion was evaluated and did not hold."""
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="nope", kind="command", command="exit 1")])
    )
    assert out.results[0].state is SmokeState.FAILED
    assert out.results[0].detail


@pytest.mark.asyncio
async def test_unreachable_http_check_is_errored_not_failed(tmp_path):
    """The load-bearing case. Port 1 refuses instantly -- we could not
    evaluate the assertion at all, and that must not read as a pass."""
    out = await smoke_check(
        _inp(tmp_path, [SmokeCheck(name="health", kind="http", path="/health")])
    )
    r = out.results[0]
    assert r.state is SmokeState.ERRORED
    assert r.passed is False
    assert r.detail


@pytest.mark.asyncio
async def test_every_check_gets_a_result(tmp_path):
    """A failure early must not swallow the checks after it -- the human
    reading the report needs the whole picture."""
    out = await smoke_check(
        _inp(
            tmp_path,
            [
                SmokeCheck(name="a", kind="command", command="exit 1"),
                SmokeCheck(name="b", kind="command", command="exit 0"),
                SmokeCheck(name="c", kind="http", path="/x"),
            ],
        )
    )
    assert [r.name for r in out.results] == ["a", "b", "c"]
    assert [r.state for r in out.results] == [
        SmokeState.FAILED,
        SmokeState.PASSED,
        SmokeState.ERRORED,
    ]


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax (test builtin)")
async def test_command_checks_see_the_deploy_environment(tmp_path):
    out = await smoke_check(
        _inp(
            tmp_path,
            [SmokeCheck(name="env", kind="command", command='test "$DEPLOY_VERSION" = "v2"')],
        )
    )
    assert out.results[0].state is SmokeState.PASSED


@pytest.mark.asyncio
async def test_rollback_raises_so_temporal_retries_it(tmp_path):
    """Rollback is the safety operation; a silent failure is unacceptable."""
    inp = RollbackInput(
        plan=DeployPlan(environment="staging", version="v2"),
        cfg=DeployConfig(adapter="script", commands={"rollback": "exit 1"}),
        repo_path=str(tmp_path),
        to_version="v1",
    )
    with pytest.raises(RuntimeError, match="rollback failed"):
        await deploy_rollback(inp)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="POSIX shell syntax (printf)")
async def test_rollback_runs_with_the_prior_version_in_scope(tmp_path):
    out = tmp_path / "v.txt"
    inp = RollbackInput(
        plan=DeployPlan(environment="staging", version="v2"),
        cfg=DeployConfig(
            adapter="script",
            commands={"rollback": f'printf "%s" "$DEPLOY_VERSION" > "{out.as_posix()}"'},
        ),
        repo_path=str(tmp_path),
        to_version="v1",
    )
    await deploy_rollback(inp)
    assert out.read_text().strip() == "v1"
