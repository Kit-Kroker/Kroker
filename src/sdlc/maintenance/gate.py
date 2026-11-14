"""The code-built maintenance gates (023a T007, R9).

Pure by design (see AGENTS.md in this directory): no I/O, no Temporal,
no config surface. The ONLY way "no configuration can open the repair
gate" (FR-011/SC-003) is true is that no configuration reaches it —
``MaintenanceConfig`` has no gate fields, and these builders hard-code
everything except the two bounded knobs they read (``threshold`` and
``gate_timeout_hours``).

Because ``GateHost._gate`` looks gate names up in ``settings.gates``
EXACTLY, each builder takes the per-incident gate name and returns a
settings dict keyed by that name alone.
"""

from __future__ import annotations

from ..core.models import GateConfig, GatePolicy, GateSettings, TimeoutAction
from .models import MaintenanceConfig


def _require_name(name: str) -> str:
    """Fail closed on a non-string name: a normalised or coerced key would
    silently detach the gate from the incident that asked for it."""
    if not isinstance(name, str):
        raise TypeError(
            f"gate name must be a str (the exact key _gate looks up), got {type(name).__name__}"
        )
    return name


def repair_gate_settings(cfg: MaintenanceConfig, name: str) -> GateSettings:
    """The repair-plan gate: SOFT at the configured threshold, REJECT on
    timeout. SOFT means an above-threshold effective confidence may be
    recorded approved by policy (``decided_by="policy"``); a timeout is
    always inaction."""
    return GateSettings(
        gates={
            _require_name(name): GateConfig(
                policy=GatePolicy.SOFT,
                threshold=cfg.threshold,
                on_timeout=TimeoutAction.REJECT,
            )
        },
        default_gate_policy=GatePolicy.HARD,
        gate_timeout_hours=cfg.gate_timeout_hours,
    )


def escalation_gate_settings(cfg: MaintenanceConfig, name: str) -> GateSettings:
    """The detect-escalation gate (a signal not collected two cycles
    running): HARD — only a human closes it — and REJECT on timeout."""
    return GateSettings(
        gates={
            _require_name(name): GateConfig(
                policy=GatePolicy.HARD,
                on_timeout=TimeoutAction.REJECT,
            )
        },
        default_gate_policy=GatePolicy.HARD,
        gate_timeout_hours=cfg.gate_timeout_hours,
    )
