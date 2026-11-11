"""base_locator_exists: per-language base locator judgment (DS6 pre-filter)."""

import inspect

from sdlc.toolchain.adapters import PythonToolchain


def test_default_is_isfile(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a_test.py").write_text("", encoding="utf-8")
    py = PythonToolchain()
    assert py.base_locator_exists(str(tmp_path), "a_test.py") is True
    assert py.base_locator_exists(str(tmp_path), "pkg") is False  # dir is not a file
    assert py.base_locator_exists(str(tmp_path), "nope.py") is False


def test_seam_routes_through_the_hook():
    src = inspect.getsource(__import__("sdlc.stages.merge.scoping", fromlist=["x"]))
    assert "adapter.base_locator_exists(" in src
    assert "os.path.isfile(os.path.join(base_wt, file))" not in src
