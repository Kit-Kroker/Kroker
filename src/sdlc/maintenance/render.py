"""The human-facing renders (023a T016, 023b T041): the gate context text, the
CLI incidents table (contracts/cli.md) and the retention text.
"""

from __future__ import annotations

from ..memory.models import MemoryKind
from .gate import risk_class
from .models import TERMINAL_INCIDENT_STATES, Incident, IncidentState

NO_EXECUTE_LINE = "approval does NOT execute in 023a — an approved plan is recorded, nothing runs"

_HEADER = (
    f"{'INC-n':<8}  {'state':<22}  {'key':<44}  {'seen':>4}  {'attempt':>7}  "
    f"{'reopens':>7}  {'eff.conf':>8}  gate  {'class':<44}  child"
)


def _conf(incident: Incident) -> str:
    if incident.plan is None:
        return "-"
    return f"{incident.plan.effective:.2f}"


def _child(incident: Incident) -> str:
    if incident.execution is None:
        return "-"
    return incident.execution.child_id


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


def _classed_verbs(incident: Incident) -> list[str]:
    """The classed actions' verbs (FR-502): plan order, deduplicated — two
    rollback actions render one ``rollback``."""
    verbs: list[str] = []
    if incident.plan is not None:
        for a in incident.plan.actions:
            if risk_class(a) is not None and a.ops_action not in verbs:
                verbs.append(str(a.ops_action))
    return verbs


def _classes(incident: Incident) -> str:
    """The class column (FR-502): one ``<verb>[<CLASS>]`` tag per classed
    action, comma-space-joined; ``-`` when there is no plan or no classed
    action — a pure ``code_fix`` plan keeps the confidence-governed render
    it always had."""
    if incident.plan is None:
        return "-"
    tags: list[str] = []
    for a in incident.plan.actions:
        cls = risk_class(a)
        if cls is not None:
            tags.append(f"{a.ops_action}[{cls.name}]")
    return ", ".join(tags) if tags else "-"


def gate_context_text(incident: Incident) -> str:
    """The GateContext body for a repair gate: the incident, the plan, the
    three confidences, the line that names the human-required ops when the
    plan bears any (FR-502), and the line that keeps 'approved' honest
    (FR-012)."""
    lines = [f"INC-{incident.no}  {incident.key}", f"state: {incident.state.value}"]
    if incident.plan is None or not incident.plan.actions:
        # FR-009's edge: a plan with zero actions is still gated, rendered
        # "no action proposed" — it never counts as resolved.
        lines.append("plan: no action proposed")
        if incident.plan is not None:
            lines.append(f"analysis: {incident.plan.analysis[:400]}")
    else:
        p = incident.plan
        lines += [
            f"plan: {len(p.actions)} action(s) — {p.analysis[:400]}",
            f"confidence: floor {p.floor:.2f} / self {p.self_confidence:.2f} "
            f"/ effective {p.effective:.2f}",
            f"author: {p.author_model}",
        ]
    verbs = _classed_verbs(incident)
    if verbs:
        lines.append(
            f"human-required ops: {', '.join(verbs)} — a human must decide; policy cannot approve"
        )
    lines.append(NO_EXECUTE_LINE)
    return "\n".join(lines)


def incidents_table(incidents: list[Incident], *, include_terminal: bool = False) -> str:
    """The `sdlc maintain incidents` table: INC-n  state  key  seen  attempt
    reopens  eff.conf  gate  class  child (023b adds attempt/reopens/child —
    the operator finds a verified incident's merge gate by its child id;
    FR-502 adds class — the ops risk class of the plan's actions, bounded
    like `key`). Terminal incidents only under --all (contracts/cli.md)."""
    rows = [
        f"INC-{i.no:<7}  {i.state.value:<22}  {i.key:<44.44}  {i.seen_count:>4}  "
        f"{i.attempt:>7}  {i.reopens:>7}  {_conf(i):>8}  {_gate(i)}  {_classes(i):<44.44}  "
        f"{_child(i)}"
        for i in incidents
        if include_terminal or i.state not in TERMINAL_INCIDENT_STATES
    ]
    if not rows:
        return _HEADER + "\n(no incidents)"
    return "\n".join([_HEADER, *rows])


#: The retention text bound (023b T041, R13): a memory document, not a report.
RETENTION_BOUND = 2000


def retention_kind(incident: Incident) -> MemoryKind | None:
    """What kind of memory this incident's retention is (023b T041,
    B-FR-012, R13) — or None: retention fires ONLY on terminal entry.
    A ``closed`` incident proved its provenance (R8's ancestry check), so
    it is a LESSON; every other terminal state keeps an EXPERIENCE —
    including ``resolved_externally`` (the squash-merge honesty: no
    lesson is claimed without provable provenance) and the 023a
    terminals."""
    if incident.state not in TERMINAL_INCIDENT_STATES:
        return None
    if incident.state is IncidentState.CLOSED:
        return MemoryKind.INCIDENT_LESSON
    return MemoryKind.INCIDENT_EXPERIENCE


def render_retention(incident: Incident) -> str:
    """The scrubbed retention text (023b T041, B-FR-012, R13): symptom,
    cause, fix, outcome, attempts and the source child id, bounded at
    ``RETENTION_BOUND``. Pure and total — every terminal incident shape
    renders (a reopen clears the plan, so the cause may be absent).

    The finding's ``evidence`` is NEVER echoed: it is a verbatim quote
    and can carry a live secret. The symptom is carried by rule, path,
    severity and the prose ``detail``; the scrub hook still runs
    activity-side (R13), but the renderer does its part."""
    sections: list[str] = []
    finding = incident.finding
    if finding is not None:
        sections.append(
            f"symptom: {finding.rule} in {finding.path}"
            f" (severity {finding.severity}) - {finding.detail}"
        )
    plan = incident.plan
    if plan is not None:
        sections.append(f"cause: {plan.analysis}")
        fixes = [a for a in plan.actions if a.kind == "code_fix"]
        if fixes:
            rendered = "; ".join(f"{a.summary} ({', '.join(a.target_paths)})" for a in fixes)
            sections.append(f"fix: {rendered}")
    record = incident.execution or (incident.executions[-1] if incident.executions else None)
    sections.append(f"outcome: {incident.state.value} after {incident.attempt} attempt(s)")
    if record is not None:
        sections.append(f"source child: {record.child_id}")
    return "\n".join(sections)[:RETENTION_BOUND]
