"""Activities of the FR-205 validators library (`sdlc.validators.activities`).

Called directly as plain functions here (no worker): the contract under test
is the mapping itself; the registration test only pins that the worker boot
path picks the module's ACTIVITIES up.
"""

from __future__ import annotations

from sdlc.validators import ACTIVITIES
from sdlc.validators.activities import paths_exist


def test_paths_exist_maps_existence(tmp_path):  # direct activity-function call, no worker
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["src/app.py", "src/missing.py"]) == {
        "src/app.py": True,
        "src/missing.py": False,
    }


def test_paths_exist_maps_empty_and_dot_prefixed_tokens(tmp_path):
    """Empty tokens map to False -- they must never resolve to the repo root."""
    (tmp_path / "app.py").write_text("x")
    assert paths_exist(str(tmp_path), ["", "  ", "./app.py"]) == {
        "": False,
        "  ": False,
        "./app.py": True,
    }


def test_validators_package_exports_activities_list():
    assert ACTIVITIES == [paths_exist]


def test_worker_registers_paths_exist():
    from sdlc.worker import get_worker_activities

    assert any(fn.__name__ == "paths_exist" for fn in get_worker_activities())
