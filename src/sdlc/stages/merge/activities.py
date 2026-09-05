"""Merge stage activities (spec A §5)."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from dataclasses import dataclass

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel
from temporalio import activity
from temporalio.exceptions import ApplicationError

from ...gate import (
    GateReport,
    QualityGateInput,
    evaluate_quality_gate,
)
from ...measurement import Measurement
from ...process import _bounded_shell
from ...stages.qa.activities import (
    _diagnostic_slice,
    _ensure_python_env,
    _stopped_early,
)
from ...stages.qa.models import QAReport
from ...toolchain.adapters import ToolchainKind, detect
from ...vcs.git import _git
from .models import CoverageReport


@dataclass
class CoverageInput:
    worktree: str
    changed_files: list[str]


@activity.defn
async def measure_coverage(inp: CoverageInput) -> CoverageReport:
    """Diff-scoped coverage from a Cobertura coverage.xml already emitted into
    the worktree by the run's test commands (FR-106). Minimal deterministic
    seam — pure filesystem read, reproducible across retries. Real per-stack
    instrumentation replaces only this body.

    The file is generated inside a harness worktree (untrusted, ARCHITECTURE.md
    §10), so it is parsed with defusedxml to block XXE / entity-expansion DoS.

    NOT_COLLECTED (check passes as a no-op) when there is no coverage.xml, it
    is unparseable/malicious, or none of the changed files appear in it; UNKNOWN
    when a changed file's line-rate is non-finite. An unbuilt measurement must
    never force a human override."""
    path = os.path.join(inp.worktree, "coverage.xml")
    if not os.path.isfile(path):
        return CoverageReport(
            coverage=Measurement.not_collected("no coverage.xml (seam not measured)")
        )
    try:
        root = DET.parse(path).getroot()
    except (DefusedXmlException, DET.ParseError, OSError):
        return CoverageReport(
            coverage=Measurement.not_collected("coverage.xml unparseable or unsafe")
        )
    rates: list[float] = []
    skipped_non_finite = 0
    for cls in root.iter("class"):
        fname = cls.get("filename") or ""
        if any(
            fname == cf or fname.endswith("/" + cf) or cf.endswith("/" + fname)
            for cf in inp.changed_files
        ):
            try:
                rate = float(cls.get("line-rate", "0"))
            except ValueError:
                continue
            if not math.isfinite(rate):
                # Hostile/corrupt input (nan, inf) -- never let it propagate
                # into a measured value, where e.g. `nan >= threshold` silently
                # evaluates False and fabricates an advisory failure. An
                # attempt DID produce output, so this is `unknown`, not
                # `not_collected` (FR-915).
                skipped_non_finite += 1
                continue
            rates.append(max(0.0, min(100.0, rate * 100.0)))
    if not rates:
        if skipped_non_finite:
            return CoverageReport(
                coverage=Measurement.unknown(
                    f"{skipped_non_finite} changed-file line-rate(s) non-finite"
                )
            )
        return CoverageReport(
            coverage=Measurement.not_collected(
                "no changed file found in coverage.xml (seam not measured)"
            )
        )
    # Unweighted mean of per-class line-rates — an approximation of true
    # diff coverage, not a line-weighted average. A 500-line file at 50%
    # and a 5-line file at 100% average to 75% here, though true line
    # coverage across both is ~50.5%. Acceptable for this seam; real
    # per-stack instrumentation should replace this with a weighted
    # (lines-covered / lines-valid) computation.
    pct = sum(rates) / len(rates)
    return CoverageReport(coverage=Measurement.measured(pct))


@dataclass
class IntegrationChecksInput:
    worktree: str
    changed_files: list[str]
    test_timeout_s: int = 600
    lint_timeout_s: int = 300
    setup_timeout_s: int = 300


class IntegrationChecks(BaseModel):
    toolchain: str | None = None  # ToolchainKind value, or None if undetected
    qa: QAReport
    lint_clean: bool
    lint_detail: str


# pytest usage-error exit code: unrecognized args (e.g. --cov when pytest-cov is
# absent) => 4, distinct from 1 (tests failed). A MISSING coverage plugin must
# degrade coverage to measured=False, never falsely fail the ABSOLUTE
# build_integration_green check — so on a 4 we re-run WITHOUT coverage for the
# honest green signal (FR-108 green-signal invariant).
_PYTEST_USAGE_ERROR = 4


@activity.defn
async def run_integration_checks(inp: IntegrationChecksInput) -> IntegrationChecks:
    """FR-108/ADR-15: resolve the toolchain by marker file and run
    coverage-instrumented tests + lint against the merged integration head.
    Emits coverage.xml into inp.worktree, where measure_coverage reads — the
    FR-106 gap this closes.

    toolchain=None (unrecognized marker) => tests/lint NOT re-run here; the
    workflow falls back to the per-task aggregate + standalone run_lint, exactly
    as before E-30. Never blocks on a language it doesn't know."""
    adapter = detect(inp.worktree)
    if adapter is None:
        return IntegrationChecks(
            toolchain=None,
            qa=QAReport(tests_passed=False, issues=["no toolchain adapter for this worktree"]),
            lint_clean=True,
            lint_detail="no toolchain adapter (not linted)",
        )

    env = None
    if adapter.kind is ToolchainKind.PYTHON:
        env, setup_error = await _ensure_python_env(inp.worktree, inp.setup_timeout_s)
        if setup_error:
            qa = QAReport(tests_passed=False, issues=[setup_error])
            return IntegrationChecks(
                toolchain=adapter.kind.value, qa=qa, lint_clean=False, lint_detail=setup_error
            )

    code, out = await _bounded_shell(
        adapter.test_cmd(coverage=True), inp.worktree, inp.test_timeout_s, env=env
    )
    if code == _PYTEST_USAGE_ERROR:
        # Coverage tooling unavailable — get the honest green signal without it.
        prefix = (
            "coverage instrumentation unavailable (pytest usage error); coverage left unmeasured\n"
        )
        code, out = await _bounded_shell(
            adapter.test_cmd(coverage=False), inp.worktree, inp.test_timeout_s, env=env
        )
        out = prefix + out
    failing = [ln.split(" ")[0] for ln in out.splitlines() if ln.startswith("FAILED")]
    qa = QAReport(
        tests_passed=code == 0,
        failing_tests=failing[:50],
        issues=[] if code == 0 else [_diagnostic_slice(out)],
        stopped_early=_stopped_early(out),
    )

    lcode, ldetail = await _bounded_shell(
        adapter.lint_cmd(), inp.worktree, inp.lint_timeout_s, env=env
    )
    return IntegrationChecks(
        toolchain=adapter.kind.value, qa=qa, lint_clean=lcode == 0, lint_detail=ldetail[-2000:]
    )


