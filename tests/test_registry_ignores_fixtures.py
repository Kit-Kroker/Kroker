"""A fixtures/ directory beside instructions.md must not break the loader:
fixtures live inside the role folder, and the loader only reads agent.yaml /
instructions.md / agent.py."""

from sdlc.agents.loader import load_registry
from tests.conftest import write_registry_dir


def test_load_registry_ignores_a_fixtures_dir(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    fx = root / "reviewer" / "fixtures"
    fx.mkdir()
    (fx / "add-login.json").write_text('{"role": "reviewer"}', encoding="utf-8")
    roles = load_registry(root)  # must not raise
    assert "reviewer" in roles
