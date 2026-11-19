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
from .models import MaintenanceConfig, RepairAction, RepairPlan, RiskClass


def _require_name(name: str) -> str:
    """Fail closed on a non-string name: a normalised or coerced key would
    silently detach the gate from the incident that asked for it."""
    if not isinstance(name, str):
        raise TypeError(
            f"gate name must be a str (the exact key _gate looks up), got {type(name).__name__}"
        )
    return name


def repair_gate_settings(cfg: MaintenanceConfig, name: str, *, human_only: bool) -> GateSettings:
    """The repair-plan gate: SOFT at the configured threshold, REJECT on
    timeout. SOFT means an above-threshold effective confidence may be
    recorded approved by policy (``decided_by="policy"``); a timeout is
    always inaction. ``human_only`` (023b R6: every refusal round) builds
    the gate HARD — policy can never resolve it, whatever the confidence,
    so a refused plan cannot be re-approved without a human."""
    return GateSettings(
        gates={
            _require_name(name): GateConfig(
                policy=GatePolicy.HARD if human_only else GatePolicy.SOFT,
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


def risk_class(action: RepairAction) -> RiskClass | None:
    """The FR-502 class of one action, or None when confidence governs.

    Fail closed (FR-502 Review Focus 2): every ``kind == "ops"`` action is
    HUMAN_REQUIRED regardless of ``ops_action`` — a None verb (the model
    has no validator demanding one) classes as needing a human too; the
    verb never lowers the class. A ``code_fix`` has no class: its gate
    stays the confidence threshold, exactly as before FR-502. Pure — no
    confidence is read here; classification and confidence compose only in
    the gate conjunct."""
    if action.kind == "ops":
        return RiskClass.HUMAN_REQUIRED
    return None


def bears_human_required(plan: RepairPlan) -> bool:
    """Whether the plan carries any action a human must approve (FR-502).

    True iff any action classes (i.e. any ops action — the verb is
    irrelevant); an empty or all-``code_fix`` plan is False and keeps the
    confidence gate it always had."""
    return any(risk_class(a) is not None for a in plan.actions)
