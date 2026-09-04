import pytest
from pydantic import ValidationError

from sdlc.core.models import (
    GateConfig,
    GatePolicy,
    PipelineConfig,
)
from sdlc.stages.architecture.models import ArchitectureSpec
from sdlc.stages.plan.models import ImplementationPlan


def test_gate_config_defaults():
    gc = GateConfig()
    assert gc.policy == GatePolicy.HARD
    assert gc.threshold == 0.8


def test_gate_config_threshold_bounds():
    with pytest.raises(ValidationError):
        GateConfig(threshold=1.5)
    with pytest.raises(ValidationError):
        GateConfig(threshold=-0.1)


def test_pipeline_config_coerces_bare_gate_policy():
    """Backward compatibility: existing call sites and tests construct
    gates={"architecture": GatePolicy.HARD} — this must keep working
    after `gates` becomes dict[str, GateConfig]."""
    cfg = PipelineConfig(gates={"architecture": GatePolicy.HARD})
    assert isinstance(cfg.gates["architecture"], GateConfig)
    assert cfg.gates["architecture"].policy == GatePolicy.HARD
    assert cfg.gates["architecture"].threshold == 0.8  # default


def test_pipeline_config_default_gates_are_gate_config():
    cfg = PipelineConfig()
    assert isinstance(cfg.gates["plan"], GateConfig)
    assert cfg.gates["plan"].policy == GatePolicy.SOFT


def test_architecture_spec_confidence_defaults_to_none():
    spec = ArchitectureSpec(overview="x", decisions=[])
    assert spec.confidence is None


def test_implementation_plan_confidence_defaults_to_none():
    plan = ImplementationPlan(tasks=[])
    assert plan.confidence is None
