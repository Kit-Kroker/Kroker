"""FR-202: the registry's `defaults.validation_retries` knob.

registry.yaml may carry an optional `defaults:` block beside `version`;
a role's agent.yaml overrides it via `RoleConfig.validation_retries`;
parsing materializes the effective value on every role, so None never
survives a registry load. Anything that would parse into a value no site
reads fails boot — unknown `defaults:` keys, out-of-range counts, and the
key on a harness role (VR-1/VR-1b of
docs/superpowers/specs/2026-11-14-validation-retries-knob-design.md,
the same fail-closed rule `_parse_role` already applies to unread files).
"""

import pytest
from pydantic import ValidationError

from sdlc.agents.loader import RegistryError, effective_validation_retries, load_registry
from sdlc.core.models import RoleConfig
from tests.conftest import write_registry_dir


def _write_registry(root, defaults=None):
    """A VALID registry tree (conftest's write_registry_dir), with an
    optional `defaults:` block rewritten into registry.yaml. Tests perturb
    exactly one thing after calling this, so each assertion fails for the
    reason under test."""
    root = write_registry_dir(root)
    if defaults is not None:
        lines = [
            "version: 1",
            "defaults:",
            *(f"  {key}: {value}" for key, value in defaults.items()),
        ]
        (root / "registry.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_default_applied_when_a_role_omits_the_key(tmp_path):
    root = _write_registry(tmp_path, defaults={"validation_retries": 1})
    roles = load_registry(root)
    assert roles["reviewer"].validation_retries == 1
    # Harness roles materialize too — the value is simply unread there.
    assert roles["dev"].validation_retries == 1


def test_per_role_override_wins_over_the_default(tmp_path):
    root = _write_registry(tmp_path, defaults={"validation_retries": 1})
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:glm-5.2\nvalidation_retries: 3\n"
    )
    roles = load_registry(root)
    assert roles["reviewer"].validation_retries == 3
    assert roles["architect"].validation_retries == 1  # default still applies elsewhere


def test_defaults_unknown_key_rejected(tmp_path):
    _write_registry(tmp_path, defaults={"validation_retries": 1, "made_up": 2})
    with pytest.raises(RegistryError, match="made_up"):
        load_registry(tmp_path)


@pytest.mark.parametrize("bad", [0, 6])
def test_defaults_validation_retries_out_of_range_rejected(tmp_path, bad):
    _write_registry(tmp_path, defaults={"validation_retries": bad})
    with pytest.raises(RegistryError, match="validation_retries"):
        load_registry(tmp_path)


@pytest.mark.parametrize("bad", [0, 6])
def test_per_role_validation_retries_out_of_range_is_pydantic_error(tmp_path, bad):
    root = _write_registry(tmp_path, defaults={"validation_retries": 1})
    (root / "reviewer" / "agent.yaml").write_bytes(
        f"kind: proposer\nmodel: anthropic:glm-5.2\nvalidation_retries: {bad}\n".encode()
    )
    with pytest.raises(ValidationError):
        load_registry(root)


def test_harness_role_carrying_the_key_rejected(tmp_path):
    """VR-1b: a harness role runs a CLI and would never read the knob —
    the same silent-dead-config rule as harness roles carrying unread
    files. Reuses conftest's dev-role shape verbatim and perturbs one key."""
    root = _write_registry(tmp_path)
    dev_yaml = root / "dev" / "agent.yaml"
    dev_yaml.write_bytes(dev_yaml.read_bytes() + b"validation_retries: 3\n")
    with pytest.raises(RegistryError) as exc:
        load_registry(root)
    msg = str(exc.value)
    assert "dev" in msg
    assert "silent dead config" in msg


def test_effective_validation_retries_precedence(tmp_path):
    root = _write_registry(tmp_path, defaults={"validation_retries": 1})
    (root / "reviewer" / "agent.yaml").write_bytes(
        b"kind: proposer\nmodel: anthropic:glm-5.2\nvalidation_retries: 3\n"
    )
    roles = load_registry(root)
    assert effective_validation_retries(roles, "reviewer") == 3  # override
    assert effective_validation_retries(roles, "architect") == 1  # materialized default
    # Hand-built mappings (the graph fixtures' dict-built registries) carry
    # None — the final fallback is 1.
    hand_built = {"reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2")}
    assert effective_validation_retries(hand_built, "reviewer") == 1