@dataclass
class PROpenInput:
    worktree: str
    title: str
    body: str
    base_branch: str


@activity.defn
async def open_pull_request(inp: PROpenInput) -> str:
    """Push the integration branch and open a PR for it.

    Preconditions first, and both non-retryable: a worker image without `gh`
    and a worktree without an `origin` are misconfigurations, not blips, so
    ACT's six attempts with backoff only delay a failure that is already
    decided. Checking `gh` *before* the push also keeps a missing binary from
    leaving a pushed branch on the remote with no PR pointing at it.

    `gh` is resolved through shutil.which rather than invoked by name: it is
    the same lookup the precondition needs, and on Windows CreateProcess
    appends only `.exe`, so a bare `["gh", ...]` misses a `gh.cmd` that is
    plainly on PATH.

    `gh pr create` is deliberately left retryable — unlike the preconditions
    it is a network call to GitHub, where a 5xx is worth another attempt. What
    must survive either way is the diagnostic: `check=True` raised a
    CalledProcessError whose str() is "returned non-zero exit status 1", so
    gh's own message was dropped on the way through Temporal (the hazard
    `_git`'s docstring documents, one seam over).
    """
    gh = shutil.which("gh")
    if gh is None:
        raise ApplicationError(
            "gh CLI not found on PATH: the worker cannot open a pull request "
            "without it (it is installed in the worker image; a source "
            "checkout needs it installed separately)",
            non_retryable=True,
        )

    remote = _git(["remote", "get-url", "origin"], inp.worktree)
    if remote.returncode != 0:
        raise ApplicationError(
            f"no 'origin' remote in {inp.worktree!r}: "
            f"{remote.stderr.strip() or remote.stdout.strip()}",
            non_retryable=True,
        )

    push = _git(["push", "-u", "origin", "HEAD"], inp.worktree)
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr.strip() or push.stdout.strip()}")

    # stdin=DEVNULL for the console-less-worker reason _git documents.
    pr = subprocess.run(
        [gh, "pr", "create", "--title", inp.title, "--body", inp.body, "--base", inp.base_branch],
        cwd=inp.worktree,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    if pr.returncode != 0:
        raise ApplicationError(f"gh pr create failed: {pr.stderr.strip() or pr.stdout.strip()}")
    return pr.stdout.strip()  # PR url


@activity.defn
async def evaluate_gate(inp: QualityGateInput) -> GateReport:
    """Activity wrapper over the pure DeterministicQualityGate."""
    return evaluate_quality_gate(inp.checks, inp.overrides)


ACTIVITIES = [
    measure_coverage,
    run_integration_checks,
    open_pull_request,
    evaluate_gate,
]

__all__ = [
    "ACTIVITIES",
    "CoverageInput",
    "IntegrationChecks",
    "IntegrationChecksInput",
    "PROpenInput",
    "evaluate_gate",
    "measure_coverage",
    "open_pull_request",
    "run_integration_checks",
]
