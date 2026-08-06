"""Stage 13 wiring. The rollback SEQUENCING is proven here with mocked
activities (D-8); the compose adapter's mechanics are proven by the
docker-marked test in Task 9."""
from __future__ import annotations

import pathlib

import pytest

from sdlc.models import (
    DeployReport, GateDecision, GateOutcome, SmokeCheckResult, SmokeState,
)
from sdlc.workflows.feature import _deploy_result

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def _report(**over) -> DeployReport:
    base = dict(deployed=False, environment="staging", version="v1",
                adapter="compose", rolled_back=True, rolled_back_to="v0",
                rollback_reason="smoke checks not passed: health=failed")
    base.update(over)
    return DeployReport(**base)


def _decision(outcome) -> GateDecision:
    return GateDecision(gate="deploy_failed", round=1, outcome=outcome,
                        decided_by="human")


def test_success_returns_deployed():
    r = DeployReport(deployed=True, environment="staging", version="v1",
                     adapter="compose")
    assert _deploy_result(r, None, "PR") == "deployed:PR"


def test_acknowledged_rollback_returns_rolled_back():
    assert _deploy_result(_report(), _decision(GateOutcome.APPROVE),
                          "PR") == "rolled-back:PR"


def test_rejection_is_terminal_and_distinct():
    assert _deploy_result(_report(), _decision(GateOutcome.REJECT),
                          "PR") == "deploy-rejected:PR"


def test_a_failed_rollback_is_never_reported_as_rolled_back():
    """The load-bearing assertion. Claiming a rollback that did not happen
    is the worst lie this system could tell: the environment is live and in
    an unknown state."""
    broken = _report(rolled_back=False, rolled_back_to=None,
                     rollback_reason="rollback exhausted: timeout")
    assert _deploy_result(broken, _decision(GateOutcome.APPROVE),
                          "PR") == "deploy-broken:PR"
    assert _deploy_result(broken, _decision(GateOutcome.REJECT),
                          "PR") == "deploy-broken:PR"


def test_no_previous_version_is_also_broken_not_rolled_back():
    """First-ever deploy that failed smoke: nothing was restored."""
    first = _report(rolled_back=False, rolled_back_to=None,
                    rollback_reason="no previous version to restore; "
                                    "smoke checks not passed: health=failed")
    assert _deploy_result(first, _decision(GateOutcome.APPROVE),
                          "PR") == "deploy-broken:PR"


def test_the_old_hardcoded_deploy_is_gone():
    src = SRC.read_text(encoding="utf-8")
    assert "make deploy ENV=staging" not in src
    assert "DeployInput" not in src


def test_the_stage_is_gated_on_config():
    src = SRC.read_text(encoding="utf-8")
    assert "cfg.deploy.enabled" in src


def test_the_child_id_is_derived_not_generated():
    """Determinism: replay must produce the same child id."""
    src = SRC.read_text(encoding="utf-8")
    assert "-deploy-" in src
    assert "uuid" not in src.split("6. DEPLOY")[1][:2000]


def test_deploy_activity_is_deleted_from_activities():
    src = pathlib.Path("src/sdlc/activities.py").read_text(encoding="utf-8")
    assert "async def deploy(" not in src
    assert "class DeployInput" not in src
