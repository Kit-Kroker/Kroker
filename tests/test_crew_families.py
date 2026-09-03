# tests/test_crew_families.py
"""E-88 §5, finding 5: the crew's roles enter the SAME decorrelation rule the
factory already applies to dev/reviewer. A second opinion from the same
weights is not a second opinion, and the granularity is model FAMILY, not
string inequality -- two models from one family are correlated regardless of
their names."""

from __future__ import annotations

import pytest

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.crew.config import CrewRole
from sdlc.crew.loader import CrewConfigError, check_crew_families


def _role(name, model, writes=False, harness=HarnessKind.OPENCODE):
    return CrewRole(name=name, harness=harness, model=model, writes=writes, skill=name)


def test_a_decorrelated_crew_passes():
    check_crew_families(
        "coder",
        [
            _role("coder", "zai-coding-plan/glm-5.3", writes=True),
            _role("critic", "anthropic:claude-opus-5"),
        ],
    )


def test_a_critic_sharing_the_leads_family_is_rejected():
    with pytest.raises(CrewConfigError, match="ADR-6"):
        check_crew_families(
            "coder",
            [
                _role("coder", "zai-coding-plan/glm-5.3", writes=True),
                _role("critic", "zai-coding-plan/glm-4.6"),
            ],
        )


def test_a_different_model_in_the_same_family_is_still_a_collision():
    """The point of family granularity: a different NAME behind the same
    provider is not an independent opinion."""
    with pytest.raises(CrewConfigError, match="ADR-6"):
        check_crew_families(
            "coder",
            [
                _role("coder", "anthropic:claude-opus-5", writes=True),
                _role("critic", "anthropic:claude-sonnet-5"),
            ],
        )


def test_a_one_role_crew_has_nothing_to_check():
    """Step 1's shipped layout. No non-lead roles, so no collision is
    possible -- and this must not become an error."""
    check_crew_families("coder", [_role("coder", "zai-coding-plan/glm-5.3", writes=True)])


def test_a_missing_lead_is_reported_as_itself():
    with pytest.raises(CrewConfigError, match="lead"):
        check_crew_families("nobody", [_role("coder", "zai-coding-plan/glm-5.3", writes=True)])


def test_preflight_refuses_a_colliding_lead_model(tmp_path, monkeypatch):
    """Parent §5: 'a run whose sweep collides never starts'. load_crew is the
    guarantee, but it fires at the code stage -- after clarify, architecture
    and plan have already spent. This is the early warning."""
    import yaml

    from sdlc.crew import loader as crew_loader

    (tmp_path / "layouts").mkdir()
    (tmp_path / "roles").mkdir()
    (tmp_path / "skills" / "coder").mkdir(parents=True)
    (tmp_path / "skills" / "critic").mkdir(parents=True)
    for s in ("coder", "critic"):
        (tmp_path / "skills" / s / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / "layouts" / "code.yaml").write_text(
        yaml.safe_dump(
            {
                "layout": "code",
                "lead": "coder",
                "crew": ["coder", "critic"],
                "rounds": {"max": 2},
                "deliverable": {"path": "notes.md", "schema": "notes-v1"},
                "limits": {"wall_clock_s": 1, "turn_timeout_s": 1, "cost_usd": 1.0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "roles" / "coder.yaml").write_text(
        yaml.safe_dump(
            {
                "harness": "opencode",
                "model": "zai-coding-plan/glm-5.3",
                "writes": True,
                "skill": "coder",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "roles" / "critic.yaml").write_text(
        yaml.safe_dump(
            {
                "harness": "claude_code",
                "model": "anthropic:claude-opus-5",
                "writes": False,
                "skill": "critic",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(crew_loader, "crew_dir", lambda: tmp_path)

    # A run that moves the LEAD onto anthropic collides with the critic.
    with pytest.raises(CrewConfigError, match="ADR-6"):
        crew_loader.preflight_crew("code", None, "anthropic:claude-sonnet-5")
    # The shipped pairing is fine.
    crew_loader.preflight_crew("code", None, "zai-coding-plan/glm-5.3")


def test_preflight_is_silent_without_a_crew_tree(monkeypatch):
    """A source checkout has no crew assets, and a non-crew run must not be
    blocked by their absence."""
    from sdlc.crew import loader as crew_loader

    monkeypatch.setattr(crew_loader, "crew_dir", lambda: None)
    crew_loader.preflight_crew("code", None, "anything/at-all")
