import pytest

from sdlc.agents.loader import (
    KNOWN_ROLES, OPTIONAL_ROLES, REQUIRED_ROLES, RegistryError, load_registry,
)
from tests.conftest import write_registry_dir


def test_research_is_optional_not_required():
    assert "research" in OPTIONAL_ROLES
    assert "research" in KNOWN_ROLES
    assert "research" not in REQUIRED_ROLES


@pytest.mark.xfail(reason="shipped agents/research/ lands in Task 6",
                   strict=True)
def test_shipped_registry_loads_with_research(monkeypatch, tmp_path):
    """The repo's own agents/ tree loads and includes a research role."""
    roles = load_registry()               # shipped agents/
    assert roles["research"].kind == "research"
    assert roles["research"].provider in ("fake", "tavily")


def test_research_tree_loads_and_carries_tool_paths(tmp_path, monkeypatch):
    root = write_registry_dir(tmp_path / "agents")
    monkeypatch.setenv("SDLC_AGENTS_DIR", str(root))
    roles = load_registry(root)
    r = roles["research"]
    assert r.kind == "research"
    assert r.provider == "fake"
    assert any(p.endswith("web_search.py") for p in r.tool_files)


def test_research_without_provider_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "agent.yaml").write_bytes(
        b"kind: research\nmodel: anthropic:glm-5.2\n")   # no provider
    with pytest.raises(RegistryError, match="provider"):
        load_registry(root)


def test_research_tavily_without_key_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "agent.yaml").write_bytes(
        b"kind: research\nmodel: anthropic:glm-5.2\nprovider: tavily\n")
    with pytest.raises(RegistryError, match="TAVILY_API_KEY"):
        load_registry(root)


def test_research_missing_tools_dir_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    import shutil
    shutil.rmtree(root / "research" / "tools")
    with pytest.raises(RegistryError, match="tools"):
        load_registry(root)


def test_tool_file_with_unannotated_signature_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "tools" / "bad.py").write_bytes(
        b"def bad(query):\n    return []\n")   # no annotations, name==file ok
    with pytest.raises(RegistryError, match="annotat"):
        load_registry(root)


def test_tool_filename_function_mismatch_fails_closed(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    (root / "research" / "tools" / "mismatch.py").write_bytes(
        b"def other(query: str) -> list:\n    return []\n")
    with pytest.raises(RegistryError, match="mismatch"):
        load_registry(root)
