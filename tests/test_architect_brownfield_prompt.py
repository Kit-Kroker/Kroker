"""E-84 D13: the Architect instructions teach the delta."""

from __future__ import annotations

from pathlib import Path


def test_the_architect_instructions_teach_the_delta():
    text = Path("agents/architect/instructions.md").read_text()
    assert "delta" in text
    assert "added" in text
    assert "modified" in text
    assert "removed" in text
    assert "brownfield" in text.lower()
    assert "ls-tree" in text or "tree" in text
    assert "do not exist" in text.lower() or "not exist" in text.lower()
