"""agent_registry: plain-YAML read of agents/ and crew/roles/ (no loader import)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs.agent_registry import RegistryGap, read_crew, read_roles


def _agents(tmp_path: Path) -> Path:
    arch = tmp_path / "architect"
    arch.mkdir()
    (arch / "agent.yaml").write_text("kind: proposer\nmodel: anthropic:glm-5.2\n", encoding="utf-8")
    (arch / "instructions.md").write_text("x", encoding="utf-8")
    dev = tmp_path / "dev"
    dev.mkdir()
    (dev / "agent.yaml").write_text(
        "kind: harness\nharness: opencode\nmodel: z/glm-5.3\n", encoding="utf-8"
    )
    return tmp_path


def test_read_roles(tmp_path: Path):
    roles = read_roles(_agents(tmp_path))
    assert [r.name for r in roles] == ["architect", "dev"]
    a, d = roles
    assert (a.kind, a.model, a.harness, a.has_instructions) == (
        "proposer",
        "anthropic:glm-5.2",
        None,
        True,
    )
    assert (d.kind, d.harness, d.has_instructions) == ("harness", "opencode", False)


def test_role_dir_without_agent_yaml_raises(tmp_path: Path):
    _agents(tmp_path)
    (tmp_path / "ghost").mkdir()
    with pytest.raises(RegistryGap) as ei:
        read_roles(tmp_path)
    assert ei.value.role == "ghost"


def test_read_crew(tmp_path: Path):
    (tmp_path / "coder.yaml").write_text(
        "harness: opencode\nmodel: m\nwrites: true\n", encoding="utf-8"
    )
    (tmp_path / "critic.yaml").write_text("harness: claude_code\n", encoding="utf-8")
    crew = read_crew(tmp_path)
    assert [(c.name, c.writes) for c in crew] == [("coder", True), ("critic", False)]


def test_render_registry_tables_and_count():
    from pathlib import Path

    from scripts.docs.agent_registry import CrewRow, read_roles, render_registry

    roles = read_roles(Path("agents"))
    md = render_registry(roles, [CrewRow("coder", "opencode", "m", True)])
    assert "17 roles" in md
    assert "| architect | proposer |" in md
    assert "## Crew roles (E-88)" in md


def test_registry_count_equals_role_dirs():
    """Spec §9 exit: the registry count equals the agents/ role-dir count."""
    from pathlib import Path

    from scripts.docs.agent_registry import read_roles

    repo = Path(__file__).resolve().parents[2]
    roles = read_roles(repo / "agents")
    assert len(roles) == len([p for p in (repo / "agents").iterdir() if p.is_dir()])
