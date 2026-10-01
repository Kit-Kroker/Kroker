import pytest

from sdlc.agents.loader import RegistryError
from sdlc.cli_roles import build_role_overrides, parse_role_models


def test_parse_valid_pairs():
    assert parse_role_models(
        ["architect=anthropic:claude-opus-4-8", "dev=zai-coding-plan/glm-5.2"]
    ) == {"architect": "anthropic:claude-opus-4-8", "dev": "zai-coding-plan/glm-5.2"}


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_role_models(["architectopus"])  # no '='


def test_parse_rejects_unknown_role():
    with pytest.raises(ValueError, match="unknown role"):
        parse_role_models(["wizard=openai/gpt-5.2"])


def test_build_overrides_sets_proposer_and_harness():
    roles = build_role_overrides({"architect": "openai:gpt-5.2"})
    assert roles["architect"].kind == "proposer"
    assert roles["architect"].model == "openai:gpt-5.2"


def test_build_overrides_rejects_invalid_proposer_model():
    """FR-004 (004 T017): a proposer override that is not a valid
    provider:model id is refused at submission. RED on main: the string is
    currently accepted and silently never reaches the model."""
    with pytest.raises(RegistryError, match=r"provider:model") as excinfo:
        build_role_overrides({"architect": "openai/gpt-5.2"})
    message = str(excinfo.value)
    assert "architect" in message
    assert "openai/gpt-5.2" in message


def test_build_overrides_accepts_harness_grammar_unchanged():
    """FR-005: harness roles keep their own grammar (the CLI adapter takes
    the string verbatim); validation is per role kind."""
    roles = build_role_overrides({"dev": "zai-coding-plan/glm-5.2"})
    assert roles["dev"].model == "zai-coding-plan/glm-5.2"


def test_build_overrides_rejects_adr6_violation():
    # force dev into the registry reviewer's family; expect a raise.
    # registry reviewer is a fixed family; dev override sharing it must fail.
    from sdlc.agents.loader import load_registry

    reg = load_registry()
    rev_model = reg["reviewer"].model
    with pytest.raises(RegistryError, match="ADR-6"):
        build_role_overrides({"dev": rev_model})
