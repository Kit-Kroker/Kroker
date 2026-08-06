"""E-67/FR-1104: the deploy contract. A smoke result that was never
observed must not be representable as a pass, and a failed deploy must
account for what happened to the rollback."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.models import (
    DeployPlan, DeployReport, FeatureFlag, RollbackPolicy, SmokeCheck,
    SmokeCheckResult, SmokeState,
)


def _plan(**over) -> DeployPlan:
    base = dict(environment="staging", version="v1",
                smoke_checks=[SmokeCheck(name="health", kind="http",
                                         path="/health")])
    base.update(over)
    return DeployPlan(**base)


def test_plan_is_frozen_by_default():
    """Same default as ValidationContract.frozen -- the plan gate freezes it."""
    assert _plan().frozen is True


def test_plan_defaults_to_auto_rollback():
    assert _plan().rollback == RollbackPolicy(auto=True, to="previous")


def test_plan_has_no_adapter_field():
    """FR-1105/D-1: the operator picks the adapter, not the planner."""
    assert "adapter" not in DeployPlan.model_fields


def test_http_check_requires_a_path():
    with pytest.raises(ValidationError):
        SmokeCheck(name="health", kind="http", path="")


def test_command_check_requires_a_command():
    with pytest.raises(ValidationError):
        SmokeCheck(name="migrated", kind="command", command="")


def test_passed_result_needs_no_detail():
    assert SmokeCheckResult(name="health", state=SmokeState.PASSED).passed


@pytest.mark.parametrize("state", [SmokeState.FAILED, SmokeState.ERRORED])
def test_non_passing_result_must_explain_itself(state):
    """Mirrors Measurement: a missing observation carries its reason."""
    with pytest.raises(ValidationError):
        SmokeCheckResult(name="health", state=state, detail="   ")


def test_errored_is_not_passed():
    """D-3: 'we could not reach it' is not 'it works'."""
    r = SmokeCheckResult(name="health", state=SmokeState.ERRORED,
                         detail="connection refused")
    assert r.passed is False


def _report(**over) -> DeployReport:
    base = dict(deployed=True, environment="staging", version="v1",
                adapter="compose")
    base.update(over)
    return DeployReport(**base)


def test_rolled_back_requires_a_target():
    with pytest.raises(ValidationError):
        _report(deployed=False, rolled_back=True, rolled_back_to=None)


def test_failed_deploy_without_rollback_must_say_why():
    with pytest.raises(ValidationError):
        _report(deployed=False, rolled_back=False, rollback_reason="")


def test_failed_deploy_with_no_previous_version_is_representable():
    """First-ever deploy: nothing to restore, and the report says so."""
    r = _report(deployed=False, rolled_back=False,
                rollback_reason="no previous version to restore")
    assert r.rolled_back is False


def test_flag_is_recorded_not_managed():
    """NG7: name + cohort, nothing else -- we do not build flagging."""
    assert set(FeatureFlag.model_fields) == {"name", "cohort"}
