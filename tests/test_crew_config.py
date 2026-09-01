# tests/test_crew_config.py
"""E-88 §5: a layout describes a TEAM, not a window. There is no geometry
here -- `splits` was herdr's and does not come across."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.crew.config import CrewLayout, CrewRole
from sdlc.models import HarnessKind


def test_crew_kind_exists():
    assert HarnessKind.CREW.value == "crew"


def test_role_parses_the_shipped_shape():
    r = CrewRole(
        name="coder",
        harness="opencode",
        model="zai-coding-plan/glm-5.3",
        writes=True,
        skill="coder",
    )
    assert r.harness is HarnessKind.OPENCODE
    assert r.writes is True
    assert r.superpowers == []


def test_role_requires_a_model():
    """Global constraint: a role without a model cannot enter ADR-6's
    role_models map in step 2, so it is rejected here, not there."""
    with pytest.raises(ValidationError):
        CrewRole(name="coder", harness="opencode", writes=True, skill="coder")


def test_layout_lists_its_roles_lead_first():
    lay = CrewLayout(
        layout="code",
        lead="coder",
        crew=["coder"],
        deliverable={"path": "notes.md", "schema": "notes-v1"},
        limits={"wall_clock_s": 3000, "turn_timeout_s": 1800, "cost_usd": 25.0},
    )
    assert lay.roles() == ["coder"]
    assert lay.rounds.max == 1


def test_layout_rejects_geometry():
    """`splits` was screen geometry. extra='forbid' makes a copied herdr
    layout fail loudly instead of silently ignoring half of itself."""
    with pytest.raises(ValidationError):
        CrewLayout(
            layout="code",
            lead="coder",
            crew=["coder"],
            splits=[{"from": "coder", "to": "critic", "direction": "right"}],
            deliverable={"path": "notes.md", "schema": "notes-v1"},
            limits={"wall_clock_s": 3000, "turn_timeout_s": 1800, "cost_usd": 25.0},
        )


def test_layout_rejects_a_lead_outside_its_crew():
    with pytest.raises(ValidationError):
        CrewLayout(
            layout="code",
            lead="planner",
            crew=["coder"],
            deliverable={"path": "notes.md", "schema": "notes-v1"},
            limits={"wall_clock_s": 3000, "turn_timeout_s": 1800, "cost_usd": 25.0},
        )
