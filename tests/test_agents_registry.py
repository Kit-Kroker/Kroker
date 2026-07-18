import pytest

from sdlc.agents.loader import (
    REQUIRED_ROLES, RegistryError, load_registry, model_family,
    validate_registry,
)
from sdlc.models import HarnessKind, RoleConfig

_HARNESS_MODEL = "zai-coding-plan/glm-5.2"
_PROPOSER_MODEL = "anthropic:glm-5.2"


def _complete_registry(**overrides: RoleConfig) -> dict[str, RoleConfig]:
    """A registry that passes every check. Tests perturb ONE role via
    overrides so each assertion fails for the reason under test."""
    roles: dict[str, RoleConfig] = {
        name: RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                         model=_HARNESS_MODEL)
        for name in ("dev", "test", "devops")
    }
    roles.update({
        name: RoleConfig(kind="proposer", model=_PROPOSER_MODEL)
        for name in ("clarify", "architect", "planner", "qa", "reviewer",
                     "analyst", "merge_verdict", "devops_planner")
    })
    roles.update(overrides)
    return roles


def test_model_family_splits_on_colon_and_slash():
    assert model_family("anthropic:glm-5.2") == "anthropic"
    assert model_family("zai-coding-plan/glm-5.2") == "zai-coding-plan"
    assert model_family("OpenAI/gpt-5.2") == "openai"


def test_complete_registry_helper_is_itself_valid():
    validate_registry(_complete_registry())      # must not raise


def test_shipped_registry_loads_and_validates():
    roles = load_registry()                      # default: discovered agents/
    assert REQUIRED_ROLES <= set(roles)
    validate_registry(roles)                     # must not raise


@pytest.mark.parametrize("missing", sorted(REQUIRED_ROLES))
def test_each_required_role_is_required(missing):
    roles = _complete_registry()
    del roles[missing]
    with pytest.raises(RegistryError, match=missing):
        validate_registry(roles)


def test_same_family_dev_and_reviewer_rejected():
    roles = _complete_registry(
        reviewer=RoleConfig(kind="proposer", model="zai-coding-plan/other"))
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_adr6_checks_dev_not_a_bystander_role():
    """Finding 4 regression. Before this change the check compared reviewer
    against a 'developer' entry that never ran, while cfg.roles['dev'] did the
    coding. A registry where the REAL developer collides with the reviewer must
    now fail."""
    roles = _complete_registry(
        dev=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                       model="anthropic:some-coder"),   # same family as reviewer
    )
    with pytest.raises(RegistryError, match="family"):
        validate_registry(roles)


def test_different_family_accepted():
    validate_registry(_complete_registry())      # no raise


def test_deep_review_harness_reviewer_must_differ_from_developer():
    roles = _complete_registry(
        reviewer=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE,
                            model=_PROPOSER_MODEL))
    with pytest.raises(RegistryError, match="harness"):
        validate_registry(roles)


from sdlc.agents.loader import KNOWN_ROLES, OPTIONAL_ROLES
from tests.conftest import write_registry_dir as _write_registry_dir


def test_optional_roles_contains_research_and_known_is_their_union():
    """The seam the research spec extends. 'research' is its first entry
    (2026-07-17-research-agent-grounded-briefs); KNOWN_ROLES stays the union."""
    assert OPTIONAL_ROLES == frozenset({"research"})
    assert KNOWN_ROLES == REQUIRED_ROLES | OPTIONAL_ROLES


def test_directory_registry_loads_and_validates(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    roles = load_registry(root)
    assert set(roles) == KNOWN_ROLES
    assert roles["dev"].harness == HarnessKind.OPENCODE
    assert roles["reviewer"].model == "anthropic:glm-5.2"


def test_unknown_role_directory_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "not_a_role").mkdir()
    (root / "not_a_role" / "agent.yaml").write_bytes(b"kind: proposer\n")
    with pytest.raises(RegistryError, match="not_a_role"):
        load_registry(root)


def test_role_directory_missing_agent_yaml_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").unlink()
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_agent_yaml_declaring_a_different_role_rejected(tmp_path):
    """The filename is the API; contents disagreeing with it is an error."""
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"role: analyst\nkind: proposer\nmodel: anthropic:glm-5.2\n")
    with pytest.raises(RegistryError, match="reviewer"):
        load_registry(root)


def test_missing_registry_yaml_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "registry.yaml").unlink()
    with pytest.raises(RegistryError, match="registry.yaml"):
        load_registry(root)


def test_unsupported_registry_version_rejected(tmp_path):
    root = _write_registry_dir(tmp_path / "agents", version=99)
    with pytest.raises(RegistryError, match="99"):
        load_registry(root)


def test_adr6_still_bites_through_the_directory_loader(tmp_path):
    """The registry spec's regression test, re-run against directories. This
    is what proves 'strict refactor' rather than aspiration."""
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: zai-coding-plan/other\n")   # dev's family
    with pytest.raises(RegistryError, match="family"):
        load_registry(root)
