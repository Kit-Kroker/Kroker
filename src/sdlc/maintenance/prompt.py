"""The repair prompt (023a T016, FR-009).

Bounded by construction: every free-text input is excerpted to a named
limit so the whole prompt stays under 16 KiB — a proposer request that
grows with a failing build's log tail is a payload the guard would
reject and the loop cannot afford.
"""

from __future__ import annotations

from .models import Incident

PROMPT_LIMIT_BYTES = 16 * 1024
EXCERPT_CHARS = 2_000  # per free-text field (finding detail/evidence/context)
CONTEXT_CHARS = 4_000  # the triage context block


def _excerpt(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"…[{len(text) - limit} chars truncated]"


def render_repair_prompt(incident: Incident, triage_context: str = "") -> str:
    """One proposer call per incident (FR-009): the deterministic facts
    first, then the ask. The maintainer's instructions (its own file)
    carry the evidence-first output discipline; this prompt carries the
    evidence."""
    f = incident.finding
    parts = [
        "A maintenance incident needs a repair plan.",
        "",
        f"Incident: INC-{incident.no} (first seen cycle {incident.first_seen_cycle}, "
        f"seen {incident.seen_count}x, state {incident.state.value})",
        f"Identity: {incident.key}",
        f"Detected on commit: {incident.commit_sha}",
    ]
    if f is not None:
        parts += [
            f"Signal: {f.signal} (rule {f.rule}, severity {f.severity})",
            f"Fix class: {f.fix_class.value}",
            f"Detail: {_excerpt(f.detail, EXCERPT_CHARS)}",
            f"Evidence: {_excerpt(f.evidence, EXCERPT_CHARS)}",
        ]
    else:
        parts.append("Finding: none (detect escalation)")
    if triage_context:
        parts += ["", "Triage context:", _excerpt(triage_context, CONTEXT_CHARS)]
    parts += [
        "",
        "Propose a repair plan: your analysis first (what the evidence shows),",
        "then ordered actions (code_fix with target paths, or ops), then your",
        "self-confidence. Your self-rating is capped by a code-computed floor.",
        "Nothing you propose is executed by this loop.",
    ]
    return "\n".join(parts)[:PROMPT_LIMIT_BYTES]
