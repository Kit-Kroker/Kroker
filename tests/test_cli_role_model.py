import pytest

from sdlc.agents.loader import RegistryError
from sdlc.cli_roles import build_role_overrides, parse_role_models


def test_parse_valid_pairs():
    assert parse_role_models(["architect=anthropic:claude-opus-4-8",
                              "dev=zai-coding-plan/glm-5.2"]) == {
        "architect": "anthropic:claude-opus-4-8",
        "dev": "zai-coding-plan/glm-5.2"}


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_role_models(["architectopus"])   # no '='


def test_parse_rejects_unknown_role():
    with pytest.raises(ValueError, match="unknown role"):
        parse_role_models(["wizard=openai/gpt-5.2"])


def test_build_overrides_sets_proposer_and_harness():
    roles = build_role_overrides({"architect": "openai/gpt-5.2"})
    assert roles["architect"].kind == "proposer"
    assert roles["architect"].model == "openai/gpt-5.2"


def test_build_overrides_rejects_adr6_violation():
    # force dev into the registry reviewer's family; expect a raise.
    # registry reviewer is a fixed family; dev override sharing it must fail.
    from sdlc.agents.loader import load_registry
    reg = load_registry()
    rev_model = reg["reviewer"].model
    with pytest.raises(RegistryError, match="ADR-6"):
        build_role_overrides({"dev": rev_model})
