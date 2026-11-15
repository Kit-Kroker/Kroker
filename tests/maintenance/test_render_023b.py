"""Retention text and kind (023b T040, RED): render_retention and retention_kind.

Subject: ``sdlc.maintenance.render`` (B-FR-012, R13; tasks.md T040).
- ``render_retention(incident) -> str``: a PURE renderer of symptom, cause, fix,
  outcome, attempts and source child id. Bounded at 2000 characters, and total
  over every terminal incident shape.
- ``retention_kind(incident) -> MemoryKind | None``: a lesson for ``closed``, an
  experience for every other terminal state, and None for every live state.
  Retention fires only on terminal entry.

Builders are local to this file (no test-module imports), per the us-suite rule.
Each test imports the render functions inside its body, so each case fails on its
own ImportError before T041 lands.
"""

from __future__ import annotations

import pytest

from sdlc.maintenance.models import (
    TERMINAL_INCIDENT_STATES,
    ExecutionRecord,
    Incident,
    IncidentState,
    RepairAction,
    RepairPlan,
)
from sdlc.triage.models import FixClass, TriageFinding

BOUND = 2000
CHILD_ID = "maint-demo-abcd1234-inc1-a2"
ANALYSIS = "The .env file is tracked and holds a live token; untracking it stops the leak."
SECRET_EVIDENCE = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"

LIVE_STATES = frozenset(IncidentState) - TERMINAL_INCIDENT_STATES


def _finding(evidence: str = "") -> TriageFinding:
    return TriageFinding(
        signal="secrets",
        rule="env_file_tracked",
        severity="high",
        detail=".env is tracked; add it to .gitignore and remove it from the index.",
        path=".gitignore",
        evidence=evidence,
        fix_class=FixClass.MECHANICAL,
    )


def _plan(analysis: str = ANALYSIS) -> RepairPlan:
    return RepairPlan(
        analysis=analysis,
        actions=[
            RepairAction(
                kind="code_fix",
                summary="untrack .env and ignore it",
                target_paths=[".env", ".gitignore"],
            )
        ],
        self_confidence=0.9,
        floor=0.95,
        effective=0.9,
        author_model="claude-sonnet-5-5",
    )


def _execution(child_id: str, attempt: int, outcome: str) -> ExecutionRecord:
    from datetime import UTC, datetime

    return ExecutionRecord(
        attempt=attempt,
        child_id=child_id,
        base_sha="a" * 40,
        started_at=datetime(2026, 11, 15, tzinfo=UTC),
        outcome=outcome,
        detail="",
    )


def _incident(state: str, *, plan: RepairPlan | None = None, evidence: str = "") -> Incident:
    return Incident(
        no=1,
        key="secrets:env_file_tracked::.gitignore",
        kind="finding",
        finding=_finding(evidence),
        commit_sha="b" * 40,
        first_seen_cycle=1,
        last_seen_cycle=4,
        seen_count=3,
        state=IncidentState(state),
        plan=plan,
        attempt=2,
        executions=[
            _execution(CHILD_ID.replace("a2", "a1"), 1, "rejected_by_loop"),
            _execution(CHILD_ID, 2, "completed"),
        ],
    )


def _closed() -> Incident:
    return _incident("closed", plan=_plan(), evidence=SECRET_EVIDENCE)


# ------------------------------------------------------------- 1. content (symptom/cause/fix)


def test_a_closed_incident_renders_symptom_cause_fix_outcome_attempts_and_child():
    from sdlc.maintenance.render import render_retention

    text = render_retention(_closed())
    assert "env_file_tracked" in text, "symptom: the rule"
    assert ".gitignore" in text, "symptom: the path"
    assert "high" in text, "symptom: the severity"
    assert ANALYSIS in text, "cause: the plan analysis"
    assert "untrack .env and ignore it" in text, "fix: the code_fix summary"
    assert ".env" in text, "fix: the code_fix target path"
    assert "closed" in text, "outcome: the terminal state"
    assert "attempt" in text.lower() and "2" in text, "attempts: the count"
    assert CHILD_ID in text, "the source child id (R13)"


@pytest.mark.parametrize("with_plan", [True, False], ids=["with-plan", "plan-cleared"])
def test_an_escalated_incident_renders_without_crashing_plan_or_not(with_plan):
    """The renderer is total over every terminal shape: a reopen clears the plan, so
    an escalated incident may have none. The cause section is then absent."""
    from sdlc.maintenance.render import render_retention

    inc = _incident("escalated", plan=_plan() if with_plan else None)
    text = render_retention(inc)
    assert isinstance(text, str)
    assert "escalated" in text
    if with_plan:
        assert ANALYSIS in text
    else:
        assert ANALYSIS not in text, "no plan, no cause text"


# ------------------------------------------------------------------ 2. the 2000-char bound


