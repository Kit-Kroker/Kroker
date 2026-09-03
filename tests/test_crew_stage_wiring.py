# tests/test_crew_stage_wiring.py
"""E-88 §5: the run's (harness, model) wins over the role file, but ONLY for
the lead. Non-lead roles take both from their own file, so a benchmark cell
varies exactly one thing."""

from __future__ import annotations

import pytest

from sdlc.core.models import (
    HarnessKind,
    RoleConfig,
)
from sdlc.crew.config import CrewLayout, CrewRole
from sdlc.crew.loader import resolve_crew_roles

LAYOUT = CrewLayout(
    layout="code",
    lead="coder",
    crew=["coder"],
    deliverable={"path": "notes.md", "schema": "notes-v1"},
    limits={"wall_clock_s": 3000, "turn_timeout_s": 1800, "cost_usd": 25.0},
)
ROLES = {
    "coder": CrewRole(
        name="coder",
        harness="opencode",
        model="zai-coding-plan/glm-5.3",
        writes=True,
        skill="coder",
    )
}


def test_role_config_carries_the_crew_knobs():
    rc = RoleConfig(
        harness=HarnessKind.CREW,
        layout="code",
        lead_harness=HarnessKind.CLAUDE_CODE,
        model="anthropic:claude-opus-5",
    )
    assert rc.layout == "code"
    assert rc.lead_harness is HarnessKind.CLAUDE_CODE


def test_the_run_model_wins_for_the_lead():
    out = resolve_crew_roles(LAYOUT, ROLES, lead_harness=None, lead_model="zai-coding-plan/glm-5.9")
    assert out[0].model == "zai-coding-plan/glm-5.9"
    assert out[0].harness is HarnessKind.OPENCODE


def test_the_run_harness_wins_for_the_lead():
    out = resolve_crew_roles(
        LAYOUT, ROLES, lead_harness=HarnessKind.CLAUDE_CODE, lead_model="anthropic:claude-opus-5"
    )
    assert out[0].harness is HarnessKind.CLAUDE_CODE
    assert out[0].model == "anthropic:claude-opus-5"


def test_a_harness_swap_without_a_model_is_refused():
    """spec §5: model strings are pass-through in each CLI's own syntax, so a
    harness swap that keeps the old string is guaranteed to fail at runtime.
    Refuse before the DAG starts, not after other roles have spent."""
    with pytest.raises(ValueError, match="model"):
        resolve_crew_roles(LAYOUT, ROLES, lead_harness=HarnessKind.CLAUDE_CODE, lead_model=None)


def test_the_lead_may_not_resolve_to_crew():
    with pytest.raises(ValueError, match="not a CLI"):
        resolve_crew_roles(LAYOUT, ROLES, lead_harness=HarnessKind.CREW, lead_model="x")
