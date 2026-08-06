"""Fake deploy activities. The workflow's sequencing is what these exercise;
the real adapter mechanics are proven by the docker-marked integration test.

Behaviour is driven by module-level state so a test can script a run without
threading config through FeatureWorkflow's whole call chain."""
from __future__ import annotations

from dataclasses import dataclass, field

from temporalio import activity

from sdlc.deploy.activities import (
    ApplyResult, CurrentVersionResult, DeployActivityInput, RollbackInput,
    SmokeCheckInput, SmokeCheckOutput,
)
from sdlc.models import SmokeCheckResult, SmokeState


@dataclass
class DeployScript:
    """What the fakes should do. `smoke_states` is consumed one entry per
    apply, so a REVISE retry can succeed where attempt 1 failed."""
    previous_version: str | None = "v0"
    apply_fails: bool = False
    rollback_fails: bool = False
    smoke_states: list[SmokeState] = field(
        default_factory=lambda: [SmokeState.PASSED])
    applies: int = 0
    rollbacks: int = 0


SCRIPT = DeployScript()


def reset(**over) -> DeployScript:
    global SCRIPT
    SCRIPT = DeployScript(**over)
    return SCRIPT


@activity.defn(name="deploy_current_version")
async def fake_current_version(inp: DeployActivityInput) -> CurrentVersionResult:
    return CurrentVersionResult(version=SCRIPT.previous_version)


@activity.defn(name="deploy_apply")
async def fake_apply(inp: DeployActivityInput) -> ApplyResult:
    SCRIPT.applies += 1
    if SCRIPT.apply_fails:
        raise RuntimeError("deploy failed (1): fake")
    return ApplyResult(endpoint="http://fake")


@activity.defn(name="smoke_check")
async def fake_smoke(inp: SmokeCheckInput) -> SmokeCheckOutput:
    idx = min(SCRIPT.applies - 1, len(SCRIPT.smoke_states) - 1)
    state = SCRIPT.smoke_states[idx]
    return SmokeCheckOutput(results=[SmokeCheckResult(
        name="liveness", state=state,
        detail="" if state is SmokeState.PASSED else f"fake {state.value}")])


@activity.defn(name="deploy_rollback")
async def fake_rollback(inp: RollbackInput) -> None:
    SCRIPT.rollbacks += 1
    if SCRIPT.rollback_fails:
        raise RuntimeError("rollback failed (1): fake")


DEPLOY_FAKES = [fake_current_version, fake_apply, fake_smoke, fake_rollback]
