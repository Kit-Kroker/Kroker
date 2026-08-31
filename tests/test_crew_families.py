# tests/test_crew_families.py
"""E-88 §5, finding 5: the crew's roles enter the SAME decorrelation rule the
factory already applies to dev/reviewer. A second opinion from the same
weights is not a second opinion, and the granularity is model FAMILY, not
string inequality -- two models from one family are correlated regardless of
their names."""
from __future__ import annotations

import pytest

from sdlc.crew.config import CrewRole
from sdlc.crew.loader import CrewConfigError, check_crew_families
from sdlc.models import HarnessKind


def _role(name, model, writes=False, harness=HarnessKind.OPENCODE):
    return CrewRole(name=name, harness=harness, model=model, writes=writes,
                    skill=name)


def test_a_decorrelated_crew_passes():
    check_crew_families("coder", [
        _role("coder", "zai-coding-plan/glm-5.3", writes=True),
        _role("critic", "anthropic:claude-opus-5"),
    ])


def test_a_critic_sharing_the_leads_family_is_rejected():
    with pytest.raises(CrewConfigError, match="ADR-6"):
        check_crew_families("coder", [
            _role("coder", "zai-coding-plan/glm-5.3", writes=True),
            _role("critic", "zai-coding-plan/glm-4.6"),
        ])


def test_a_different_model_in_the_same_family_is_still_a_collision():
    """The point of family granularity: a different NAME behind the same
    provider is not an independent opinion."""
    with pytest.raises(CrewConfigError, match="ADR-6"):
        check_crew_families("coder", [
            _role("coder", "anthropic:claude-opus-5", writes=True),
            _role("critic", "anthropic:claude-sonnet-5"),
        ])


def test_a_one_role_crew_has_nothing_to_check():
    """Step 1's shipped layout. No non-lead roles, so no collision is
    possible -- and this must not become an error."""
    check_crew_families("coder", [
        _role("coder", "zai-coding-plan/glm-5.3", writes=True)])


def test_a_missing_lead_is_reported_as_itself():
    with pytest.raises(CrewConfigError, match="lead"):
        check_crew_families("nobody", [
            _role("coder", "zai-coding-plan/glm-5.3", writes=True)])
