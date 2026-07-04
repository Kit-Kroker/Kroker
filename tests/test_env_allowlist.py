import sdlc.harness.adapters as ad


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
