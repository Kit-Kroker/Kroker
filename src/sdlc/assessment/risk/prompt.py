"""Bounded, deterministic rendering of the baseline for the risk proposer.

Pure by design -- see the package docstring in models.py.

Named in RULE_MODULES (P2-D7): the renderer decides what the model sees, so
editing it moves a stored map exactly as editing a weight does. E-46's D10
records what it costs to find that out late.

Every value here is one code already computed. The proposer is shown the
score so it can judge the rows underneath it -- never so it can restate it.
"""
from __future__ import annotations

from ..discover.map import CapabilityMap
from .models import UnifiedRiskMap

MAX_VULNERABILITIES = 30


def render_risk_prompt(cmap: CapabilityMap, baseline: UnifiedRiskMap, *,
                       max_vulnerabilities: int = MAX_VULNERABILITIES) -> str:
    """One section per capability, in the baseline's own (sorted) order.

    An uncollected control or criticality renders its REASON rather than a
    state, so RD5's two sourceless families cannot be read as findings.
    """
    names = {c.bc_id: c.name for c in cmap.capabilities}
    lines: list[str] = [
        f"# Capability Risk Baseline ({len(baseline.capabilities)})",
        "",
    ]
    for cap in baseline.capabilities:
        crit = (cap.criticality.level.value
                if cap.criticality.level is not None
                else f"(not collected: {cap.criticality.collected.reason})")
        lines.append(f"## {cap.bc_id}: {names.get(cap.bc_id, '(unnamed)')}")
        lines.append(f"- Criticality: {crit}")
        lines.append("- Controls:")
        for control in cap.controls:
            state = (control.state.value if control.state is not None
                     else f"(not collected: {control.collected.reason})")
            lines.append(f"  - {control.family.value}: {state}")
        lines.append(f"- Vulnerabilities ({len(cap.vulnerabilities)}):")
        for v in cap.vulnerabilities[:max_vulnerabilities]:
            loc = f"{v.path}:{v.line}" if v.line else v.path
            lines.append(f"  - [{v.key}] severity={v.severity.value} "
                         f"class={v.classification.value} at {loc}")
        if len(cap.vulnerabilities) > max_vulnerabilities:
            lines.append(
                f"  \u2026 {len(cap.vulnerabilities) - max_vulnerabilities} more "
                f"vulnerability row(s) not shown")
        lines.append("")

    return "\n".join(lines)
