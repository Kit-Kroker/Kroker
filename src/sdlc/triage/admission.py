"""FR-903 (E-45 D2): the ONE admission rule, at two strictnesses.

Pure -- Pydantic and triage/models.py only, like the rest of triage/.

Tier 0 (tidy-up) and Tier 2 (assessment) differ in whether a non-human
approval admits, and that difference is a PARAMETER rather than a second copy
of the rule. Two admission rules in two modules agree only by coincidence,
which is the failure shape 2026-07-16-registry-drives-every-role was written
about: an invariant that held only while two hardcoded lists matched.
"""

from __future__ import annotations

from .models import RepoTriage, Verdict


def admits(triage: RepoTriage, *, require_human: bool) -> tuple[bool, str]:
    """Whether this triage admits the repository to the caller's tier.

    Returns (admitted, reason). The reason is recorded on the artifact, so a
    refusal is legible without a Temporal replay.

    `reviewer` is deliberately NOT consulted: it is self-asserted (the gap
    FR-1004 closes), while approved_by carries GateDecision.decided_by
    VERBATIM and is therefore the field that can be trusted to distinguish a
    human act from "policy" (gate OFF) or "timeout" (on_timeout=APPROVE).
    """
    verdict = triage.readiness.verdict
    if verdict is Verdict.READY:
        return True, "verdict ready"
    override = triage.override
    if override is None:
        return False, f"verdict {verdict.value} and no override"
    if require_human and override.approved_by != "human":
        return False, (
            f"verdict {verdict.value}; override approved_by="
            f"{override.approved_by!r} is not a human act"
        )
    return True, (f"verdict {verdict.value} admitted by {override.approved_by} override")
