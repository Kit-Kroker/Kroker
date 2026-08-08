"""TriageWorkflow (E-42) -- Tier 0's assess half.

Deterministic by construction: no model call, no proposer, no confidence.
It pins a commit, fans out E-41's hygiene signals, and hands the results to
compute_readiness, which stays the only producer of a Verdict.

Operator-run only. triage_build_probe executes the triaged repository's own
code as the worker user with network access (NFR-9); E-57 and E-21 are what
remove that debt.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..measurement import Measurement
    from ..models import GateSettings
    from ..triage.activities import (
        TriageDependencyInput, TriagePin, TriagePinInput, TriageProbeInput,
        TriageSignalInput, triage_baseline, triage_build_probe,
        triage_dependencies, triage_misconfig, triage_outliers,
        triage_resolve_commit, triage_scaffold, triage_secrets,
    )
    from ..triage.models import RepoTriage, SignalResult, compute_readiness
    from ..triage.registry import SIGNALS
    from .gates import GateHost

# Read-only and idempotent -- retrying is free.
PIN_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
               retry_policy=RetryPolicy(maximum_attempts=3))
# Deterministic given a tree and a sha; the retry covers FS/git blips only.
SIGNAL_ACT = dict(start_to_close_timeout=timedelta(minutes=10),
                  retry_policy=RetryPolicy(maximum_attempts=2))
# The only signal doing network I/O (E-41a's AdvisorySource).
DEPS_ACT = dict(start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(maximum_attempts=3))
# ONE attempt, per triage_build_probe's own docstring: a ten-minute timeout
# retried three times is a thirty-minute triage, and a deterministic build
# failure does not become a success on attempt two.
PROBE_ACT = dict(start_to_close_timeout=timedelta(minutes=40),
                 retry_policy=RetryPolicy(maximum_attempts=1))


class TriageInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"                # resolved to a sha by D7's activity
    build_probe: bool = True            # D6
    advisory_source: str = "none"       # E-41a: declared egress, off by default
    gates: GateSettings = Field(default_factory=GateSettings)
    max_gate_rounds: int = 2            # D9's bound on the REVISE loop


def skipped_signal(signal_id: str, reason: str) -> SignalResult:
    """A SignalResult for a signal that did not run -- skipped (D6) or failed
    (D8). Its owed readiness keys come from the registry declaration (D8a), so
    the dimension reports WHY it is unmeasured instead of falling through to
    compute_readiness's generic 'no signal reported <key>'.

    Never Measurement.measured(0.0): a run that did not happen has no value.
    """
    spec = SIGNALS[signal_id]
    return SignalResult(
        signal=signal_id, version=spec.version,
        collected=Measurement.not_collected(reason),
        metrics={key: Measurement.not_collected(reason)
                 for key in spec.readiness_keys})


@workflow.defn
class TriageWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._triage: RepoTriage | None = None

    @workflow.query
    def triage(self) -> RepoTriage | None:
        """The artifact; None until the fan-out completes (D11)."""
        return self._triage

    async def _one(self, signal_id: str, activity, arg, opts) -> SignalResult:
        """Run one signal. A timeout, a lost worker, or an exhausted retry
        becomes not_collected for THIS signal while every other one still
        reports -- the workflow-side half of E-41 spec D3, which the activity's
        own try/except cannot keep."""
        try:
            return await workflow.execute_activity(activity, arg, **opts)
        except Exception as e:                      # noqa: BLE001
            return skipped_signal(
                signal_id, f"{signal_id} activity failed: "
                           f"{type(e).__name__}: {e}"[:300])

    async def _fan_out(self, inp: TriageInput,
                       commit_sha: str) -> list[SignalResult]:
        sig = TriageSignalInput(repo_dir=inp.repo_dir, commit_sha=commit_sha)
        jobs = [
            self._one("baseline", triage_baseline, sig, SIGNAL_ACT),
            self._one("secrets", triage_secrets, sig, SIGNAL_ACT),
            self._one("scaffold", triage_scaffold, sig, SIGNAL_ACT),
            self._one("misconfig", triage_misconfig, sig, SIGNAL_ACT),
            self._one("outliers", triage_outliers, sig, SIGNAL_ACT),
            self._one("dependencies", triage_dependencies,
                      TriageDependencyInput(
                          repo_dir=inp.repo_dir, commit_sha=commit_sha,
                          advisory_source=inp.advisory_source),
                      DEPS_ACT),
        ]
        if inp.build_probe:
            jobs.append(self._one(
                "build_probe", triage_build_probe,
                TriageProbeInput(repo_dir=inp.repo_dir,
                                 commit_sha=commit_sha),
                PROBE_ACT))
        results = list(await asyncio.gather(*jobs))
        if not inp.build_probe:
            results.append(skipped_signal(
                "build_probe", "build probe not run (--no-build-probe)"))
        return results

    async def _assess(self, inp: TriageInput) -> RepoTriage:
        pin: TriagePin = await workflow.execute_activity(
            triage_resolve_commit,
            TriagePinInput(repo_dir=inp.repo_dir, commit=inp.commit),
            **PIN_ACT)
        self._status = "running"
        signals = await self._fan_out(inp, pin.commit_sha)
        return RepoTriage(repo_dir=inp.repo_dir, commit_sha=pin.commit_sha,
                          toolchain=pin.toolchain,
                          readiness=compute_readiness(signals),
                          signals=signals)

    @workflow.run
    async def run(self, inp: TriageInput) -> RepoTriage:
        self._triage = await self._assess(inp)
        self._status = f"triaged:{self._triage.readiness.verdict.value}"
        return self._triage
