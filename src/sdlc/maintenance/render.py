"""The human-facing renders (023a T016): the gate context text and the
CLI incidents table (contracts/cli.md).
"""

from __future__ import annotations

from .models import TERMINAL_INCIDENT_STATES, Incident, IncidentState

NO_EXECUTE_LINE = "approval does NOT execute in 023a — an approved plan is recorded, nothing runs"

_HEADER = f"{'INC-n':<8}  {'state':<22}  {'key':<44}  {'seen':>4}  {'eff.conf':>8}  gate"


def _conf(incident: Incident) -> str:
    if incident.plan is None:
        return "-"
    return f"{incident.plan.effective:.2f}"


def _gate(incident: Incident) -> str:
    name = (
        f"detect_escalation:{incident.key.split(':')[0]}:{incident.no}"
        if incident.kind == "detect_escalation"
        else f"repair:{incident.no}"
    )
    if incident.decision is not None:
        return f"{name}:{incident.decision.outcome.value}"
    if incident.state is IncidentState.AWAITING_DECISION:
        return f"{name}:pending"
    return "-"


def gate_context_text(incident: Incident) -> str:
    """The GateContext body for a repair gate: the incident, the plan, the
    three confidences, and the line that keeps 'approved' honest (FR-012)."""
    lines = [f"INC-{incident.no}  {incident.key}", f"state: {incident.state.value}"]
    if incident.plan is None:
        lines.append("plan: no action proposed")
    else:
        p = incident.plan
        lines += [
            f"plan: {len(p.actions)} action(s) — {p.analysis[:400]}",
            f"confidence: floor {p.floor:.2f} / self {p.self_confidence:.2f} "
            f"/ effective {p.effective:.2f}",
            f"author: {p.author_model}",
        ]
    lines.append(NO_EXECUTE_LINE)
    return "\n".join(lines)


def incidents_table(incidents: list[Incident], *, include_terminal: bool = False) -> str:
    """The `sdlc maintain incidents` table: INC-n  state  key  seen
    eff.conf  gate. Terminal incidents only under --all (contracts/cli.md)."""
    rows = [
        f"INC-{i.no:<7}  {i.state.value:<22}  {i.key:<44.44}  {i.seen_count:>4}  "
        f"{_conf(i):>8}  {_gate(i)}"
        for i in incidents
        if include_terminal or i.state not in TERMINAL_INCIDENT_STATES
    ]
    if not rows:
        return _HEADER + "\n(no incidents)"
    return "\n".join([_HEADER, *rows])
