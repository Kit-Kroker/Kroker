# tests/test_harness_adapter_layout.py
import importlib
import pathlib

import pytest


def test_adapters_module_is_gone():
    assert not pathlib.Path("src/sdlc/harness/adapters.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.harness.adapters")


def test_registry_still_resolves_every_harness_kind():
    from sdlc.core.models import HarnessKind
    from sdlc.harness.claude_code import ClaudeCodeHarness
    from sdlc.harness.cursor import CursorHarness
    from sdlc.harness.opencode import OpenCodeHarness
    from sdlc.harness.registry import HARNESSES

    # CREW is deliberately absent from HARNESSES -- it is a composition mode,
    # not a CLI, so there is no subprocess to build (models.py:41-44).
    assert HarnessKind.CREW not in HARNESSES
    assert isinstance(HARNESSES[HarnessKind.CLAUDE_CODE], ClaudeCodeHarness)
    assert isinstance(HARNESSES[HarnessKind.OPENCODE], OpenCodeHarness)
    assert isinstance(HARNESSES[HarnessKind.CURSOR], CursorHarness)


def test_each_module_is_under_the_ceiling():
    for name in ("base", "claude_code", "opencode", "cursor", "registry"):
        path = pathlib.Path(f"src/sdlc/harness/{name}.py")
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, name
