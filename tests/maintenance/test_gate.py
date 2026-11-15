"""Chaos and edge-case contracts for the code-built repair gate (023a T006, RED).

Subject: ``sdlc.maintenance.gate`` (does not exist yet; T007 implements it).
Authoritative contract: ``.specify/specs/023-daper-maintenance-loop/tasks.md`` T006,
``research.md`` R9 and ``data-model.md``.

This is the chaos/edge half. The happy-path half is added to this same file
by qa-happy. The invariant under test: no ``MaintenanceConfig`` combination,
and no gate name, can produce a gate that is OFF, that approves on timeout, or
that holds forever. The repair gate is SOFT and the escalation gate is HARD,
and both reject on timeout.
"""

from __future__ import annotations

import itertools
import socket
from typing import Any

import pytest

from sdlc.core.models import GateConfig, GatePolicy, GateSettings, TimeoutAction
from sdlc.maintenance.gate import escalation_gate_settings, repair_gate_settings
from sdlc.maintenance.models import MaintenanceConfig

REPO_DIR = "/srv/example-repo"

# Every valid corner of the registration surface (data-model.md §MaintenanceConfig).
THRESHOLD_CORNERS = (0.5, 1.0)
TIMEOUT_CORNERS = (1, 168)
BUILD_PROBE_CORNERS = (True, False)
ADVISORY_CORNERS = ("none", "osv")

CORNERS = list(
    itertools.product(THRESHOLD_CORNERS, TIMEOUT_CORNERS, BUILD_PROBE_CORNERS, ADVISORY_CORNERS)
)


def _cfg(
    *,
    threshold: float = 0.8,
    gate_timeout_hours: int = 48,
    build_probe: bool = True,
    advisory_source: str = "none",
) -> MaintenanceConfig:
    """Build a valid config. ``build_probe=True`` needs the unattended ack (R14)."""
    return MaintenanceConfig(
        project="example-app",
        repo_dir=REPO_DIR,
        build_probe=build_probe,
        ack_unattended_build_probe=build_probe,
        advisory_source=advisory_source,
        threshold=threshold,
        gate_timeout_hours=gate_timeout_hours,
    )


def _corner_cfg(corner: tuple[float, int, bool, str]) -> MaintenanceConfig:
    threshold, timeout, build_probe, advisory = corner
    return _cfg(
        threshold=threshold,
        gate_timeout_hours=timeout,
        build_probe=build_probe,
        advisory_source=advisory,
    )


def _corner_id(corner: tuple[float, int, bool, str]) -> str:
    threshold, timeout, build_probe, advisory = corner
    return f"thr={threshold}-timeout={timeout}-probe={build_probe}-advisory={advisory}"


# --------------------------------------------------------------------------- #
# repair_gate_settings: exact shape, exact name
# --------------------------------------------------------------------------- #


def test_repair_gate_is_soft_reject_at_the_configured_threshold_under_exact_name() -> None:
    cfg = _cfg(threshold=0.65)

    settings = repair_gate_settings(cfg, "repair:3")

    assert isinstance(settings, GateSettings)
    assert settings.gates == {
        "repair:3": GateConfig(
            policy=GatePolicy.SOFT,
            threshold=0.65,
            on_timeout=TimeoutAction.REJECT,
        )
    }
    assert settings.gate_timeout_hours == cfg.gate_timeout_hours


@pytest.mark.parametrize("name", ["repair:1", "repair:10", "repair:999"])
def test_repair_gate_has_exactly_one_key_equal_to_the_name_passed(name: str) -> None:
    settings = repair_gate_settings(_cfg(), name)

    assert list(settings.gates) == [name]


@pytest.mark.parametrize(
    "name",
    [
        " repair:3",  # leading whitespace: the lookup is exact, so no stripping
        "repair:3 ",  # trailing whitespace
        "Repair:3",  # case: no lowercasing
        "REPAIR:3",
        "repair:٣",  # a non-ASCII digit must stay as given
    ],
)
def test_repair_gate_key_is_never_normalised(name: str) -> None:
    # `_gate` looks names up exactly. A normalised key would silently detach
    # the gate from the incident that asked for it.
    settings = repair_gate_settings(_cfg(), name)

    assert list(settings.gates) == [name]


def test_repair_gate_default_fallback_policy_is_never_off() -> None:
    # A gate whose name is not in `gates` falls back to default_gate_policy.
    # That fallback must not be OFF.
    settings = repair_gate_settings(_cfg(), "repair:3")

    assert settings.default_gate_policy in {GatePolicy.SOFT, GatePolicy.HARD}


# --------------------------------------------------------------------------- #
# escalation_gate_settings: HARD + REJECT, same timeout
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name",
    ["escalation:build_probe:not_collected", "escalation:secrets", "escalation:9"],
)
def test_escalation_gate_is_hard_reject_under_exact_name(name: str) -> None:
    cfg = _cfg(gate_timeout_hours=12)

    settings = escalation_gate_settings(cfg, name)

    assert isinstance(settings, GateSettings)
    assert settings.gates == {
        name: GateConfig(policy=GatePolicy.HARD, on_timeout=TimeoutAction.REJECT)
    }
    assert settings.gate_timeout_hours == 12


