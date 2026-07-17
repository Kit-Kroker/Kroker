"""Registry resolution must not depend on where the CODE is installed.

`DEFAULT_AGENTS_CONFIG = Path(__file__).resolve().parents[3] / "config" /
"agents.yaml"` worked only because the local install is editable. Under
`pip install .` the package lands in site-packages and parents[3] is
/usr/local/lib/python3.13 — so the image could never boot. These tests pin the
replacement: explicit arg -> $SDLC_AGENTS_DIR -> repo-root discovery -> a
RegistryError that names all three.
"""
import pytest

from sdlc.agents.loader import (
    AGENTS_DIR_ENV, LEGACY_AGENTS_ENV, RegistryError, _resolve_agents_dir,
)


def test_explicit_path_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv(AGENTS_DIR_ENV, str(tmp_path / "from_env"))
    assert _resolve_agents_dir(tmp_path / "explicit") == tmp_path / "explicit"


def test_env_var_used_when_no_explicit_path(tmp_path, monkeypatch):
    monkeypatch.setenv(AGENTS_DIR_ENV, str(tmp_path / "from_env"))
    assert _resolve_agents_dir(None) == tmp_path / "from_env"


def test_repo_root_discovered_by_marker_files(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "agents").mkdir(parents=True)
    (root / "pyproject.toml").write_bytes(b"[project]\n")
    (root / "agents" / "registry.yaml").write_bytes(b"version: 1\n")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.delenv(AGENTS_DIR_ENV, raising=False)
    monkeypatch.chdir(nested)                      # discovery walks UP from cwd
    assert _resolve_agents_dir(None) == root / "agents"


def test_unresolvable_raises_registry_error_naming_all_mechanisms(
        tmp_path, monkeypatch):
    monkeypatch.delenv(AGENTS_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)                    # no markers anywhere above
    with pytest.raises(RegistryError) as exc:
        _resolve_agents_dir(None)
    msg = str(exc.value)
    assert AGENTS_DIR_ENV in msg
    assert "pyproject.toml" in msg
    assert "registry.yaml" in msg


def test_legacy_env_var_raises_rather_than_being_ignored(tmp_path, monkeypatch):
    """SDLC_AGENTS_CONFIG named a FILE; SDLC_AGENTS_DIR names a DIRECTORY.
    Silently ignoring the old name would let a stale value fail later and
    less clearly."""
    monkeypatch.setenv(LEGACY_AGENTS_ENV, str(tmp_path / "agents.yaml"))
    with pytest.raises(RegistryError, match=AGENTS_DIR_ENV):
        _resolve_agents_dir(None)
