import pytest

from sdlc.agents.loader import (
    REQUIRED_ROLES,
    RegistryError,
    load_registry,
    model_family,
    validate_registry,
)
from sdlc.core.models import (
    HarnessKind,
    RoleConfig,
)

# 7f5191d0 moved dev/devops to glm-5.3; round 019 moved test to glm-5.3.
_HARNESS_MODELS = {
    "dev": "zai-coding-plan/glm-5.3",
    "test": "zai-coding-plan/glm-5.3",
    "devops": "zai-coding-plan/glm-5.3",
}
_PROPOSER_MODEL = "anthropic:glm-5.2"
_FLIPPED_PROPOSER_MODEL = "zai:glm-5.3"


def _complete_registry(**overrides: RoleConfig) -> dict[str, RoleConfig]:
    """A registry that passes every check. Tests perturb ONE role via
    overrides so each assertion fails for the reason under test."""
    roles: dict[str, RoleConfig] = {
        name: RoleConfig(kind="harness", harness=HarnessKind.OPENCODE, model=_HARNESS_MODELS[name])
        for name in ("dev", "test", "devops")
    }
    roles.update(
        {
            name: RoleConfig(kind="proposer", model=_PROPOSER_MODEL)
            for name in (
                "clarify",
                "architect",
                "planner",
                "qa",
                "reviewer",
                "analyst",
                "merge_verdict",
                "devops_planner",
            )
        }
    )
    roles.update(overrides)
    return roles


def test_model_family_splits_on_colon_and_slash():
    assert model_family("anthropic:glm-5.2") == "anthropic"
    assert model_family("zai-coding-plan/glm-5.2") == "zai-coding-plan"
    assert model_family("OpenAI/gpt-5.2") == "openai"


def test_complete_registry_helper_is_itself_valid():
    validate_registry(_complete_registry())  # must not raise


def test_shipped_registry_loads_and_validates():
    roles = load_registry()  # default: discovered agents/
    assert REQUIRED_ROLES <= set(roles)
    validate_registry(roles)  # must not raise


def test_shipped_registry_models_are_the_005_targets():
    """US1 (005 T019, data-model.md): the SHIPPED agents/ tree declares the
    flipped models exactly — the 11 glm proposer roles on ``zai:glm-5.3``,
    dev and devops on ``zai-coding-plan/glm-5.3`` (moved off glm-5.2 by
    7f5191d0), test moved to ``zai-coding-plan/glm-5.3`` in round 019,
    adversary on ``anthropic:claude-sonnet-5`` (moved off glm-5.3-flash
    after R019's weak arm collided with it by model id) and discover/risk
    on ``zai:glm-5.3-flash`` — and ADR-6 still holds on the flipped
    registry (validate_registry does not raise)."""
    roles = load_registry()
    for name in (
        "analyst",
        "architect",
        "clarify",
        "devops_planner",
        "handoff",
        "planner",
        "research",
    ):
        assert roles[name].model == _FLIPPED_PROPOSER_MODEL, (
            f"{name} ships {roles[name].model!r}; the 005 flip puts the 11 "
            f"glm proposer roles on '{_FLIPPED_PROPOSER_MODEL}' (data-model.md)"
        )
    # ADR-6 (amended 2026-11-11): every judge runs different weights than dev.
    for name in ("deep_review", "merge_verdict", "qa", "reviewer"):
        assert roles[name].model == "zai:glm-5.3-flash", name
    for name in ("dev", "test", "devops"):
        assert roles[name].model == _HARNESS_MODELS[name], (
            f"{name} ships {roles[name].model!r}; the harness default is "
            f"'{_HARNESS_MODELS[name]}' (dev/devops glm-5.3 since 7f5191d0)"
        )
    assert roles["adversary"].model == "anthropic:claude-sonnet-5"
    assert roles["discover"].model == "zai:glm-5.3-flash"
    assert roles["risk"].model == "zai:glm-5.3-flash"
    validate_registry(roles)  # must not raise: ADR-6 on the flipped registry


@pytest.mark.parametrize("missing", sorted(REQUIRED_ROLES))
def test_each_required_role_is_required(missing):
    roles = _complete_registry()
    del roles[missing]
    with pytest.raises(RegistryError, match=missing):
        validate_registry(roles)