def test_escalation_gate_default_fallback_policy_is_never_off() -> None:
    settings = escalation_gate_settings(_cfg(), "escalation:secrets")

    assert settings.default_gate_policy in {GatePolicy.SOFT, GatePolicy.HARD}


# --------------------------------------------------------------------------- #
# Corner sweep: no valid config can reach OFF, APPROVE or HOLD
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("corner", CORNERS, ids=_corner_id)
def test_repair_gate_at_every_corner_is_soft_and_reject(
    corner: tuple[float, int, bool, str],
) -> None:
    cfg = _corner_cfg(corner)

    gate = repair_gate_settings(cfg, "repair:1").gates["repair:1"]

    assert gate.policy is GatePolicy.SOFT
    assert gate.on_timeout is TimeoutAction.REJECT
    assert gate.threshold == cfg.threshold


@pytest.mark.parametrize("corner", CORNERS, ids=_corner_id)
def test_escalation_gate_at_every_corner_is_hard_and_reject(
    corner: tuple[float, int, bool, str],
) -> None:
    cfg = _corner_cfg(corner)

    gate = escalation_gate_settings(cfg, "escalation:secrets").gates["escalation:secrets"]

    assert gate.policy is GatePolicy.HARD
    assert gate.on_timeout is TimeoutAction.REJECT


@pytest.mark.parametrize("corner", CORNERS, ids=_corner_id)
def test_no_corner_reaches_off_approve_or_hold_on_either_kind(
    corner: tuple[float, int, bool, str],
) -> None:
    cfg = _corner_cfg(corner)
    names = ["repair:1", "repair:2"]
    settings = [repair_gate_settings(cfg, n) for n in names]
    settings.append(escalation_gate_settings(cfg, "escalation:secrets"))

    policies = {gate.policy for s in settings for gate in s.gates.values()} | {
        s.default_gate_policy for s in settings
    }
    timeouts = {gate.on_timeout for s in settings for gate in s.gates.values()}

    assert policies <= {GatePolicy.SOFT, GatePolicy.HARD}
    assert timeouts == {TimeoutAction.REJECT}


def test_full_corner_sweep_reachable_policy_set_is_soft_and_hard_only() -> None:
    # Collect every policy and timeout reachable across the whole valid space,
    # not only per corner.
    policies: set[GatePolicy] = set()
    timeouts: set[TimeoutAction] = set()
    for corner in CORNERS:
        cfg = _corner_cfg(corner)
        for s in (
            repair_gate_settings(cfg, "repair:7"),
            escalation_gate_settings(cfg, "escalation:7"),
        ):
            for gate in s.gates.values():
                policies.add(gate.policy)
                timeouts.add(gate.on_timeout)

    assert policies == {GatePolicy.SOFT, GatePolicy.HARD}
    assert timeouts == {TimeoutAction.REJECT}


# --------------------------------------------------------------------------- #
# Purity and non-mutation
# --------------------------------------------------------------------------- #


def test_repair_gate_does_not_mutate_the_config_it_is_handed() -> None:
    cfg = _cfg(threshold=0.5, gate_timeout_hours=168)
    before: dict[str, Any] = cfg.model_dump()
    fields_set_before = set(cfg.model_fields_set)

    repair_gate_settings(cfg, "repair:3")

    assert cfg.model_dump() == before
    assert set(cfg.model_fields_set) == fields_set_before


def test_escalation_gate_does_not_mutate_the_config_it_is_handed() -> None:
    cfg = _cfg(threshold=1.0, gate_timeout_hours=1)
    before: dict[str, Any] = cfg.model_dump()

    escalation_gate_settings(cfg, "escalation:secrets")

    assert cfg.model_dump() == before


def test_repair_gate_is_pure_across_repeated_calls() -> None:
    cfg = _cfg()

    first = repair_gate_settings(cfg, "repair:3")
    second = repair_gate_settings(cfg, "repair:3")

    assert first == second
    assert first is not second  # fresh object each call, no shared mutable state


def test_equal_inputs_built_separately_give_equal_outputs() -> None:
    assert repair_gate_settings(_cfg(), "repair:3") == repair_gate_settings(_cfg(), "repair:3")
    assert escalation_gate_settings(_cfg(), "escalation:x") == (
        escalation_gate_settings(_cfg(), "escalation:x")
    )


def test_call_order_does_not_leak_state_between_gates() -> None:
    # Build a repair gate, then an escalation gate, then the repair gate again.
    # The repair result must be unchanged by the escalation call in between.
    cfg = _cfg()

    before = repair_gate_settings(cfg, "repair:3")
    escalation_gate_settings(cfg, "escalation:3")
    after = repair_gate_settings(cfg, "repair:3")

    assert before == after
    assert "escalation:3" not in after.gates


