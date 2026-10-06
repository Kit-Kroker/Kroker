"""The one run-budget validation and its start notice (011, US2).

Shared by the CLI flag and the dashboard start request (R3: one rule, two
entry points); a budget of 0 is OFF and means "absent" everywhere else, so
an EXPLICIT zero is rejected here with the hint instead of silently
disabling the gate (R7). This module is client code: it is never imported
by a workflow module (plan constitution check) and imports the registry
catalog the same way the dashboard already does.
"""

from __future__ import annotations

import math

from .core.models import PipelineConfig
from .pricing import PriceUsageInput, compute_price
from .workflows.graph_catalog import resolved_roles

BUDGET_ZERO_HINT = "budget must be greater than 0; omit it to run without a budget"
BUDGET_SCOPE_NOTE = (
    "counts priced planning-agent spend only. "
    "Coding-harness, crew and research-stage spend is not counted."
)

_NOT_A_NUMBER = "budget must be a number greater than 0"

# The planning roles _run_role serves in this tree, pinned from
# agents/roles.py STAGE_ROLES values (recorded in the 011 baseline). The
# harness roles (dev, test, devops) are never planning roles; the notice's
# probe lists only these.
PLANNING_ROLES = frozenset(
    {
        "clarify",
        "architect",
        "planner",
        "devops_planner",
        "reviewer",
        "analyst",
        "qa",
        "merge_verdict",
        "research",
        "deep_review",
        "handoff",
        "adversary",
        "discover",
        "risk",
    }
)


def parse_run_budget(raw: object) -> float:
    """Parse a budget request into dollars. Raises ValueError with a
    message ready to show; bool is rejected before the int check (bool is
    an int subclass), strings are stripped, and NaN/inf/negative/zero each
    carry their own message (zero: BUDGET_ZERO_HINT, R7)."""
    if isinstance(raw, bool):
        raise ValueError(_NOT_A_NUMBER)
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw.strip())
        except ValueError:
            raise ValueError(_NOT_A_NUMBER) from None
    else:
        raise ValueError(_NOT_A_NUMBER)
    if math.isnan(value) or math.isinf(value) or value < 0:
        raise ValueError(_NOT_A_NUMBER)
    if value == 0:
        raise ValueError(BUDGET_ZERO_HINT)
    return value


def budget_notice(cfg: PipelineConfig) -> str | None:
    """The FR-009 notice: None without a budget, else the fixed scope
    sentence plus, when the probe finds planning roles whose model has no
    known price, the roles that will not count. The probe says only what is
    missing, never "all priced"."""
    if cfg.run_budget_usd <= 0:
        return None
    text = f"Budget ${cfg.run_budget_usd:.2f} {BUDGET_SCOPE_NOTE}"
    unpriced = sorted(
        role
        for role in PLANNING_ROLES
        if (rc := resolved_roles(cfg).get(role)) is not None
        and rc.model is not None
        and compute_price(PriceUsageInput(model=rc.model, input_tokens=1)) is None
    )
    if unpriced:
        text += f" No price found for: {', '.join(unpriced)}."
    return text
