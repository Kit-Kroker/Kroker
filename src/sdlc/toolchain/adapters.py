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
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import Enum
from typing import Literal


class ToolchainKind(str, Enum):
    PYTHON = "python"
    # GO / TS / RUST are added by E-30a/b/c — each is the N-th adapter,
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
    manifests: tuple[str, ...] = ()          # files declaring direct deps
    ecosystem: str | None = None             # OSV ecosystem name
    source_extensions: tuple[str, ...] = ()  # what counts as source
    max_file_loc: int = 0                    # 0 disables the rule
    max_function_loc: int = 0                # 0 disables the rule
    min_clone_loc: int = 30                  # duplication window, in lines

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

    def classify_test_exit(
            self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
        """Whether the suite RAN, as distinct from whether it PASSED.

        Load-bearing for the triage `runnable` dimension: "tests ran and some
        failed" and "the suite could not be collected" are different readiness
        facts, and the exit-code mapping is per-language. The default is the
        conservative one for a language whose runner has not been mapped."""
        return "ran" if code == 0 else "failed_to_run"

    @abstractmethod
    def test_cmd(self, coverage: bool = True) -> str:
        """Test command. With coverage=True it MUST emit a Cobertura
        coverage.xml at the worktree root, where measure_coverage reads.
        coverage=False is the honest green-signal fallback when coverage
        tooling is unavailable (see run_integration_checks)."""

    @abstractmethod
    def lint_cmd(self) -> str:
        ...

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
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))

    def install_cmd(self, marker: str) -> str | None:
        if marker == "requirements.txt":
            return "pip install -r requirements.txt"
        # Non-editable: `pip install -e .` writes *.egg-info into the tree
        # under audit, and triage must not mutate what it measures. PEP 517
        # builds `pip install .` in a temporary directory.
        return "pip install ."

    def classify_test_exit(
            self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]:
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

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        # -p no:cacheprovider: never write .pytest_cache into the produced
        # repo (keeps the throwaway worktree clean). --junitxml lands the
        # canonical report the grader parses. -o junit_family=legacy: pytest's
        # default xunit2 family strips the testcase `file` attribute, which
        # grade_testcases_from_junit (oracle.py) relies on to build the
        # "file.py::test_name" node ids that tasks.yaml oracle_tests entries
        # reference -- legacy keeps that attribute on the report.
        return (f"pytest {oracle_path} -q "
                f"--junitxml={report_out} -p no:cacheprovider "
                f"-o junit_family=legacy")


TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter] = {
    ToolchainKind.PYTHON: PythonToolchain(),
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


def detect_with_marker_from_paths(
        paths: Sequence[str]) -> tuple[ToolchainAdapter, str] | None:
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