def test_a_pathological_analysis_is_bounded_at_2000_characters():
    from sdlc.maintenance.render import render_retention

    # Executor adaptation: RepairPlan.analysis is Field(max_length=4000)
    # (models.py) — a 5400-char analysis cannot be constructed, so the
    # pathological input is the model's own ceiling. The bound still
    # bites: a 4000-char cause alone exceeds the 2000-char document.
    long_analysis = "analysis " * 500  # 4500 -> truncated to the 4000 ceiling
    assert len(long_analysis) >= 4000
    inc = _incident("closed", plan=_plan(analysis=long_analysis[:4000]))
    text = render_retention(inc)
    assert len(text) <= BOUND


# ---------------------------------------------------- 3. retention_kind: exhaustive matrix


@pytest.mark.parametrize(
    "state",
    sorted(s.value for s in TERMINAL_INCIDENT_STATES),
)
def test_every_terminal_state_is_retained_once_as_a_lesson_or_an_experience(state):
    from sdlc.maintenance.render import retention_kind
    from sdlc.memory.models import MemoryKind

    expected = MemoryKind.INCIDENT_LESSON if state == "closed" else MemoryKind.INCIDENT_EXPERIENCE
    assert retention_kind(_incident(state, plan=_plan())) is expected


@pytest.mark.parametrize("state", sorted(s.value for s in LIVE_STATES))
def test_every_live_state_retains_nothing(state):
    """Retention fires only on terminal entry (R13). ``verified`` and every
    non-terminal state return None."""
    from sdlc.maintenance.render import retention_kind

    assert retention_kind(_incident(state, plan=_plan())) is None


def test_the_matrix_covers_every_incident_state_exactly_once():
    """Exhaustive: the terminal and live sets partition IncidentState. A new state
    added to the enum must be classified here, or this fails."""
    terminal = {s.value for s in TERMINAL_INCIDENT_STATES}
    live = {s.value for s in LIVE_STATES}
    assert terminal.isdisjoint(live)
    assert terminal | live == {s.value for s in IncidentState}
    assert "verified" in live, "verified is live: it is never retained"


# ------------------------------------------------------- 4. scrub: evidence is never echoed


def test_the_rendered_text_never_echoes_the_raw_evidence_quote():
    """TriageFinding.evidence is a verbatim quote and can carry a live secret. The
    symptom is carried by ``detail`` (a prose description with no secret literal),
    so the renderer must not echo ``evidence``."""
    from sdlc.maintenance.render import render_retention

    inc = _closed()
    assert SECRET_EVIDENCE in inc.finding.evidence  # precondition: the secret is there
    text = render_retention(inc)
    assert "AKIAIOSFODNN7EXAMPLE" not in text
    assert SECRET_EVIDENCE not in text


# ------------------------------------------------------ EDGE (023b T040) -- qa-chaos


def test_a_multi_action_plan_renders_every_summary_in_order_and_the_latest_attempt_child():
    """Edge, RED until T041 (ImportError). R12's multi-action shape: two code_fix
    summaries render in plan order. The incident has two attempts (a1 rejected, a2
    the source), so the source child id is the CURRENT attempt's record, a2. The a1
    id must not appear: that would mean the renderer picked the first record."""
    from sdlc.maintenance.render import render_retention

    first = "untrack .env and ignore it"
    second = "rotate the token in the sample config"
    plan = RepairPlan(
        analysis=ANALYSIS,
        actions=[
            RepairAction(kind="code_fix", summary=first, target_paths=[".env", ".gitignore"]),
            RepairAction(kind="code_fix", summary=second, target_paths=["config/sample.ini"]),
        ],
        self_confidence=0.9,
        floor=0.95,
        effective=0.9,
        author_model="claude-sonnet-5-5",
    )
    text = render_retention(_incident("closed", plan=plan))

    assert first in text and second in text
    assert text.index(first) < text.index(second), "summaries keep their plan order"
    assert CHILD_ID in text, "the source child is the current attempt's record"
    assert CHILD_ID.replace("a2", "a1") not in text, "the first attempt is not the source"


def test_the_bound_is_total_and_no_extreme_input_raises():
    """Edge, RED until T041 (ImportError). Pinned, honestly weaker than a promise
    that the symptom survives truncation: the layout is T041's, and the contract
    states only the 2000-character bound. Two things are pinned here:
    (1) a maximal 4000-character analysis (the RepairPlan ceiling) renders within
        2000 characters;
    (2) no exception for a plan with zero actions, or a code_fix with empty
        target_paths.
    Not pinned: that the rule or path survives truncation."""
    from sdlc.maintenance.render import render_retention

    maximal = RepairPlan(
        analysis=("cause " * 600)[:4000],
        actions=[RepairAction(kind="code_fix", summary="fix " * 200, target_paths=[])],
        self_confidence=0.9,
        floor=0.95,
        effective=0.9,
        author_model="claude-sonnet-5-5",
    )
    assert len(render_retention(_incident("closed", plan=maximal))) <= BOUND

    no_actions = RepairPlan(
        analysis=ANALYSIS,
        actions=[],
        self_confidence=0.0,
        floor=0.0,
        effective=0.0,
        author_model="claude-sonnet-5-5",
    )
    assert isinstance(render_retention(_incident("escalated", plan=no_actions)), str)
