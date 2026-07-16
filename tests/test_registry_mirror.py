"""PipelineConfig.roles is a hardcoded mirror of agents.yaml's harness roles.

It must be hardcoded: PipelineConfig() is constructed inside the workflow
(feature.py:602), so a default_factory reading agents.yaml would put file I/O
in the Temporal sandbox. The mirror-check makes drift a boot failure instead of
a silent divergence — which is exactly how ADR-6 came to validate a role that
never ran.
"""
import pytest

from sdlc.agents.loader import HARNESS_ROLES, RegistryError, validate_registry
from sdlc.models import HarnessKind, PipelineConfig, RoleConfig

from test_agents_registry import _complete_registry


def test_pipeline_default_roles_are_exactly_the_harness_roles():
    assert set(PipelineConfig().roles) == HARNESS_ROLES


def test_shipped_registry_and_pipeline_default_agree():
    from sdlc.agents.loader import load_registry
    validate_registry(load_registry())        # must not raise


def test_registry_drifting_from_pipeline_default_is_rejected():
    """A different-family model keeps ADR-6 satisfied, so this fails on the
    mirror and nothing else."""
    roles = _complete_registry(
        dev=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                       model="zai-coding-plan/some-other-coder"))
    with pytest.raises(RegistryError, match="mirror"):
        validate_registry(roles)


def test_mirror_error_names_the_role_and_both_values():
    roles = _complete_registry(
        test=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                        model="zai-coding-plan/drifted"))
    with pytest.raises(RegistryError) as exc:
        validate_registry(roles)
    assert "test" in str(exc.value)
    assert "zai-coding-plan/drifted" in str(exc.value)
    assert "zai-coding-plan/glm-5.2" in str(exc.value)
