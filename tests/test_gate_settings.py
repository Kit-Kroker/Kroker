"""E-42 D3: the three fields a durable HITL gate reads, extracted so GateHost
does not depend on the feature pipeline's PipelineConfig."""

from __future__ import annotations

from sdlc.core.models import (
    GateConfig,
    GatePolicy,
    GateSettings,
    PipelineConfig,
)


def test_gate_settings_defaults_are_conservative():
    s = GateSettings()
    assert s.gates == {}
    assert s.default_gate_policy is GatePolicy.HARD
    assert s.gate_timeout_hours == 48


def test_pipeline_config_projects_its_three_gate_fields():
    cfg = PipelineConfig()
    s = cfg.gate_settings()
    assert s.gates == cfg.gates
    assert s.default_gate_policy is cfg.default_gate_policy
    assert s.gate_timeout_hours == cfg.gate_timeout_hours


def test_projection_does_not_alias_the_config_dict():
    """A workflow handed GateSettings must not be able to mutate the config
    it was projected from."""
    cfg = PipelineConfig()
    s = cfg.gate_settings()
    s.gates["invented"] = GateConfig(policy=GatePolicy.OFF)
    assert "invented" not in cfg.gates


def test_unnamed_gate_falls_back_to_default_policy():
    """TriageInput ships an empty GateSettings, so `readiness` is unnamed and
    must resolve to HARD (spec section 7)."""
    s = GateSettings()
    assert s.gates.get("readiness") is None
    assert s.default_gate_policy is GatePolicy.HARD