def test_gate_builders_perform_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    # gate.py is pure: no file, no socket, no subprocess. Any I/O fails loudly.
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("gate builder performed I/O")

    monkeypatch.setattr("builtins.open", _forbidden)
    monkeypatch.setattr(socket, "socket", _forbidden)

    repair_gate_settings(_cfg(), "repair:3")
    escalation_gate_settings(_cfg(), "escalation:3")


# --------------------------------------------------------------------------- #
# Invalid inputs
# --------------------------------------------------------------------------- #


def test_repair_gate_refuses_none_config() -> None:
    with pytest.raises((TypeError, AttributeError, ValueError)):
        repair_gate_settings(None, "repair:3")  # type: ignore[arg-type]


def test_escalation_gate_refuses_none_config() -> None:
    with pytest.raises((TypeError, AttributeError, ValueError)):
        escalation_gate_settings(None, "escalation:3")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_name", [None, 3, b"repair:3"])
def test_repair_gate_refuses_non_string_name(bad_name: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        repair_gate_settings(_cfg(), bad_name)


@pytest.mark.parametrize("bad_name", [None, 3, b"escalation:3"])
def test_escalation_gate_refuses_non_string_name(bad_name: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        escalation_gate_settings(_cfg(), bad_name)


def test_config_cannot_smuggle_gate_policy_into_the_builder() -> None:
    # The config model refuses gate fields outright (R9, extra="forbid"), so no
    # caller can hand the builder an OFF or APPROVE policy through it.
    with pytest.raises((TypeError, ValueError)):
        MaintenanceConfig(  # type: ignore[call-arg]
            project="example-app",
            repo_dir=REPO_DIR,
            build_probe=False,
            advisory_source="none",
            gates={"repair:3": {"policy": "off", "on_timeout": "approve"}},
        )


# =========================================================================== #
# Happy-path half (023a T006, qa-happy). Direct propagation pins only: the
# valid inputs, the exact shapes, and the threshold and timeout passing
# through. Corner sweeps and purity live in the chaos half above.
# =========================================================================== #


def test_happy_repair_gate_default_config_pins_soft_reject_at_0_8_under_repair_1() -> None:
    cfg = _cfg()  # defaults: threshold 0.8, timeout 48

    settings = repair_gate_settings(cfg, "repair:1")

    assert settings.gates == {
        "repair:1": GateConfig(
            policy=GatePolicy.SOFT,
            threshold=0.8,
            on_timeout=TimeoutAction.REJECT,
        )
    }
    assert settings.gate_timeout_hours == 48


@pytest.mark.parametrize("threshold", [0.5, 0.75, 1.0])
def test_happy_repair_gate_threshold_propagates_from_config(threshold: float) -> None:
    settings = repair_gate_settings(_cfg(threshold=threshold), "repair:1")

    assert settings.gates["repair:1"].threshold == threshold


@pytest.mark.parametrize("hours", [1, 24, 168])
def test_happy_repair_gate_timeout_propagates_from_config(hours: int) -> None:
    settings = repair_gate_settings(_cfg(gate_timeout_hours=hours), "repair:1")

    assert settings.gate_timeout_hours == hours


def test_happy_escalation_gate_pins_hard_reject_under_its_name() -> None:
    settings = escalation_gate_settings(_cfg(gate_timeout_hours=24), "escalation:secrets")

    assert settings.gates == {
        "escalation:secrets": GateConfig(
            policy=GatePolicy.HARD,
            on_timeout=TimeoutAction.REJECT,
        )
    }
    assert settings.gate_timeout_hours == 24


@pytest.mark.parametrize("hours", [1, 24, 168])
def test_happy_escalation_gate_timeout_propagates_from_config(hours: int) -> None:
    settings = escalation_gate_settings(
        _cfg(gate_timeout_hours=hours), "escalation:build_probe:not_collected"
    )

    assert settings.gate_timeout_hours == hours


def test_happy_shapes_hold_for_ack_build_probe_with_osv_advisory() -> None:
    cfg = _cfg(
        build_probe=True,
        advisory_source="osv",
        threshold=0.65,
        gate_timeout_hours=12,
    )

    repair = repair_gate_settings(cfg, "repair:2")
    escalation = escalation_gate_settings(cfg, "escalation:dependencies")

    assert repair.gates == {
        "repair:2": GateConfig(
            policy=GatePolicy.SOFT,
            threshold=0.65,
            on_timeout=TimeoutAction.REJECT,
        )
    }
    assert repair.gate_timeout_hours == 12
    assert escalation.gates == {
        "escalation:dependencies": GateConfig(
            policy=GatePolicy.HARD,
            on_timeout=TimeoutAction.REJECT,
        )
    }
    assert escalation.gate_timeout_hours == 12
