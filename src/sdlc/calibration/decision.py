"""C7: the single home of the SOFT-gate auto-approve rule.

FR-301 plus the C7 conjunct. Before C7 this rule existed twice --
workflows/role_host.py and stages/merge/step.py held logically identical
copies -- and audit row 8 found it UNPAIRED: a self-reported confidence at or
above threshold synthesized the APPROVE and the human wait never happened.

The `calibration` and `verdict` parameters are REQUIRED and have no
defaults. A default would make "no evidence was fetched" indistinguishable
from "the evidence passed", which is the same defect one layer up -- and
the deterministic verdict carries the same rule (ADR-24): a call with no
verdict is a call that skipped the conjunct.
"""

from __future__ import annotations

from ..core.models import (
    GateConfig,
    GateDecision,
    GateOutcome,
    GatePolicy,
    PipelineConfig,
)
from ..validators.verdicts import Verdict
from .models import CalibrationVerdict


def auto_decision_for(
    name: str,
    cfg: PipelineConfig,
    confidence: float | None,
    calibration: CalibrationVerdict,
    verdict: Verdict,
) -> GateDecision | None:
    """SOFT + confidence >= threshold + a calibrated bucket + a passing
    deterministic verdict -> an APPROVE decision _gate() can short-circuit
    on. Anything else -> None, falling through to the human wait.

    None confidence (missing/legacy artifact) never auto-approves, and neither
    does an `uncalibrated` or `insufficient_data` bucket -- all three are the
    same defensive stance: absent evidence is not passing evidence. The
    verdict conjunct (ADR-24) is the stance made deterministic: a vacuous
    verdict (no provider for this gate) passes -- that is architecture today
    -- but a provider that ran and failed never does; `ok` is the only field
    consulted."""
    gate_cfg = cfg.gates.get(name, GateConfig())
    if gate_cfg.policy != GatePolicy.SOFT or confidence is None:
        return None
    if confidence < gate_cfg.threshold:
        return None
    if calibration.verdict != "calibrated":
        return None
    if not verdict.ok:
        return None
    return GateDecision(
        gate=name,
        round=1,
        outcome=GateOutcome.APPROVE,
        decided_by="policy",
        comments=(
            f"auto-approved: confidence={confidence:.2f} "
            f">= threshold={gate_cfg.threshold:.2f}; "
            f"calibration={calibration.verdict} "
            f"(n={calibration.n}, agreement={calibration.agreement_rate:.2f})"
        ),
    )
