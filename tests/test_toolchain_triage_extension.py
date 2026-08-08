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


# ---- E-41a-d adapter extension ---------------------------------------

from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter


class _Bare(ToolchainAdapter):
    """An adapter that has not thought about triage. It must instantiate and
    degrade, not fail (spec section 4)."""
    kind = None
    markers = ()

    def test_cmd(self, coverage: bool = True) -> str:
        return "true"

    def lint_cmd(self) -> str:
        return "true"

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        return "true"


def test_a_triage_unaware_adapter_degrades_rather_than_failing():
    a = _Bare()
    assert a.manifests == ()
    assert a.ecosystem is None
    assert a.source_extensions == ()
    assert a.max_file_loc == 0          # 0 disables the rule
    assert a.max_function_loc == 0
    assert a.min_clone_loc == 30
    assert a.function_spans("def f():\n    pass\n") is None


def test_python_declares_its_triage_facts():
    a = PythonToolchain()
    assert a.manifests == ("pyproject.toml", "requirements.txt")
    assert a.ecosystem == "PyPI"
    assert a.source_extensions == (".py",)
    assert a.max_file_loc == 800
    assert a.max_function_loc == 100


def test_function_spans_reports_name_and_line_range():
    text = ("import os\n"
            "\n"
            "def small():\n"
            "    return 1\n"
            "\n"
            "async def big():\n"
            "    x = 1\n"
            "    return x\n")
    spans = PythonToolchain().function_spans(text)
    assert ("small", 3, 4) in spans
    assert ("big", 6, 8) in spans


def test_function_spans_finds_methods_inside_classes():
    text = "class C:\n    def m(self):\n        return 1\n"
    assert ("m", 2, 3) in PythonToolchain().function_spans(text)


def test_unparseable_python_is_an_empty_list_not_none():
    # None means "this language has no parser here", which makes the metric
    # not_collected. A file we CAN parse and that simply is not valid Python
    # has no spans -- that is a measured zero, and conflating the two would
    # report an unparseable file as an unmeasurable language.
    assert PythonToolchain().function_spans("def (:\n") == []
