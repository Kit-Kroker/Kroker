# tests/core/test_models_module_is_gone.py
import importlib
import pathlib

import pytest


def test_the_monolith_is_deleted():
    assert not pathlib.Path("src/sdlc/models.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.models")


def test_no_import_still_resolves_to_the_deleted_monolith():
    # Only relative imports that resolve back up to src/sdlc/models.py are defects:
    # at depth N from src/sdlc/ (where direct files have depth 1), exactly N leading dots
    # ('from ' + '.' * N + 'models import') would reach the deleted monolith.
    offenders = []
    root = pathlib.Path("src/sdlc")
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        depth = len(p.relative_to(root).parts)
        target = f"from {'.' * depth}models import"
        if target in text:
            offenders.append(str(p))
    assert offenders == [], offenders
