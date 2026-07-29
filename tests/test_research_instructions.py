import pytest
from pathlib import Path

def test_instructions_updated():
    instructions = Path("agents/research/instructions.md").read_text()
    assert "CodeMode" in instructions or "run_code" in instructions
    assert "ExaSearch" in instructions or "deep_search" in instructions
    assert "web_search" not in instructions # Should be replaced by exa search reference
    assert "$SDLC_RUNS_ROOT" in instructions
    assert "sha256" in instructions
