"""Language-agnostic toolchain adapters (ADR-15, FR-108).

A ToolchainAdapter resolves the deterministic quality gate's stack-specific
verification commands (test / lint / build) from the produced repository's
marker file, so the gate grades whatever language was actually built.
Structurally identical to harness/adapters.py: an ABC + concrete adapters +
a module-level registry dict.

The adapter object is PURE — it produces command strings and identity only,
never runs a subprocess. Execution lives in Temporal activities
(activities.py), exactly as CodingHarness never runs in workflow code.
"""

from __future__ import annotations

import ast
import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from ..change_scope import normalize_path
from .junit import shell_safe


class ToolchainKind(StrEnum):
    PYTHON = "python"
    GO = "go"
    # TS / RUST are added by E-30b/c — each is the N-th adapter,
    # identical in shape, added on demand as the case corpus needs it.


class ToolchainAdapter(ABC):
    kind: ToolchainKind
    # candidate marker filenames at the repo root detect() resolves by --
    # any one present is enough; a project may use only one of several
    # valid conventions (e.g. Python: pyproject.toml OR requirements.txt).
    markers: tuple[str, ...]

    # E-41 (FR-902). Concrete defaults, not abstract: a new adapter that has
    # not thought about triage yet degrades to "no install command" and the
    # probe records not_collected, rather than failing to instantiate.
    test_globs: tuple[str, ...] = ()
    lockfiles: tuple[str, ...] = ()

    # E-41a-d (spec section 4). Same degradation rule: empty tuples and
    # disabled thresholds mean "rule skipped, metric not_collected", never a
    # silent zero. Language-level facts ONLY -- framework fingerprints and
    # misconfiguration rules live in their signal modules, because one
    # language serves many frameworks (spec D15).
    manifests: tuple[str, ...] = ()  # files declaring direct deps
    ecosystem: str | None = None  # OSV ecosystem name
    source_extensions: tuple[str, ...] = ()  # what counts as source
    max_file_loc: int = 0  # 0 disables the rule
    max_function_loc: int = 0  # 0 disables the rule
    min_clone_loc: int = 30  # duplication window, in lines

    def function_spans(self, text: str) -> list[tuple[str, int, int]] | None:
        """(name, first line, last line) for every function in `text`, or
        None when this language has no parser here.

        None is what makes E-41d's `oversized_function` metric
        not_collected rather than absent: a language we cannot parse is not
        a language with no long functions.

        Pure -- text in, spans out, no subprocess and no filesystem. The same
        kind of member as `classify_test_exit`: a per-language
        *interpretation*, not a command string (ADR-15, spec D15).
        """
        return None

    def install_cmd(self, marker: str) -> str | None:
        """Dependency-install command for the marker detect_with_marker
        matched, or None where the language has none. Takes the marker
        because one adapter can serve several conventions (Python:
        pyproject.toml vs requirements.txt) and the adapter stays pure --
        it never looks at the filesystem to decide."""
        return None

    def classify_test_exit(self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        """Whether the suite RAN, as distinct from whether it PASSED.

        Load-bearing for the triage `runnable` dimension: "tests ran and some
        failed" and "the suite could not be collected" are different readiness
        facts, and the exit-code mapping is per-language. The default is the
        conservative one for a language whose runner has not been mapped."""
        return "ran" if code == 0 else "failed_to_run"

    def base_locator_exists(self, root: str, locator: str) -> bool:
        """Whether a diff-scoped test locator's file exists at the base, as a
        per-language judgment. The Python-shaped default is a plain file
        check; a language whose test ids are not file paths (Go overrides
        this for import-path-keyed ids) redefines what "exists" means.

        The pre-filter is an optimization only: a locator judged absent
        short-circuits base corroboration for that failure, but the
        collect/re-run steps in the scoping pipeline remain the authoritative
        attribution (DS6) -- a wrong "exists" cannot mislabel a failure, only
        spend a base run on it.
        """
        return os.path.isfile(os.path.join(root, locator))

    @abstractmethod
    def test_cmd(self, coverage: bool = True) -> str:
        """Test command. With coverage=True it MUST emit a Cobertura
        coverage.xml at the worktree root, where measure_coverage reads.
        coverage=False is the honest green-signal fallback when coverage
        tooling is unavailable (see run_integration_checks)."""

    @abstractmethod
    def lint_cmd(self) -> str: ...

    # Diff-scoped gates (DS5/DS6). Declarative, so a language adds no gate code
    # (FR-108). E-30a/b/c adapters must implement every method below.
    lint_policy_globs: tuple[str, ...] = ()
    suppression_pattern: str = ""  # regex; "" = no inline suppression syntax

    @abstractmethod
    def lint_json_cmd(self) -> str:
        """Machine-readable lint over the cwd; exit 0 whether or not it found anything."""

    @abstractmethod
    def parse_lint(self, code: int, out: str, root: str) -> list[tuple[str, str, int]] | None:
        """(rule, repo-relative POSIX path, 1-based row) per finding. None = the
        tool failed (or reported an I/O error), never "no findings"."""

    @abstractmethod
    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        """The merge gate's whole-suite run: NO early stop of any kind (an
        early stop hides introduced failures behind pre-existing ones), per-test
        JUnit at junit_out, and coverage.xml when coverage=True."""

    @abstractmethod
    def collect_ids_cmd(self, paths: Sequence[str]) -> str: ...

    @abstractmethod
    def parse_collected_ids(self, out: str) -> set[str]: ...

    @abstractmethod
    def selected_tests_cmd(self, node_ids: Sequence[str], junit_out: str) -> str: ...

    @abstractmethod
    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        """Run ONLY the tests under oracle_path (a path relative to the
        worktree root), emitting a JUnit XML report at report_out. The
        held-out oracle grader (benchmarks/oracle.py) reads tests/failures/
        errors/skipped from that report. Canonical JUnit XML keeps the grade
        language-agnostic, exactly as Cobertura does for coverage."""

    def build_cmd(self) -> str | None:
        """Separate build step, or None where the language has none (Python)."""
        return None


class PythonToolchain(ToolchainAdapter):
    kind = ToolchainKind.PYTHON
    markers = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")

    test_globs = ("test_*.py", "*_test.py", "tests/**/*.py")
    # requirements.txt is deliberately NOT here: it is a manifest that may or
    # may not pin. Whether it pins is E-41a's dependency-health question.
    lockfiles = ("uv.lock", "poetry.lock", "Pipfile.lock")

    manifests = ("pyproject.toml", "requirements.txt")
    ecosystem = "PyPI"
    source_extensions = (".py",)
    # Absolute, not percentile (spec D14): Tier 0 asks what state this
    # repository is in, not which file is worst inside it, and E-44's
    # before/after delta needs numbers comparable across repositories.
    max_file_loc = 800
    max_function_loc = 100

    def function_spans(self, text: str) -> list[tuple[str, int, int]] | None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # We CAN parse Python; this file simply is not valid Python. That
            # is a measured zero spans, not an unmeasurable language, so it
            # must not return None.
            return []
        return sorted(
            (node.name, node.lineno, node.end_lineno or node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

    def install_cmd(self, marker: str) -> str | None:
        if marker == "requirements.txt":
            return "pip install -r requirements.txt"
        # Non-editable: `pip install -e .` writes *.egg-info into the tree
        # under audit, and triage must not mutate what it measures. PEP 517
        # builds `pip install .` in a temporary directory.
        return "pip install ."

    def classify_test_exit(self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        # pytest exit codes: 0 ok, 1 tests failed, 2 interrupted,
        # 3 internal error, 4 usage error, 5 no tests collected.
        if code in (0, 1):
            return "ran"
        if code == 5:
            return "no_tests"
        return "failed_to_run"

    def test_cmd(self, coverage: bool = True) -> str:
        # --maxfail bounds output like the per-task QA command. pytest-cov
        # drives coverage.py; --cov-report=xml writes Cobertura to coverage.xml
        # at cwd (the integration worktree measure_coverage reads).
        base = "pytest -q --maxfail=25"
        if coverage:
            return f"{base} --cov=. --cov-report=xml:coverage.xml"
        return base

    def lint_cmd(self) -> str:
        return "ruff check ."

    lint_policy_globs = ("pyproject.toml", "ruff.toml", ".ruff.toml", "*/ruff.toml", "*/.ruff.toml")
    suppression_pattern = r"#\s*noqa\b"

    _PYTEST_GATE = (
        "pytest -q -p no:cacheprovider --continue-on-collection-errors -o junit_family=legacy"
    )

    def lint_json_cmd(self) -> str:
        return "ruff check --output-format json --exit-zero --no-cache ."

    def parse_lint(self, code: int, out: str, root: str) -> list[tuple[str, str, int]] | None:
        if code != 0:
            return None
        m = re.search(r"(?m)^\[", out)
        if m is None:
            return None
        try:
            rows = json.loads(out[m.start() :])
        except ValueError:
            return None
        found: list[tuple[str, str, int]] = []
        for row in rows:
            rule = row.get("code") or "syntax-error"
            if rule == "E902":  # ruff's I/O error: the tool could not read a file
                return None
            path = normalize_path(os.path.relpath(row["filename"], root))
            found.append((rule, path, int(row["location"]["row"])))
        return sorted(found)

    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        base = f"{self._PYTEST_GATE} --junitxml={junit_out}"
        return f"{base} --cov=. --cov-report=xml:coverage.xml" if coverage else base

    def collect_ids_cmd(self, paths: Sequence[str]) -> str:
        unsafe = [p for p in paths if not shell_safe(p)]
        if unsafe:
            raise ValueError(f"refusing to shell-interpolate unsafe test ids: {unsafe[:3]}")
        quoted = " ".join(f'"{p}"' for p in paths)
        return (
            f"pytest --collect-only -q -p no:cacheprovider --continue-on-collection-errors {quoted}"
        )

    def parse_collected_ids(self, out: str) -> set[str]:
        return {
            ln.strip()
            for ln in out.splitlines()
            if "::" in ln and not ln[:1].isspace() and not ln.startswith(("ERROR", "="))
        }

    def selected_tests_cmd(self, node_ids: Sequence[str], junit_out: str) -> str:
        unsafe = [p for p in node_ids if not shell_safe(p)]
        if unsafe:
            raise ValueError(f"refusing to shell-interpolate unsafe test ids: {unsafe[:3]}")
        quoted = " ".join(f'"{n}"' for n in node_ids)
        return f"{self._PYTEST_GATE} --junitxml={junit_out} {quoted}"

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        # -p no:cacheprovider: never write .pytest_cache into the produced
        # repo (keeps the throwaway worktree clean). --junitxml lands the
        # canonical report the grader parses. -o junit_family=legacy: pytest's
        # default xunit2 family strips the testcase `file` attribute, which
        # grade_testcases_from_junit (oracle.py) relies on to build the
        # "file.py::test_name" node ids that tasks.yaml oracle_tests entries
        # reference -- legacy keeps that attribute on the report.
        return (
            f"pytest {oracle_path} -q "
            f"--junitxml={report_out} -p no:cacheprovider "
            f"-o junit_family=legacy"
        )


class GoToolchain(ToolchainAdapter):
    """The second adapter (E-30a) and the first real test of the abstraction
    on a non-Python language: the gate must grade a go.mod repo with zero
    gate/workflow changes (FR-108). Go is also package-shaped where Python is
    file-shaped -- its test ids are import paths, not file paths -- which is
    exactly the assumption the base_locator_exists hook exists to relax.

    `function_spans` is deliberately the inherited None: there is no Go
    parser here, so `oversized_function` reads not_collected -- a language we
    cannot parse is not a language with no long functions, and a fake zero
    would be a vacuous pass.

    The command members land later in the E-30a increment; until each lands,
    its stub raises rather than guess a command string -- the same fail-closed
    rule as a missing external tool downstream (a collection failure, never a
    vacuous pass).
    """

    kind = ToolchainKind.GO
    markers = ("go.mod",)

    test_globs = ("*_test.go",)
    lockfiles = ("go.sum",)

    manifests = ("go.mod",)
    ecosystem = "Go"
    source_extensions = (".go",)
    # Same ceilings as the Python reference (spec D14): the numbers are
    # policy, not language facts, and stay comparable across repositories.
    max_file_loc = 800
    max_function_loc = 100

    def install_cmd(self, marker: str) -> str | None:
        # `go mod download` fills the module cache from go.mod's pinned
        # requires and does not mutate the tree under audit (go get would).
        return "go mod download"

    def classify_test_exit(self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        # `go test`: 0 ok, 1 tests failed. Unlike pytest there is NO no-tests
        # exit -- a package without tests reports "no test files" and exits 0.
        return "ran" if code in (0, 1) else "failed_to_run"

    # Shared by both coverage branches: one constant so the converter
    # invocation cannot drift between them.
    _GOCOVER = "gocover-cobertura < cover.out > coverage.xml"

    def test_cmd(self, coverage: bool = True) -> str:
        # -covermode=atomic: `go test` runs packages (and t.Parallel tests)
        # concurrently, and the default `set` mode's counter updates race and
        # undercount -- atomic keeps the profile honest under that default.
        base = "go test ./..."
        if coverage:
            return f"{base} -coverprofile=cover.out -covermode=atomic && {self._GOCOVER}"
        return base

    def lint_cmd(self) -> str:
        return "go vet ./..."

    def lint_json_cmd(self) -> str:
        # Unlike ruff there is no --exit-zero: `go vet -json` exits 1 when it
        # finds anything and streams one JSON object per package on stdout.
        # That nonzero exit is findings, not tool failure -- interpreting it
        # is parse_lint's contract, which owns this stream.
        return "go vet -json ./..."

    def parse_lint(self, code: int, out: str, root: str) -> list[tuple[str, str, int]] | None:
        # Only 0 (clean) and 1 (findings found) are interpreted; any other
        # exit is a tool failure before finding interpretation even starts.
        if code not in (0, 1):
            return None
        # vet streams one top-level JSON object per package, in completion
        # order and concatenated with no separator -- never a JSON array --
        # so the stream must be decoded incrementally with raw_decode;
        # json.loads would see a single invalid document.
        decoder = json.JSONDecoder()
        pos = 0
        packages: list[dict] = []
        try:
            while True:
                while pos < len(out) and out[pos].isspace():
                    pos += 1
                if pos >= len(out):
                    break
                obj, pos = decoder.raw_decode(out, pos)
                packages.append(obj)
        except ValueError:
            # Garbage anywhere in the stream means it was truncated or
            # corrupted mid-run: the objects decoded so far cannot be proven
            # to be the complete set, so fail closed (None = tool failure)
            # rather than grade a partial read.
            return None
        if code == 1 and not packages:
            # Exit 1 claims findings; an empty stdout says nothing. A claim
            # contradicted by its evidence is ambiguity -- None (NOT_COLLECTED
            # downstream), never a vacuous clean pass.
            return None
        found: list[tuple[str, str, int]] = []
        for pkg in packages:
            for report in pkg.values():
                for d in report.get("diagnostics", []):
                    loc = d["location"]
                    rule = d.get("category") or "vet"
                    # vet reports absolute filenames; the gate speaks in
                    # repo-relative POSIX paths, so relativize against the
                    # worktree root and normalize.
                    path = normalize_path(os.path.relpath(loc["file"]["filename"], root))
                    found.append((rule, path, int(loc["line"])))
        return sorted(found)

    def integration_test_cmd(self, junit_out: str, coverage: bool = True) -> str:
        """The merge gate's whole-suite run, Go-shaped.

        No early stop exists in `go test` to disable: it runs every matched
        package even after another package failed, so the no-early-stop rule
        is the language's natural behavior, not a flag.

        The pipe's exit is `go-junit-report`'s (0), never `go test`'s -- the
        exit says nothing about test outcomes. Outcomes come from the JUnit
        file at junit_out, which `_head_run` already treats as ground truth.
        """
        unsafe = [p for p in (junit_out,) if not shell_safe(p)]
        if unsafe:
            raise ValueError(f"refusing to shell-interpolate unsafe test ids: {unsafe[:3]}")
        # Pipes, &&, <, > are the only shell syntax here -- all cmd.exe-valid,
        # since workers run on Windows. Nothing needs quoting: guarded paths
        # interpolate verbatim (where this adapter does quote args, the rule
        # is double quotes only -- cmd.exe- and POSIX-compatible).
        if coverage:
            return (
                "go test -v ./... -coverprofile=cover.out -covermode=atomic"
                f" | go-junit-report > {junit_out} && {self._GOCOVER}"
            )
        return f"go test -v ./... | go-junit-report > {junit_out}"

    def collect_ids_cmd(self, paths: Sequence[str]) -> str:
        raise NotImplementedError("GoToolchain.collect_ids_cmd lands with E-30a's test-id members")

    def parse_collected_ids(self, out: str) -> set[str]:
        raise NotImplementedError(
            "GoToolchain.parse_collected_ids lands with E-30a's test-id members"
        )

    def selected_tests_cmd(self, node_ids: Sequence[str], junit_out: str) -> str:
        raise NotImplementedError(
            "GoToolchain.selected_tests_cmd lands with E-30a's test-id members"
        )

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        # Same pipe exit semantics as integration_test_cmd: the shell reports
        # go-junit-report's 0; the oracle grader reads outcomes from the JUnit
        # report, never from the exit code. -v is the per-test verbosity
        # go-junit-report parses into that report.
        unsafe = [p for p in (oracle_path, report_out) if not shell_safe(p)]
        if unsafe:
            raise ValueError(f"refusing to shell-interpolate unsafe test ids: {unsafe[:3]}")
        return f"go test -v ./{oracle_path}/... | go-junit-report > {report_out}"

    def build_cmd(self) -> str:
        # The first non-None build command: Go has no interpreter stage, so
        # `go build ./...` compiling every package is the gate's first
        # does-this-even-build fact (the triage consumer already handles it).
        return "go build ./..."


TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter] = {
    ToolchainKind.PYTHON: PythonToolchain(),
    ToolchainKind.GO: GoToolchain(),
}


def detect_with_marker(worktree: str) -> tuple[ToolchainAdapter, str] | None:
    """Return (adapter, the marker filename that matched) or None.

    E-41 needs to know WHICH marker matched, because install_cmd differs
    between a packaging marker and a requirements file while the adapter
    itself stays pure. detect() is the unchanged one-value form."""
    for adapter in TOOLCHAINS.values():
        for marker in adapter.markers:
            if os.path.isfile(os.path.join(worktree, marker)):
                return adapter, marker
    return None


def detect_with_marker_from_paths(paths: Sequence[str]) -> tuple[ToolchainAdapter, str] | None:
    """The pinned-commit form of detect_with_marker: resolve (adapter, marker)
    from repo-relative tracked paths instead of statting a checkout.

    Markers are root-level files, so a marker is present at the pinned commit
    iff its bare name is among the root-level paths (``git ls-tree`` emits
    forward-slash repo-relative paths, root files carry no separator). Triage
    signals over a pinned commit MUST use this, not detect_with_marker on the
    repo_dir: the operator's live working checkout can diverge from commit_sha,
    so resolving the toolchain from it produces false findings (spec D6)."""
    root = {p for p in paths if "/" not in p}
    for adapter in TOOLCHAINS.values():
        for marker in adapter.markers:
            if marker in root:
                return adapter, marker
    return None


def detect(worktree: str) -> ToolchainAdapter | None:
    """Return the first adapter whose marker file exists at the worktree root,
    or None for an unrecognized/absent marker (caller degrades gracefully).

    Resolves by what was BUILT (marker file), never the contract's claimed
    stack — a marker/claim mismatch is itself a signal (ADR-15)."""
    found = detect_with_marker(worktree)
    return found[0] if found else None
