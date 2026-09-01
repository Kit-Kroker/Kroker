"""ToolchainAdapter: pure command/identity resolution (ADR-15, FR-108)."""

from sdlc.toolchain.adapters import (
    TOOLCHAINS,
    PythonToolchain,
    ToolchainKind,
    detect,
)


def test_detect_python_by_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_detect_returns_none_on_bare_dir(tmp_path):
    assert detect(str(tmp_path)) is None


def test_detect_python_by_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_detect_python_by_setup_py(tmp_path):
    (tmp_path / "setup.py").write_text("", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_detect_python_by_setup_cfg(tmp_path):
    (tmp_path / "setup.cfg").write_text("", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


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


def test_registry_has_python_markers():
    assert TOOLCHAINS[ToolchainKind.PYTHON].markers == (
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
    )


def test_python_oracle_test_cmd_targets_path_and_emits_junit():
    cmd = PythonToolchain().oracle_test_cmd("oracle", "oracle-report.xml")
    assert cmd.startswith("pytest oracle")
    assert "--junitxml=oracle-report.xml" in cmd
    # never pollute the produced repo with a pytest cache
    assert "-p no:cacheprovider" in cmd
    # the oracle run is NOT coverage-instrumented (that is test_cmd's job)
    assert "--cov" not in cmd
