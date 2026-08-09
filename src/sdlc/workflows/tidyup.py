"""TidyUpWorkflow (E-44) -- Tier 0's fix half.

Assess -> fix -> PROVE. Accepted MECHANICAL findings become governed
brownfield FeatureWorkflow child runs, one PR each (NG5, D2), and triage then
re-runs against a composite verification branch so the before/after delta is
recorded evidence rather than a claim.

No LLM call lives here. Every model call happens inside the child fix runs.

Operator-run only. The fix runs execute the triaged repository's build and
test commands, which is a wider exposure than E-42's build probe alone
(NFR-9). E-57 and E-21 are what remove that debt.
"""
from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import VerifyBranchInput, build_verification_branch
    from ..models import (
        GateConfig, GatePolicy, GateSettings, IdeaBrief, PipelineConfig,
        ProjectMode,
    )
    from ..pending import GateContext
    from ..tidyup.backlog import (
        admitted, mechanical_backlog, seeded_work_for,
    )
    from ..triage.delta import FindingDelta, compute_delta
    from ..triage.models import RepoTriage, Verdict
    from .feature import FeatureWorkflow
    from .gates import GateHost
    from .triage import TriageInput, TriageWorkflow

# Local git only; a retry is free because the branch is force-created.
VERIFY_ACT = dict(start_to_close_timeout=timedelta(minutes=10),
                  retry_policy=RetryPolicy(maximum_attempts=3))


def _fix_gates() -> dict[str, GateConfig]:
    """D9. feature.py opens the `deploy` gate BEFORE checking
    cfg.deploy.enabled, and PipelineConfig.default_gate_policy is HARD -- so
    an unconfigured tidy-up PR would park for 48 hours on a gate for a deploy
    that was never going to run. Defaulted here rather than reordered in
    feature.py: that ordering is deliberate for feature runs, where the gate
    records an operator's intent independently of deploy configuration.
    """
    cfg = PipelineConfig()
    gates = dict(cfg.gates)
    gates["deploy"] = GateConfig(policy=GatePolicy.OFF)
    return gates


def _default_fix_cfg() -> PipelineConfig:
    cfg = PipelineConfig()
    cfg.gates = _fix_gates()
    cfg.deploy.enabled = False
    return cfg


class TidyUpInput(BaseModel):
    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    base_branch: str = "main"
    gates: GateSettings = Field(default_factory=GateSettings)
    fix_cfg: PipelineConfig = Field(default_factory=_default_fix_cfg)
    max_fix_runs: int = 10          # D10: a cap on spend, not on honesty


class FixRunResult(BaseModel):
    identity: str
    workflow_id: str
    outcome: str                    # FeatureWorkflow's return string, verbatim
    pr_url: str | None = None
    branch: str | None = None
    merged_into_verify: bool = False


class TidyUpReport(BaseModel):
    before: RepoTriage
    after: RepoTriage | None = None
    verify_ref: str | None = None
    backlog: list[str] = Field(default_factory=list)
    accepted: list[str] = Field(default_factory=list)
    deferred: list[str] = Field(default_factory=list)
    runs: list[FixRunResult] = Field(default_factory=list)
    deltas: list[FindingDelta] = Field(default_factory=list)
    readiness_before: Verdict
    readiness_after: Verdict | None = None


def fix_workflow_id(tidyup_id: str, index: int) -> str:
    """D10: derived, never generated. Replay must produce the same id, and a
    fix run stays identifiable in the Temporal UI."""
    return f"{tidyup_id}-fix-{index:02d}"


def reached_a_pr(outcome: str) -> bool:
    """Whether a fix run produced a branch worth merging into the
    verification tree. The return string is the only thing FeatureWorkflow
    gives a caller, and `deployed:` / `merged-not-deployed:` are the two
    prefixes reachable only after the absolute merge gate passed."""
    return outcome.startswith(("deployed:", "merged-not-deployed:"))


def branches_to_verify(runs: list[FixRunResult]) -> list[str]:
    """Successful branches in accepted order (D6)."""
    return [r.branch for r in runs if r.branch and reached_a_pr(r.outcome)]


def _backlog_summary(pairs, deferred_from: int) -> str:
    """ASCII render for the gate's pending item."""
    lines = []
    for n, (identity, f) in enumerate(pairs):
        mark = "  " if n < deferred_from else "* "
        lines.append(f"{mark}{identity}  [{f.severity}] {f.detail[:90]}")
    tail = ("\n\n(* beyond max_fix_runs; deferred with the reason recorded)"
            if len(pairs) > deferred_from else "")
    return (f"{len(pairs)} mechanically-fixable finding(s). Approving opens "
            f"one PR per item.\n\n" + "\n".join(lines) + tail)


