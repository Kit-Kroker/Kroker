"""Fake triage activities for the maintenance workflow tier (023a T017).

Deterministic by construction: each fake reads the FIXTURE REPO's real
committed state (via git plumbing, never mutating it), so a test's
narrative — "commit a build break, nudge, one incident" — flows through
the same observable facts the real signals would report. No subprocess
probe ever runs; the build-probe fake inspects the marker the
conftest's `commit_build_break` writes.

On replay the recorded results return, so the git reads execute once.
"""

from __future__ import annotations

from pathlib import Path

from temporalio import activity

from sdlc.measurement import Measurement
from sdlc.triage.activities import (
    TriageDependencyInput,
    TriagePin,
    TriagePinInput,
    TriageProbeInput,
    TriageSignalInput,
)
from sdlc.triage.models import SignalResult

from .conftest import (
    build_break_finding,
    credential_finding,
    env_file_findings,
    git,
)

BREAK_MARKER = "build break"


def _ok(signal: str, version: int, findings=None, metrics=None) -> SignalResult:
    return SignalResult(
        signal=signal,
        version=version,
        collected=Measurement.measured(float(len(findings or []))),
        findings=findings or [],
        metrics=metrics or {},
    )


def _tracked(repo_dir: str) -> set[str]:
    out = git(Path(repo_dir), "ls-files")
    return set(out.split())


@activity.defn(name="triage_resolve_commit")
async def fake_pin(inp: TriagePinInput) -> TriagePin:
    return TriagePin(
        commit_sha=git(Path(inp.repo_dir), "rev-parse", "HEAD").strip(), toolchain="python"
    )


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, metrics={"tests_present": Measurement.measured(1.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1, metrics={"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 2)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 2)


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    """Broken iff the fixture's build-break marker is committed."""
    pkg = Path(inp.repo_dir) / "src" / "fixture_pkg" / "__init__.py"
    broken = pkg.exists() and BREAK_MARKER in pkg.read_text(encoding="utf-8")
    metrics = {
        "buildable": Measurement.measured(0.0 if broken else 1.0),
        "runnable": Measurement.measured(0.0 if broken else 1.0),
    }
    return _ok("build_probe", 1, [build_break_finding()] if broken else [], metrics=metrics)


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    tracked = _tracked(inp.repo_dir)
    findings = []
    if ".env" in tracked:
        findings.extend(env_file_findings())
    if "config/settings.ini" in tracked:
        findings.append(credential_finding())
    return _ok("secrets", 3, findings)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp: TriageDependencyInput) -> SignalResult:
    # The workflow tier runs advisory_source=none (no OSV egress in tests):
    # the signal reads not configured, never a fault.
    return SignalResult(
        signal="dependencies",
        version=2,
        collected=Measurement.not_collected("advisory source is none (not configured)"),
    )


TRIAGE_ACTIVITIES = [
    fake_pin,
    fake_baseline,
    fake_scaffold,
    fake_misconfig,
    fake_outliers,
    fake_probe,
    fake_secrets,
    fake_deps,
]