def test_same_family_dev_and_reviewer_rejected():
    roles = _complete_registry(reviewer=RoleConfig(kind="proposer", model="zai:glm-5.3"))
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_registry(roles)


def test_adr6_checks_dev_not_a_bystander_role():
    """Finding 4 regression. Before this change the check compared reviewer
    against a 'developer' entry that never ran, while cfg.roles['dev'] did the
    coding. A registry where the REAL developer collides with the reviewer must
    now fail."""
    roles = _complete_registry(
        dev=RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model=_PROPOSER_MODEL
        ),  # same model id as reviewer
    )
    with pytest.raises(RegistryError, match="ADR-6"):
        validate_registry(roles)


def test_different_family_accepted():
    validate_registry(_complete_registry())  # no raise


def test_deep_review_harness_reviewer_must_differ_from_developer():
    roles = _complete_registry(
        reviewer=RoleConfig(kind="harness", harness=HarnessKind.OPENCODE, model=_PROPOSER_MODEL)
    )
    with pytest.raises(RegistryError, match="harness"):
        validate_registry(roles)


from sdlc.agents.loader import KNOWN_ROLES, OPTIONAL_ROLES
from tests.conftest import write_registry_dir as _write_registry_dir


def test_optional_roles_contains_research_and_deep_review():
    assert OPTIONAL_ROLES == frozenset(
        {
            "research",
            "deep_review",
            "handoff",
            "adversary",
            "discover",
            "risk",
            "constitution",
            "product",
            "maintainer",
        }
    )
    assert KNOWN_ROLES == REQUIRED_ROLES | OPTIONAL_ROLES


def test_directory_registry_loads_and_validates(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    roles = load_registry(root)
    assert set(roles) == KNOWN_ROLES
    assert roles["dev"].harness == HarnessKind.OPENCODE


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
        b"role: analyst\nkind: proposer\nmodel: anthropic:glm-5.2\n"
    )
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
        b"kind: proposer\nmodel: zai-coding-plan/glm-5.3\n"
    )  # dev's model id
    with pytest.raises(RegistryError, match="ADR-6"):
        load_registry(root)


# =========================================================================== #
# ## chaos: per-role unknown keys (FR-202 follow-up) -- qa-chaos, RED
#
# Happy paths are qa-happy's. Everything here is an edge: multiple surplus
# keys, a present-but-empty surplus key, the `role:` bookkeeping key staying
# legal, the actionability of the message, and non-mapping/non-string-key
# files. Subject: loader._parse_role, which today builds RoleConfig(**data)
# with pydantic's default extra=ignore, so every surplus key vanishes.
# Subject files: .workspace/tasks/2026-11-14-fr202-per-role-unknown-keys.md.
# =========================================================================== #


def _append_agent_yaml(root, role: str, text: str) -> None:
    p = root / role / "agent.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "\n" + text, encoding="utf-8")


def test_multiple_unknown_keys_are_all_named_sorted_not_just_the_first(tmp_path):
    # "not just the first": a fix that reports only one surplus key forces a
    # fix-run-fix loop. Sorted order keeps the message deterministic.
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "bogus_zeta: 1\nbogus_alpha: 2\nbogus_mid: 3")
    with pytest.raises(RegistryError) as exc_info:
        load_registry(root)
    msg = str(exc_info.value)
    for key in ("bogus_alpha", "bogus_mid", "bogus_zeta"):
        assert key in msg, f"{key} must be named, got: {msg}"
    assert msg.index("bogus_alpha") < msg.index("bogus_mid") < msg.index("bogus_zeta")


def test_unknown_key_with_an_empty_value_still_refuses(tmp_path):
    # A present-but-empty key is not an absent key. `bogus_key:` parses to
    # None and must still be refused, not dropped as "nothing set".
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "bogus_key:")
    with pytest.raises(RegistryError, match="bogus_key"):
        load_registry(root)


