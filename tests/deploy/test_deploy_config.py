"""D-9: the deploy stage is opt-in. Nothing that exists today may start
shelling out to Docker when E-67 lands."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.core.models import (
    DeployConfig,
    PipelineConfig,
)


def test_deploy_is_disabled_by_default():
    assert PipelineConfig().deploy.enabled is False


def test_compose_is_the_default_adapter():
    """FR-1105 reference adapter."""
    assert PipelineConfig().deploy.adapter == "compose"


def test_unknown_adapter_is_rejected_at_the_boundary():
    with pytest.raises(ValidationError):
        DeployConfig(adapter="kubernetes")


def test_script_adapter_is_available():
    """D-7: a seam with one implementation ossifies into a substrate."""
    assert DeployConfig(adapter="script").adapter == "script"


def test_readiness_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        DeployConfig(readiness_timeout_s=0)


def test_config_round_trips_through_dicts():
    """PipelineConfig is constructed from dicts in benchmark cell config."""
    cfg = PipelineConfig(
        deploy={"enabled": True, "adapter": "script", "commands": {"deploy": "make ship"}}
    )
    assert cfg.deploy.enabled is True
    assert cfg.deploy.commands["deploy"] == "make ship"
