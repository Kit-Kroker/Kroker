"""E-9 Task 1: per-gate timeout semantics. Only `merge` changes default
behaviour; every other gate keeps today's reject."""
from __future__ import annotations

from sdlc.models import GateConfig, GatePolicy, PipelineConfig, TimeoutAction


def test_default_on_timeout_is_reject():
    """Preserves today's behaviour for any gate that does not opt out."""
    assert GateConfig().on_timeout is TimeoutAction.REJECT


def test_timer_overrides_default_to_none():
    cfg = GateConfig()
    assert cfg.remind_after_hours is None
    assert cfg.escalate_after_hours is None


def test_merge_defaults_to_hold_every_other_gate_rejects():
    gates = PipelineConfig().gates
    assert gates["merge"].on_timeout is TimeoutAction.HOLD
    for name in ("clarify", "architecture", "plan", "deploy"):
        assert gates[name].on_timeout is TimeoutAction.REJECT, name


def test_bare_policy_string_still_coerces():
    """GateConfig._coerce is unchanged: existing configs keep parsing and
    keep today's timeout behaviour."""
    cfg = PipelineConfig(gates={"architecture": "hard"})
    assert cfg.gates["architecture"].policy is GatePolicy.HARD
    assert cfg.gates["architecture"].on_timeout is TimeoutAction.REJECT


def test_overrides_round_trip_through_dict_coercion():
    cfg = PipelineConfig(gates={
        "merge": {"policy": "hard", "on_timeout": "approve",
                  "remind_after_hours": 4, "escalate_after_hours": 8},
    })
    g = cfg.gates["merge"]
    assert g.on_timeout is TimeoutAction.APPROVE
    assert (g.remind_after_hours, g.escalate_after_hours) == (4, 8)