@workflow.defn
class TidyUpWorkflow(GateHost):
    def __init__(self) -> None:
        super().__init__()
        self._report: TidyUpReport | None = None
        self._selected: list[str] | None = None

    @workflow.query
    def report(self) -> TidyUpReport | None:
        """The artifact; None until the baseline triage completes."""
        return self._report

    @workflow.signal
    def select_items(self, identities: list[str]) -> None:
        """D8: narrows the backlog before the gate is decided. Unsent means
        all. Read ONCE, at decision time -- a signal arriving afterwards
        cannot retroactively change what ran."""
        self._selected = list(identities)

    async def _triage(self, inp: TidyUpInput, suffix: str,
                      commit: str) -> RepoTriage:
        return await workflow.execute_child_workflow(
            TriageWorkflow.run,
            TriageInput(repo_dir=inp.repo_dir, commit=commit,
                        build_probe=inp.build_probe,
                        advisory_source=inp.advisory_source,
                        gates=inp.gates),
            id=f"{workflow.info().workflow_id}-triage-{suffix}",
            task_queue=workflow.info().task_queue)

    async def _fix_run(self, inp: TidyUpInput, index: int, identity: str,
                       finding, signal_version: int) -> FixRunResult:
        """One accepted finding -> one governed run -> one PR.

        A child that raises degrades THIS item only, never the tidy-up --
        the shape TriageWorkflow._one established.
        """
        wf_id = fix_workflow_id(workflow.info().workflow_id, index)
        branch = f"sdlc/{wf_id}/integration"
        try:
            outcome = await workflow.execute_child_workflow(
                FeatureWorkflow.run,
                args=[
                    IdeaBrief(title=f"tidy-up: {finding.rule}",
                              description=finding.detail,
                              mode=ProjectMode.BROWNFIELD,
                              repo_url=inp.repo_dir,
                              base_branch=inp.base_branch),
                    inp.fix_cfg,
                    seeded_work_for(identity, finding, signal_version),
                ],
                id=wf_id, task_queue=workflow.info().task_queue)
        except Exception as e:                      # noqa: BLE001
            return FixRunResult(
                identity=identity, workflow_id=wf_id,
                outcome=f"failed:{type(e).__name__}: {e}"[:300])
        pr = outcome.split(":", 1)[1] if reached_a_pr(outcome) else None
        return FixRunResult(identity=identity, workflow_id=wf_id,
                            outcome=outcome, pr_url=pr,
                            branch=branch if reached_a_pr(outcome) else None)

    @workflow.run
    async def run(self, inp: TidyUpInput) -> TidyUpReport:
        self._status = "triaging"
        before = await self._triage(inp, "before", inp.commit)

        versions = {s.signal: s.version for s in before.signals}
        pairs = mechanical_backlog(before)
        backlog = [identity for identity, _ in pairs]

        def _finish(**kw) -> TidyUpReport:
            self._report = TidyUpReport(
                before=before, backlog=backlog,
                readiness_before=before.readiness.verdict, **kw)
            return self._report

        if not admitted(before):
            # D7: not admitted is not empty-handed -- the backlog IS US-8's
            # checkable hygiene list. D5 rule 4 supplies the deltas.
            self._status = "blocked:readiness"
            return _finish(deltas=compute_delta(before, None))

        if not backlog:
            self._status = "tidied:nothing-mechanical"
            return _finish(deltas=compute_delta(before, None))

        self._status = "awaiting:tidy_up"
        decision = await self._gate(
            "tidy_up", inp.gates,
            context=GateContext(spec_summary=_backlog_summary(
                pairs, inp.max_fix_runs)))
        if not decision.approved:
            self._status = "rejected:tidy_up"
            return _finish(deltas=compute_delta(before, None))

        # D8: read the selection ONCE, here.
        chosen = (backlog if self._selected is None
                  else [i for i in backlog if i in set(self._selected)])
        accepted = chosen[:inp.max_fix_runs]
        deferred = chosen[inp.max_fix_runs:]
        by_identity = dict(pairs)

        self._status = "fixing"
        runs: list[FixRunResult] = []
        for index, identity in enumerate(accepted):
            finding = by_identity[identity]
            runs.append(await self._fix_run(
                inp, index, identity, finding,
                versions.get(finding.signal, 0)))

        branches = branches_to_verify(runs)
        if not branches:
            # D5 rule 4: nothing to measure, and the report says so.
            self._status = "tidied:no-branches"
            return _finish(accepted=accepted, deferred=deferred, runs=runs,
                           deltas=compute_delta(before, None))

        self._status = "verifying"
        verify = await workflow.execute_activity(
            build_verification_branch,
            VerifyBranchInput(repo_path=inp.repo_dir,
                              base_sha=before.commit_sha,
                              tidyup_id=workflow.info().workflow_id,
                              branches=branches),
            **VERIFY_ACT)
        merged = set(verify.merged)
        for r in runs:
            r.merged_into_verify = r.branch in merged
        conflicted = [r.identity for r in runs
                      if r.branch and r.branch not in merged]

        after = await self._triage(inp, "after", verify.head_sha)
        self._status = "tidied"
        return _finish(after=after, verify_ref=verify.ref,
                       accepted=accepted, deferred=deferred, runs=runs,
                       readiness_after=after.readiness.verdict,
                       deltas=compute_delta(before, after, conflicted))
