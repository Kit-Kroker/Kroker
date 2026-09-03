# tests/test_board_project_key.py
"""Board identity is its own field — not borrowed from the memory bank."""

from sdlc.core.models import (
    PipelineConfig,
)


def test_project_key_defaults_to_default():
    assert PipelineConfig().project_key == "default"


def test_project_key_is_settable():
    assert PipelineConfig(project_key="kroker").project_key == "kroker"


def test_project_key_is_distinct_from_memory_project_bank():
    """MemoryConfig.project_bank addresses Hindsight; project_key addresses
    the board. Sharing one identifier across two stores by accident is the
    bug this test exists to prevent."""
    cfg = PipelineConfig(project_key="kroker")
    assert cfg.project_key != cfg.memory.project_bank
