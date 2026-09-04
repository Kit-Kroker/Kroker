# tests/core/test_models_module_is_gone.py
import importlib
import pathlib

import pytest


def test_the_monolith_is_deleted():
    assert not pathlib.Path("src/sdlc/models.py").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("sdlc.models")


def test_no_import_still_resolves_to_the_deleted_monolith():
    # `from .models import` inside a subpackage is that package's OWN models
    # module and is fine. Only the paths that used to reach src/sdlc/models.py
    # are defects: `from ..models import` in a subpackage, and
    # `from .models import` in a module sitting directly in src/sdlc/.
    offenders = []
    for p in pathlib.Path("src/sdlc").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "from ..models import" in text:
            offenders.append(str(p))
        if p.parent.name == "sdlc" and "from .models import" in text:
            offenders.append(str(p))
    assert offenders == [], offenders