def test_bookkeeping_role_key_stays_legal_with_known_keys(tmp_path):
    # The filename-agreement check depends on `role:`. The unknown-key
    # refusal must not swallow it: a file with a matching `role:` and only
    # known keys still loads. (Passes today by design; the fix must keep it.)
    root = _write_registry_dir(tmp_path / "agents")
    p = root / "planner" / "agent.yaml"
    p.write_text("role: planner\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    roles = load_registry(root)
    assert roles["planner"].kind == "proposer"


def test_unknown_key_message_names_the_role_the_key_and_the_known_set(tmp_path):
    # Actionable on the typo case the task names: validation_retry vs
    # validation_retries. The message must say WHICH role, WHICH key, and
    # hint a real known key so the fix is obvious.
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "validation_retry: 3")
    with pytest.raises(RegistryError) as exc_info:
        load_registry(root)
    msg = str(exc_info.value)
    assert "planner" in msg
    assert "validation_retry" in msg
    assert "validation_retries" in msg  # the known set is hinted


def test_unknown_key_is_refused_on_a_harness_role_too(tmp_path):
    # The check must not be proposer-only: a harness role's agent.yaml carries
    # the same surface. `dev` is the harness role in the registry tree.
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "dev", "bogus_harness_key: yes")
    with pytest.raises(RegistryError, match="bogus_harness_key"):
        load_registry(root)


def test_unknown_key_match_is_case_sensitive(tmp_path):
    # `Model:` is not `model:`. A case-folding loader would silently accept
    # the wrong spelling; the surplus check must refuse it.
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "Model: anthropic:glm-5.2")
    with pytest.raises(RegistryError, match="Model"):
        load_registry(root)


def test_non_string_yaml_key_is_a_registry_error_not_a_type_error(tmp_path):
    # Subtlety: `42: x` is a valid YAML mapping with an int key. Splatting it
    # into RoleConfig(**data) raises TypeError today. The contract is a
    # RegistryError naming the bad key.
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "42: x")
    with pytest.raises(RegistryError, match="42"):
        load_registry(root)


def test_non_mapping_agent_yaml_is_a_registry_error_not_an_attribute_error(tmp_path):
    # Subtlety: a top-level list parses fine but `data.pop("role", None)`
    # raises TypeError today (list.pop takes one argument). A malformed file
    # must be a RegistryError naming the role.
    root = _write_registry_dir(tmp_path / "agents")
    (root / "planner" / "agent.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RegistryError, match="planner"):
        load_registry(root)


def test_present_but_empty_known_key_is_legal_and_uses_the_default(tmp_path):
    # Anti-overcorrection pin: `validation_retries:` (known, empty) must stay
    # legal and materialise the registry default, while an EMPTY UNKNOWN key
    # is refused. Guards a fix that rejects every None-valued key. (Passes
    # today by design.)
    root = _write_registry_dir(tmp_path / "agents")
    _append_agent_yaml(root, "planner", "validation_retries:")
    roles = load_registry(root)
    assert roles["planner"].kind == "proposer"


# =========================================================================== #
# ## S-rider RED (.workspace/tasks/2026-11-14-fr202-per-role-unknown-keys.md)
#
# Per-role agent.yaml files parse into RoleConfig, which ignores unknown keys:
# a typo'd `validation_retry:` silently runs the role on defaults. The defaults
# block already fails closed on unknown keys (_defaults_validation_retries);
# these tests pin the same rule for per-role files. Happy-path pair only.
# =========================================================================== #


def test_typoed_per_role_key_is_rejected_naming_the_role_and_the_key(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:glm-5.2\nvalidation_retry: 2\n"
    )  # typo: the key is validation_retries
    with pytest.raises(RegistryError) as exc:
        load_registry(root)
    message = str(exc.value)
    assert "reviewer" in message
    assert "validation_retry" in message


def test_clean_per_role_keys_still_load_with_the_bookkeeping_role_key(tmp_path):
    root = _write_registry_dir(tmp_path / "agents")
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"role: reviewer\n"
        b"kind: proposer\n"
        b"model: anthropic:glm-5.2\n"
        b"validation_retries: 2\n"
        b"context_budget_tokens: 20000\n"
    )
    roles = load_registry(root)
    assert roles["reviewer"].validation_retries == 2
    assert roles["reviewer"].context_budget_tokens == 20000
