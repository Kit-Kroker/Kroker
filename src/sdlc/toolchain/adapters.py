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

import os
from abc import ABC, abstractmethod
from enum import Enum


class ToolchainKind(str, Enum):
    PYTHON = "python"
    # GO / TS / RUST are added by E-30a/b/c — each is the N-th adapter,
    # identical in shape, added on demand as the case corpus needs it.


class ToolchainAdapter(ABC):
    kind: ToolchainKind
    marker: str          # marker filename at the repo root detect() resolves by

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
    marker = "pyproject.toml"

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
        # canonical report the grader parses.
        return (f"pytest {oracle_path} -q "
                f"--junitxml={report_out} -p no:cacheprovider")


TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter] = {
    ToolchainKind.PYTHON: PythonToolchain(),
}


def detect(worktree: str) -> ToolchainAdapter | None:
    """Return the first adapter whose marker file exists at the worktree root,
    or None for an unrecognized/absent marker (caller degrades gracefully).

    Resolves by what was BUILT (marker file), never the contract's claimed
    stack — a marker/claim mismatch is itself a signal (ADR-15)."""
    for adapter in TOOLCHAINS.values():
        if os.path.isfile(os.path.join(worktree, adapter.marker)):
            return adapter
    return None
