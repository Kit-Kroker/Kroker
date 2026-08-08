"""FR-902: missing baseline practice. Pure logic over a list of tracked paths.

Owns test discovery for the whole triage tier (find_test_files) -- build_probe
imports it. BrownKit ships bash, PowerShell and Python copies of its detectors;
FR-902's "exactly one implementation per signal" applies to our own code too,
and a second copy of test discovery inside the probe is the same failure at
smaller scale.
"""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Sequence

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import (
    FixClass, M_TESTS_PRESENT, SignalResult, TriageFinding,
)

SIGNAL_ID = "baseline"
VERSION = 2

_CI_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml",
             ".gitlab-ci.yml", "Jenkinsfile", ".circleci/config.yml",
             "azure-pipelines.yml", ".travis.yml")

_ENV_EXAMPLES = (".env.example", ".env.sample", ".env.template")


def find_test_files(paths: Sequence[str],
                    test_globs: Sequence[str]) -> list[str]:
    """Every tracked path matching one of the adapter's test conventions.

    Matches against the full posix-style repo-relative path AND the basename,
    because conventions come in both shapes ("tests/**/*.py" is a path glob,
    "test_*.py" is a basename glob)."""
    out: list[str] = []
    for p in paths:
        base = posixpath.basename(p)
        for glob in test_globs:
            if fnmatch.fnmatch(p, glob) or fnmatch.fnmatch(base, glob):
                out.append(p)
                break
    return out


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path)


def evaluate(paths: Sequence[str], gitignore_text: str,
             toolchain: ToolchainAdapter | None) -> SignalResult:
    """Static baseline checks. `paths` are repo-relative posix paths tracked at
    the pinned commit; `gitignore_text` is "" when no .gitignore is tracked."""
    tracked = set(paths)
    findings: list[TriageFinding] = []

    has_ci = any(fnmatch.fnmatch(p, g) for p in tracked for g in _CI_GLOBS)
    if not has_ci:
        findings.append(_finding(
            "no_ci", "medium",
            "No CI configuration found; nothing runs the suite on push.",
            FixClass.JUDGEMENT))

    if ".gitignore" not in tracked:
        findings.append(_finding(
            "gitignore_missing", "medium",
            "No .gitignore; build output and local env files are one "
            "`git add -A` away from being committed.",
            FixClass.MECHANICAL, path=".gitignore"))
    elif not any(line.strip().startswith(".env")
                 for line in gitignore_text.splitlines()):
        findings.append(_finding(
            "gitignore_missing_env", "high",
            ".gitignore does not cover .env files, which is how credentials "
            "reach a repository in the first place.",
            FixClass.MECHANICAL, path=".gitignore"))

    if not any(posixpath.basename(p).lower().startswith("readme")
               for p in tracked if "/" not in p):
        findings.append(_finding(
            "no_readme", "low", "No README at the repository root.",
            FixClass.JUDGEMENT))

    lockfiles = toolchain.lockfiles if toolchain else ()
    if lockfiles and not any(lf in tracked for lf in lockfiles):
        findings.append(_finding(
            "no_lockfile", "medium",
            f"No lockfile ({', '.join(lockfiles)}); dependency resolution is "
            f"not reproducible.",
            FixClass.JUDGEMENT))

    test_files = find_test_files(
        sorted(tracked), toolchain.test_globs if toolchain else ())
    if not test_files:
        findings.append(_finding(
            "no_tests", "high",
            "No test files found. Writing a suite is design work, not a "
            "mechanical patch.",
            FixClass.STRUCTURAL))

    # A committed .env is the signal that the project actually uses one; a
    # .gitignore that merely COVERS .env is universal hygiene, not evidence of
    # use (every clean Python repo gitignores .env). Flagging on the gitignore
    # would turn a clean repo into a finding.
    env_referenced = ".env" in tracked
    if env_referenced and not any(e in tracked for e in _ENV_EXAMPLES):
        findings.append(_finding(
            "no_env_example", "low",
            "The project uses a .env but ships no .env.example, so required "
            "configuration is undiscoverable.",
            FixClass.MECHANICAL))

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            # structure_discernible moved to the scaffold signal (E-41b,
            # spec D12): exactly one signal may own a readiness key, and the
            # sharpened dimension needs fingerprints this signal does not have.
            M_TESTS_PRESENT: Measurement.measured(float(len(test_files))),
        })
