"""GoToolchain: identity, triage fields, install/build, exit classification (E-30a)."""

import json

import pytest

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


# --- E-30a command members ---------------------------------------------------


def test_go_test_cmd_exact_strings():
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.test_cmd(True) == (
        "go test ./... -coverprofile=cover.out -covermode=atomic"
        " && gocover-cobertura < cover.out > coverage.xml"
    )
    assert go.test_cmd(False) == "go test ./..."


def test_go_lint_cmds_exact_strings():
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.lint_cmd() == "go vet ./..."
    assert go.lint_json_cmd() == "go vet -json ./..."


def test_go_integration_test_cmd_exact_strings():
    go = TOOLCHAINS[ToolchainKind.GO]
    assert (
        go.integration_test_cmd("junit.xml", True)
        == "go test -v ./... -coverprofile=cover.out -covermode=atomic"
        " | go-junit-report > junit.xml"
        " && gocover-cobertura < cover.out > coverage.xml"
    )
    assert go.integration_test_cmd("junit.xml", False) == (
        "go test -v ./... | go-junit-report > junit.xml"
    )


def test_go_oracle_test_cmd_exact_string():
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.oracle_test_cmd("internal/foo", "report.xml") == (
        "go test -v ./internal/foo/... | go-junit-report > report.xml"
    )


def test_go_cmd_members_refuse_unsafe_interpolation():
    # junit_out / oracle_path / report_out are interpolated into shell
    # commands, so anything the shell_safe allowlist rejects is a ValueError
    # refusal -- never an escaped guess at what the caller meant.
    go = TOOLCHAINS[ToolchainKind.GO]
    with pytest.raises(ValueError):
        go.oracle_test_cmd("a;rm", "r.xml")
    with pytest.raises(ValueError):
        go.oracle_test_cmd("internal/foo", "r;xml")
    with pytest.raises(ValueError):
        go.integration_test_cmd("j;xml", True)


def test_registry_lists_python_first():
    assert list(TOOLCHAINS)[0] is ToolchainKind.PYTHON


# --- E-30a parse_lint: the `go vet -json` stream ------------------------------


def _vet_package(pkg: str, category: str | None, filename: str, line: int) -> str:
    # One top-level vet JSON object: keyed by import path, diagnostics carry
    # absolute file locations. category=None omits the key entirely -- vet
    # emits "" or omits it depending on the analyzer.
    d: dict = {
        "message": "m",
        "location": {"file": {"filename": filename}, "line": line, "column": 1},
    }
    if category is not None:
        d["category"] = category
    return json.dumps({pkg: {"diagnostics": [d]}})


def test_go_parse_lint_decodes_concatenated_package_objects(tmp_path):
    # `go vet -json` streams one object per package, glued together with no
    # separator -- never a JSON array. Exit 1 means findings, not tool
    # failure, so code 1 with a decodable stream must parse to rows: empty
    # and missing categories both fall back to "vet", absolute filenames
    # come back repo-relative POSIX, and rows are sorted.
    a, b, c = tmp_path / "a.go", tmp_path / "b.go", tmp_path / "c.go"
    stream = "\n".join(
        (
            _vet_package("example.com/m/a", "printf", str(a), 42),
            _vet_package("example.com/m/b", "", str(b), 7),
            _vet_package("example.com/m/c", None, str(c), 10),
        )
    )
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_lint(1, stream, str(tmp_path)) == [
        ("printf", "a.go", 42),
        ("vet", "b.go", 7),
        ("vet", "c.go", 10),
    ]


def test_go_parse_lint_clean_exit_is_empty_measured_list():
    # Code 0 with empty stdout: vet ran and found nothing -- a measured
    # clean pass ([]), not a collection failure (None).
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_lint(0, "", "/x") == []


def test_go_parse_lint_exit_one_with_empty_stdout_fails_closed():
    # Exit 1 claims findings; an empty stdout says nothing. A claim
    # contradicted by its evidence is ambiguity -- None (NOT_COLLECTED
    # downstream), never a vacuous clean pass.
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_lint(1, "", "/x") is None


def test_go_parse_lint_exit_two_is_tool_failure():
    # Only 0 and 1 are interpreted; anything else is vet failing before any
    # finding interpretation is possible.
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_lint(2, "vet: bad flag", "/x") is None


def test_go_parse_lint_trailing_garbage_fails_closed():
    # Garbage after valid objects means the stream was truncated or
    # corrupted: the set decoded so far cannot be proven complete, so the
    # whole read is discarded (None) rather than graded partial.
    go = TOOLCHAINS[ToolchainKind.GO]
    stream = _vet_package("example.com/m/a", "printf", "/x/a.go", 1) + "\ntrailing{garbage"
    assert go.parse_lint(1, stream, "/x") is None
