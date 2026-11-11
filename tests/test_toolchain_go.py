"""GoToolchain: identity, triage fields, install/build, exit classification (E-30a)."""

from sdlc.toolchain.adapters import (
    TOOLCHAINS,
    ToolchainKind,
    detect,
)


def test_detect_go_by_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.GO


def test_detect_prefers_python_when_both_markers_exist(tmp_path):
    # Registry order is the tiebreak: Python landed first (E-30) and must keep
    # resolving repos it already graded, even when a go.mod also appears.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("", encoding="utf-8")
    a = detect(str(tmp_path))
    assert a is not None and a.kind is ToolchainKind.PYTHON


def test_registry_go_identity_and_triage_fields():
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.kind is ToolchainKind.GO
    assert go.markers == ("go.mod",)
    assert go.lockfiles == ("go.sum",)
    assert go.manifests == ("go.mod",)
    assert go.ecosystem == "Go"
    assert go.source_extensions == (".go",)
    assert go.test_globs == ("*_test.go",)
    # Same absolute ceilings as the Python reference: policy, not language facts.
    assert go.max_file_loc == 800
    assert go.max_function_loc == 100


def test_go_function_spans_is_inherited_none():
    # No Go parser here: the oversized_function metric must read not_collected,
    # never a fake zero (a language we cannot parse is not a language with no
    # long functions).
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.function_spans("func F() {}") is None


def test_go_install_cmd():
    assert TOOLCHAINS[ToolchainKind.GO].install_cmd("go.mod") == "go mod download"


def test_go_build_cmd():
    assert TOOLCHAINS[ToolchainKind.GO].build_cmd() == "go build ./..."


def test_go_classify_test_exit_has_no_no_tests():
    # `go test`: 0 ok, 1 tests failed. Unlike pytest there is NO no-tests exit:
    # a package without tests reports "no test files" and exits 0, so code 5
    # (pytest's no_tests) can only mean failure-to-run in Go.
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.classify_test_exit(0) == "ran"
    assert go.classify_test_exit(1) == "ran"
    for code in (2, 5):
        assert go.classify_test_exit(code) == "failed_to_run"
