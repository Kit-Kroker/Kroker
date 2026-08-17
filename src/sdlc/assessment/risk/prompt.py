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
from ...measurement import CollectionState
from .models import UnifiedRiskMap

MAX_VULNERABILITIES = 30
MAX_BOUNDARIES = 20
MAX_CHAINS = 10
MAX_SHARED = 10
MAX_CASCADES = 10


def _family(lines: list[str], title: str, collected, rows, cap: int,
            render) -> None:
    """One family, or the reason it is not one.

    An uncollected family renders its REASON rather than an empty list: a
    proposer shown "Cascades (0)" would reasonably read "nothing propagates",
    which is the claim FR-915 forbids the artifact from making.
    """
    if collected.state is not CollectionState.MEASURED:
        lines.append(f"## {title}: (not collected: {collected.reason})")
        lines.append("")
        return
    lines.append(f"## {title} ({len(rows)})")
    for row in rows[:cap]:
        lines.append(f"  - {render(row)}")
    if len(rows) > cap:
        lines.append(f"  … {len(rows) - cap} more not shown")
    lines.append("")


def _system_section(system) -> list[str]:
    lines: list[str] = ["# System View", ""]
    _family(lines, "Shared weaknesses",
            system.shared_vulnerabilities_collected,
            system.shared_vulnerabilities, MAX_SHARED,
            lambda r: (f"[{r.weakness_class}] severity={r.severity.value} "
                       f"in {', '.join(r.bc_ids)}"))
    _family(lines, "Cascades", system.cascades_collected, system.cascades,
            MAX_CASCADES, lambda c: " -> ".join(c.path))
    _family(lines, "Trust boundary candidates", system.trust_boundaries_collected,
            system.trust_boundaries, MAX_BOUNDARIES,
            lambda b: (f"{b.source_bc_id} -> {b.target_bc_id} "
                       f"(rule={b.rule})"))
    _family(lines, "Escalation chain candidates",
            system.escalation_paths_collected, system.escalation_paths,
            MAX_CHAINS, lambda p: f"{p.path_id} (rule={p.rule})")
    if system.truncated:
        lines.append(
            f"NOTE: {', '.join(system.truncated)} hit their enumeration cap "
            f"and are incomplete.")
        lines.append("")
    return lines


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
                f"  … {len(cap.vulnerabilities) - max_vulnerabilities} more "
                f"vulnerability row(s) not shown")
        lines.append("")

    lines.extend(_system_section(baseline.system))
    return "\n".join(lines)
