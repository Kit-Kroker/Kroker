"""E-41's additions to the FR-108 adapter. classify_test_exit carries the
weight: pytest exits 1 for test failures and 2/3/4 for collection errors, and
"the suite ran and failed" is a different readiness fact from "the suite could
not run".
"""
import pytest

from sdlc.toolchain.adapters import (
    PythonToolchain, ToolchainKind, detect, detect_with_marker,
    detect_with_marker_from_paths,
)


def test_install_cmd_for_requirements_uses_the_requirements_file():
    assert PythonToolchain().install_cmd("requirements.txt") == (
        "pip install -r requirements.txt")


@pytest.mark.parametrize("marker", ["pyproject.toml", "setup.py", "setup.cfg"])
def test_install_cmd_for_packaging_markers_is_non_editable(marker):
    # Non-editable on purpose: `pip install -e .` writes *.egg-info into the
    # repository under audit; PEP 517 builds `pip install .` in a temp dir.
    assert PythonToolchain().install_cmd(marker) == "pip install ."


@pytest.mark.parametrize("code,expected", [
    (0, "ran"),            # all passed
    (1, "ran"),            # tests failed -- the suite still RAN
    (2, "failed_to_run"),  # interrupted
    (3, "failed_to_run"),  # internal error
    (4, "failed_to_run"),  # usage error
    (5, "no_tests"),       # nothing collected
])
def test_classify_test_exit(code, expected):
    assert PythonToolchain().classify_test_exit(code) == expected


def test_python_declares_test_globs_and_lockfiles():
    tc = PythonToolchain()
    assert "test_*.py" in tc.test_globs
    assert "uv.lock" in tc.lockfiles


def test_detect_with_marker_returns_which_marker_matched(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    found = detect_with_marker(str(tmp_path))
    assert found is not None
    adapter, marker = found
    assert adapter.kind is ToolchainKind.PYTHON
    assert marker == "requirements.txt"


def test_detect_with_marker_is_none_for_unrecognized_tree(tmp_path):
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    assert detect_with_marker(str(tmp_path)) is None


def test_detect_still_returns_just_the_adapter(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect(str(tmp_path)).kind is ToolchainKind.PYTHON


def test_detect_with_marker_from_paths_matches_a_root_marker():
    found = detect_with_marker_from_paths(
        ["pyproject.toml", "src/app.py", "README.md"])
    assert found is not None
    adapter, marker = found
    assert adapter.kind is ToolchainKind.PYTHON
    assert marker == "pyproject.toml"


def test_detect_with_marker_from_paths_ignores_a_nested_marker():
    # A marker nested under a subdir is not a root-level toolchain marker.
    assert detect_with_marker_from_paths(
        ["src/pyproject.toml", "app.py"]) is None


def test_detect_with_marker_from_paths_is_none_for_unrecognized_paths():
    assert detect_with_marker_from_paths(
        ["README.md", "docs/guide.md"]) is None
