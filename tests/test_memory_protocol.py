import pytest

from sdlc.memory.protocol import Memory


def test_memory_is_abstract():
    with pytest.raises(TypeError):
        Memory()


def test_memory_declares_all_four_operations():
    for name in ("recall", "retain", "reflect", "current_watermark"):
        assert name in Memory.__abstractmethods__
