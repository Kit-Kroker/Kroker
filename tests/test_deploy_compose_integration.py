"""The only test proving the compose adapter's ROLLBACK MECHANICS. Everything
else proves the sequencing around them (D-8)."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import urllib.request

import pytest

from sdlc.deploy.activities import (
    DeployActivityInput,
    RollbackInput,
    SmokeCheckInput,
    deploy_apply,
    deploy_current_version,
    deploy_rollback,
    smoke_check,
)
from sdlc.models import (
    DeployConfig,
    DeployPlan,
    SmokeCheck,
    SmokeState,
)

TARGET = pathlib.Path(__file__).parent / "fixtures" / "deploy_target"
BASE_URL = "http://localhost:18080"

pytestmark = [
    pytest.mark.docker,
    pytest.mark.asyncio,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH"),
]


def _cfg() -> DeployConfig:
    return DeployConfig(adapter="compose", base_url=BASE_URL, readiness_timeout_s=90)


def _plan(version: str) -> DeployPlan:
    return DeployPlan(
        environment="staging",
        version=version,
        smoke_checks=[
            SmokeCheck(name="health", kind="http", path="/health", expect_status=200, timeout_s=10)
        ],
    )


def _serving_version() -> str:
    with urllib.request.urlopen(f"{BASE_URL}/health", timeout=10) as r:
        return json.load(r)["version"]


@pytest.fixture
def compose_down():
    yield
    subprocess.run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=TARGET,
        check=False,
        capture_output=True,
    )


async def test_deploy_smoke_and_real_rollback(compose_down, monkeypatch):
    """Ship v1 (healthy), ship v2 (broken), roll back, assert v1 serves."""
    cfg, repo = _cfg(), str(TARGET)

    # --- v1: a good deploy passes its smoke check -------------------------
    await deploy_apply(DeployActivityInput(plan=_plan("v1"), cfg=cfg, repo_path=repo))
    out = await smoke_check(
        SmokeCheckInput(plan=_plan("v1"), cfg=cfg, repo_path=repo, endpoint=BASE_URL)
    )
    assert [r.state for r in out.results] == [SmokeState.PASSED]
    assert _serving_version() == "v1"

    # --- the adapter can now see what is running --------------------------
    current = await deploy_current_version(
        DeployActivityInput(plan=_plan("v2"), cfg=cfg, repo_path=repo)
    )
    assert current.version is not None

    # --- v2: builds fine, fails its smoke check ---------------------------
    monkeypatch.setenv("HEALTHY", "0")
    await deploy_apply(DeployActivityInput(plan=_plan("v2"), cfg=cfg, repo_path=repo))
    out = await smoke_check(
        SmokeCheckInput(plan=_plan("v2"), cfg=cfg, repo_path=repo, endpoint=BASE_URL)
    )
    assert out.results[0].state is SmokeState.FAILED

    # --- rollback restores the prior version, observably ------------------
    monkeypatch.setenv("HEALTHY", "1")
    await deploy_rollback(RollbackInput(plan=_plan("v2"), cfg=cfg, repo_path=repo, to_version="v1"))
    assert _serving_version() == "v1"


async def test_unreachable_service_errors_rather_than_passing(compose_down):
    """Nothing is running: every http check must be ERRORED, never PASSED."""
    cfg = DeployConfig(adapter="compose", base_url="http://localhost:18081", readiness_timeout_s=2)
    out = await smoke_check(
        SmokeCheckInput(
            plan=_plan("v1"), cfg=cfg, repo_path=str(TARGET), endpoint="http://localhost:18081"
        )
    )
    assert out.results[0].state is SmokeState.ERRORED
