"""ToolchainAdapter: pure command/identity resolution (ADR-15, FR-108)."""
from sdlc.toolchain.adapters import (
    PythonToolchain, TOOLCHAINS, ToolchainKind, detect,
)


def test_detect_python_by_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n",
                                             encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_detect_returns_none_on_bare_dir(tmp_path):
    assert detect(str(tmp_path)) is None


def test_python_test_cmd_is_coverage_instrumented_by_default():
    cmd = PythonToolchain().test_cmd()
    assert "--cov" in cmd and "coverage.xml" in cmd


def test_python_test_cmd_plain_omits_coverage():
    cmd = PythonToolchain().test_cmd(coverage=False)
    assert "--cov" not in cmd and cmd.startswith("pytest")


def test_python_lint_cmd():
    assert PythonToolchain().lint_cmd() == "ruff check ."


def test_python_build_cmd_is_none():
    assert PythonToolchain().build_cmd() is None


def test_registry_has_python_marker():
    assert TOOLCHAINS[ToolchainKind.PYTHON].marker == "pyproject.toml"
