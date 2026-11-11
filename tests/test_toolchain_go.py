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


def test_go_parse_lint_objects_glued_without_separator(tmp_path):
    # Task-4 review follow-up, pinning the documented shape: go vet -json
    # emits one object per package concatenated with NOTHING between them --
    # never a JSON array, and the separator is incidental, not part of the
    # contract. The same fixtures glued with "" must yield the same rows as
    # the newline-joined variant above.
    a, b, c = tmp_path / "a.go", tmp_path / "b.go", tmp_path / "c.go"
    stream = "".join(
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


def test_go_parse_lint_exit_one_whitespace_only_stdout_fails_closed():
    # Task-4 review follow-up, committed: exit 1 with a whitespace-only stream
    # decodes to zero objects, so the code-1-with-empty-stdout rule must catch
    # it too, not only the exactly-empty case.
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_lint(1, "  \n\t ", "/x") is None


# --- E-30a test-id round-trip: collect / parse / selected ---------------------


def test_go_collect_ids_cmd_exact_string():
    # Go locators are import paths (Go tooling cannot attribute a test to a
    # file), and `go test` accepts import paths directly as package
    # arguments -- collect needs no path mapping at all.
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.collect_ids_cmd(["example.com/m/a", "example.com/m/b"]) == (
        'go test -list ".*" "example.com/m/a" "example.com/m/b"'
    )


def test_go_collect_ids_cmd_refuses_unsafe_paths():
    go = TOOLCHAINS[ToolchainKind.GO]
    with pytest.raises(ValueError, match="example.com/m;a"):
        go.collect_ids_cmd(["example.com/m;a"])


def test_go_parse_collected_ids_interleaved_ok_and_no_test_files():
    # Real `go test -list '.*' <pkgs>` shape: test names one per line, then
    # one tab-separated status line per package. Names accumulate since the
    # last status line; `ok\\t<pkg>` emits them keyed by import path,
    # `?\\t<pkg>` discards them (a package with no test files contributes
    # nothing). TestGamma under the ?-line must vanish while the names after
    # it accrue to the next ok line -- that interleaving is the point.
    out = "\n".join(
        (
            "TestAlpha",
            "TestBeta",
            "ok  \texample.com/m/a\t0.012s",
            "TestGamma",
            "?   \texample.com/m/b\t[no test files]",
            "TestDelta",
            "TestEpsilon",
            "ok  \texample.com/m/c\t0.003s",
            "?   \texample.com/m/d\t[no test files]",
        )
    )
    go = TOOLCHAINS[ToolchainKind.GO]
    assert go.parse_collected_ids(out) == {
        "example.com/m/a::TestAlpha",
        "example.com/m/a::TestBeta",
        "example.com/m/c::TestDelta",
        "example.com/m/c::TestEpsilon",
    }


def test_go_selected_tests_cmd_exact_string():
    # DS6 chunk re-run: ids group by the part before `::`; one -run regex
    # applies to every listed package, so names dedupe across packages into
    # one sorted alternation and packages dedupe into a sorted list. The
    # sorting is for determinism: the same chunk must produce a
    # byte-identical command on every run.
    go = TOOLCHAINS[ToolchainKind.GO]
    ids = [
        "example.com/m/b::TestGamma",
        "example.com/m/a::TestBeta",
        "example.com/m/a::TestAlpha",
        "example.com/m/a::TestBeta",  # duplicate id: alternation dedupes
    ]
    assert go.selected_tests_cmd(ids, ".sdlc-junit-base.xml") == (
        'go test -v -run "^(TestAlpha|TestBeta|TestGamma)$"'
        ' "example.com/m/a" "example.com/m/b"'
        " | go-junit-report > .sdlc-junit-base.xml"
    )


def test_go_selected_tests_cmd_refuses_unsafe_ids():
    go = TOOLCHAINS[ToolchainKind.GO]
    with pytest.raises(ValueError, match="TestA;rm"):
        go.selected_tests_cmd(["example.com/m/a::TestA;rm"], "j.xml")
