import os

import sdlc.harness.base as ad


def test_build_env_excludes_non_allowlisted_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leakme")
    env = ad.build_env({"GITHUB_TOKEN": "scoped-short-lived"})
    assert env["PATH"] == "/usr/bin"
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["GITHUB_TOKEN"] == "scoped-short-lived"


def test_build_env_injected_credentials_are_included():
    env = ad.build_env({"GITHUB_TOKEN": "x"})
    assert env["GITHUB_TOKEN"] == "x"


def test_build_env_only_includes_present_allowlisted_vars(monkeypatch):
    monkeypatch.delenv("LANG", raising=False)
    env = ad.build_env({})
    assert "LANG" not in env  # not set in os.environ → not fabricated


def test_provider_env_carries_anthropic_prefix_and_nothing_else(monkeypatch):
    """The secret channel is exactly the ANTHROPIC_* prefix of the ambient
    environment: the two vars set here must pass through verbatim, anything
    outside the prefix (AWS secret below) must never appear. Compared against
    the live prefix rather than a literal dict — conftest seeds dummy
    ANTHROPIC_* vars for import-only tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leakme")
    env = ad.provider_env()
    expected = {k: v for k, v in os.environ.items() if k.startswith("ANTHROPIC_")}
    assert env == expected
    assert not any(k.startswith("AWS_") for k in env)
