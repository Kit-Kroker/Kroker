"""AssessmentWorkflow (E-45) -- Tier 2's shell.

The EDCR DAG (init -> scan -> discover -> assess -> report -> generate ->
finish) as a durable workflow, with five of seven phase bodies deliberately
unbuilt: scan is built (E-46), and discover E-48, assess E-49, finish E-51,
report and generate E-52 remain.

What ships now is the shape plus three invariants that are cheapest to install
before any phase produces findings: the admission rule narrowed to HUMAN
approvals (D2), phase state in workflow history rather than a ported
workflow.json (FR-911 deviation (b)), and FR-915's not_collected discipline
applied to phases so an assessment that assessed nothing says so (D5).

No LLM call lives here. Operator-run only: the init phase's TriageWorkflow
child executes the assessed repository's own build (NFR-9); E-57 and E-21 are
what remove that debt.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..agents.roles import PROMPT_SHAS, STAGE_MODELS, t_discover, t_risk
    from ..assessment.activities import (
        AssessRiskInput,
        BlueprintInput,
        DiscoverContextInput,
        DiscoverFinalizeInput,
        DiscoverLockInput,
        DiscoverMemoInput,
        DiscoverMemoStoreInput,
        LoadDispositionsInput,
        RiskMemoInput,
        RiskMemoStoreInput,
        VerifyRefsInput,
        VerifyRiskRefsInput,
        assess_risk,
        discover_context,
        discover_finalize,
        discover_lock,
        discover_memo_load,
        discover_memo_store,
        load_blueprint,
        load_dispositions,
        no_finalize,
        risk_memo_load,
        risk_memo_store,
        verify_discover_refs,
        verify_risk_refs,
    )
    from ..assessment.discover.apply import (
        apply,
        build_map,
        capabilities_of,
        fingerprint_of,
        stamp,
    )
    from ..assessment.discover.blueprint import not_compared
    from ..assessment.discover.context import (
        contract_collected,
        render_discover_prompt,
        schema_collected,
    )
    from ..assessment.discover.domain import consolidate
    from ..assessment.discover.map import (
        CapabilityMap,
        DiscoverProposal,
        context_digest,
        guard_tripped,
    )
    from ..assessment.discover.verify import RefVerification
    from ..assessment.gates.checks import evaluate
    from ..assessment.gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict
    from ..assessment.models import (
        PHASE_ORDER,
        Assessment,
        InitOutcome,
        PhaseId,
        PhaseResult,
        terminal_status,
    )
    from ..assessment.risk.apply import apply_judgment, degraded
    from ..assessment.risk.build import map_digest, no_risk
    from ..assessment.risk.models import RiskProposal, RiskVerification, UnifiedRiskMap
    from ..assessment.risk.prompt import render_risk_prompt
    from ..assessment.scan.models import ScanResult, ScanSignalId
    from ..assessment.verification import guard_reason
    from ..capability.models import ProposedCapability
    from ..core.models import (
        GateDecision,
        GateSettings,
    )
    from ..measurement import CollectionState, Measurement
    from ..memoization.cache import NO_PROPOSER
    from ..pending import GateContext
    from ..triage.admission import admits
    from ..triage.models import RepoTriage
    from .fanout import run_or_degrade
    from .gates import GateHost
    from .scanning import (
        ScanOutcome,
        scan_tree,
    )
    from .scanning import (
        _collected_from_categories as _collected_from_categories,
    )
    from .scanning import (
        _inherited_row as _inherited_row,
    )
    from .scanning import (
        _merged_row as _merged_row,
    )
    from .scanning import (
        fold_row as fold_row,
    )
    from .scanning import (
        skipped_scan_signal as skipped_scan_signal,
    )
    from .scanning import (
        upstream_for as upstream_for,
    )
    from .triage import TriageInput, TriageWorkflow


class AssessmentInput(BaseModel):
    """Mirrors TriageInput's knobs, which are the ones the child needs.

    max_gate_rounds is deliberately NOT surfaced: the readiness gate's REVISE
    loop belongs to the child, which owns its own bound.
    """

    repo_dir: str
    commit: str = "HEAD"
    build_probe: bool = True
    advisory_source: str = "none"
    gates: GateSettings = Field(default_factory=GateSettings)
    # Capability identity is per-project (E-47a), and this is the scope every
    # BC-NNN is allocated within. Deliberately NOT derived from repo_dir: a
    # value computed from a filesystem path moves every client-cited id when
    # a checkout moves. Named after PipelineConfig.project_key, which
    # addresses the same SQLite file.
    project_key: str = "default"
    # DD7: whether the discover proposer stage is active (propose_discover=True)
    # or disabled (propose_discover=False, baseline only).
    propose_discover: bool = True
    # RD7: whether the risk proposer stage is active (propose_risk=True) or
    # disabled (propose_risk=False, deterministic score only). The phase is
    # MEASURED either way -- what changes is whether the judgment layer is.
    propose_risk: bool = True


# The E-item owing each unbuilt phase body, so an empty assessment says WHY
# it is empty rather than merely being empty. SCAN dropped here in E-46,
# DISCOVER in E-48, and ASSESS in E-49: their bodies are built, so nothing
# owes them.
PHASE_OWNER: dict[PhaseId, str] = {
    PhaseId.REPORT: "E-52",
    PhaseId.GENERATE: "E-52",
    PhaseId.FINISH: "E-51",
}


def unbuilt(phase: PhaseId) -> PhaseResult:
    """A phase whose body is a later item. Never Measurement.measured(0.0):
    a phase that did not run has no value (FR-915)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected(
            f"{phase.value} not implemented ({PHASE_OWNER[phase]})"
        ),
    )


def skipped(phase: PhaseId) -> PhaseResult:
    """A phase that exists but was never reached, because the repository was
    not admitted (FR-903 / ADR-18)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected("not run: repository not admitted (FR-903)"),
    )


DISCOVER_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=10), retry_policy=RetryPolicy(maximum_attempts=2)
)
# Three attempts, not two: an IdentityConflictError means a concurrent
# assessment wrote first, and a retry re-reads the registry and re-matches
# (E-47a's loser behaviour) rather than replaying computed attachments.
LOCK_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=2), retry_policy=RetryPolicy(maximum_attempts=3)
)

ASSESS_ACT = workflow.ActivityConfig(
    start_to_close_timeout=timedelta(minutes=5), retry_policy=RetryPolicy(maximum_attempts=2)
)


class DiscoverOutcome(BaseModel):
    """discover's two halves, mirroring ScanOutcome."""

    result: PhaseResult
    map: CapabilityMap | None = None


class AssessOutcome(BaseModel):
    """assess's two halves, mirroring ScanOutcome and DiscoverOutcome."""

    result: PhaseResult
    risk: UnifiedRiskMap | None = None


def no_discover(reason: str) -> DiscoverOutcome:
    """DD9's phase-level failure: the capability set itself could not be
    produced, so there is no map. Everything short of that degrades
    per-report INSIDE the map instead."""
    return DiscoverOutcome(
        result=PhaseResult(phase=PhaseId.DISCOVER, collected=Measurement.not_collected(reason))
    )


def no_assess(reason: str) -> AssessOutcome:
    """The phase-level failure: there is no capability set to score, so
    there is no map. Everything short of that degrades INSIDE the map."""
    return AssessOutcome(
        result=PhaseResult(phase=PhaseId.ASSESS, collected=Measurement.not_collected(reason))
    )


class RiskGateStepOutcome(BaseModel):
    """_risk_gate's result: the report (None only when ASSESS did not
    measure), the audited override (None unless BLOCK was approved), and
    whether REPORT/GENERATE/FINISH must be skipped (GD1/GD2)."""

    gates: RiskGateReport | None = None
    override: RiskGateOverride | None = None
    blocked: bool = False


def risk_gate_skipped(phase: PhaseId) -> PhaseResult:
    """A phase that exists but was never reached because the risk gate
    (FR-917) BLOCKed and was not overridden (E-50 GD2)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected(
            "not run: risk gate BLOCKed and was not overridden (FR-917)"
        ),
    )


def _risk_gate_summary(report: RiskGateReport) -> str:
    lines = [f"verdict: {report.verdict.value}"]
    if report.reasons:
        lines.append("reasons:")
        lines.extend(f"  {r}" for r in report.reasons)
    if report.deferred:
        lines.append("deferred:")
        lines.extend(f"  {d}" for d in report.deferred)
    return "\n".join(lines)


def risk_override_from(decision: GateDecision) -> RiskGateOverride | None:
    """FR-304, mirroring triage.py's override_from -- every APPROVE records
    an override, with approved_by carrying decided_by VERBATIM (E-50 GD5)."""
    if not decision.approved:
        return None
    return RiskGateOverride(
        approved_by=decision.decided_by,
        reviewer=decision.reviewer,
        reason=decision.comments or "",
        decided_at=decision.decided_at or workflow.now(),
        gate_round=decision.round,
    )


def assemble(
    repo_dir: str,
    init: InitOutcome,
    admitted: bool,
    reason: str,
    rest: list[PhaseResult] | None = None,
    scan: ScanResult | None = None,
    discover: CapabilityMap | None = None,
    risk: UnifiedRiskMap | None = None,
    gates: RiskGateReport | None = None,
    gate_override: RiskGateOverride | None = None,
) -> Assessment:
    """The ONLY constructor of an Assessment and the only caller of
    terminal_status: one place where the artifact is built means the derived
    status cannot disagree with the phase list it was derived from.

    When NOT admitted, unreached phases are filled with skipped() -- whose
    'not admitted' message is then truthful -- so `phases` is always the whole
    DAG. When admitted, every non-init phase MUST be supplied (run() always
    does): an admitted run has no 'unreached' phases, and filling a missing
    one with skipped() would stamp 'not admitted' onto an artifact whose
    admitted field is True (review finding 1).
    """
    owed = [p for p in PHASE_ORDER if p is not PhaseId.INIT]
    by_id = {p.phase: p for p in (rest or [])}
    if admitted:
        missing = [p for p in owed if p not in by_id]
        if missing:
            raise ValueError(
                f"admitted run missing phase result(s) "
                f"{[p.value for p in missing]} -- an admitted run has no "
                f"unreached phases; supply every non-init result"
            )
    phases = [init.result] + [by_id.get(p, skipped(p)) for p in owed]
    t = init.triage
    return Assessment(
        repo_dir=repo_dir,
        commit_sha=t.commit_sha if t else "",
        toolchain=t.toolchain if t else None,
        triage=t,
        admitted=admitted,
        admission_reason=reason,
        phases=phases,
        terminal_status=terminal_status(admitted, phases),
        scan=scan,
        discover=discover,
        risk=risk,
        gates=gates,
        gate_override=gate_override,
    )


@workflow.defn
class AssessmentWorkflow(GateHost):
    """Inherits GateHost for two gates: the readiness gate is the CHILD
    TriageWorkflow's; the risk gate (E-50, FR-917) is this workflow's own,
    opened by _risk_gate right after ASSESS."""

    def __init__(self) -> None:
        super().__init__()
        self._assessment: Assessment | None = None

    @workflow.query
    def assessment(self) -> Assessment | None:
        """The artifact; None until the run terminates."""
        return self._assessment

    async def _init(self, inp: AssessmentInput) -> InitOutcome:
        """Phase 1. Runs TriageWorkflow as a CHILD (D3) rather than accepting
        a RepoTriage as input: the admission rule's whole subject is
        override.approved_by, and a caller-supplied artifact is a
        caller-supplied value for exactly that field. Running the child puts
        the verdict, the readiness gate and the human decision in THIS
        assessment's history, so the claim is replayable evidence.

        A child that raises degrades to a refusal, never a crashed
        assessment -- the shape TriageWorkflow._one established.
        """
        self._status = "triaging"
        try:
            triage: RepoTriage = await workflow.execute_child_workflow(
                TriageWorkflow.run,
                TriageInput(
                    repo_dir=inp.repo_dir,
                    commit=inp.commit,
                    build_probe=inp.build_probe,
                    advisory_source=inp.advisory_source,
                    gates=inp.gates,
                ),
                id=f"{workflow.info().workflow_id}-triage",
                task_queue=workflow.info().task_queue,
            )
        except Exception as e:  # noqa: BLE001
            return InitOutcome(
                result=PhaseResult(
                    phase=PhaseId.INIT,
                    collected=Measurement.not_collected(
                        f"triage child failed: {type(e).__name__}: {e}"[:300]
                    ),
                )
            )
        return InitOutcome(
            result=PhaseResult(phase=PhaseId.INIT, collected=Measurement.measured(1.0)),
            triage=triage,
        )

    async def _scan(self, inp: AssessmentInput, triage: RepoTriage) -> ScanOutcome:
        """Phase 2 (E-46). The fan-out moved to workflows/scanning.py with
        E-84, so the pipeline's brownfield context stage runs the identical
        thirteen signals over the identical memo (E-84 D1)."""
        return await scan_tree(inp.repo_dir, triage.commit_sha, triage)

    async def _discover(
        self, inp: AssessmentInput, triage: RepoTriage, scan_out: ScanOutcome
    ) -> DiscoverOutcome:
        """Phase 3 (E-48). DD4's pipeline, complete with proposer, verification,
        citation guard, blueprint comparison, and derived domain model.

        Nothing here executes the assessed repository's code -- activities
        read blob bytes at the pinned commit (NFR-9).
        """
        if scan_out.scan is None:
            return no_discover(f"scan produced no result: {scan_out.result.collected.reason}")
        s5 = next((r for r in scan_out.scan.signals if r.signal is ScanSignalId.S5), None)
        if s5 is None or s5.collected.state is not CollectionState.MEASURED:
            # DD9's first row. Without a candidate set there is nothing to
            # dispose over, and an empty map would claim the repository has
            # no capabilities rather than that the scan could not see them.
            return no_discover(f"S5 did not collect: {s5.collected.reason if s5 else 'no S5 row'}")

        try:
            context = await workflow.execute_activity(
                discover_context,
                DiscoverContextInput(
                    repo_dir=inp.repo_dir,
                    commit_sha=triage.commit_sha,
                    tree_hash=scan_out.tree_hash,
                    scan=scan_out.scan,
                ),
                **DISCOVER_ACT,
            )
        except Exception as e:  # noqa: BLE001
            return no_discover(f"discover_context failed: {type(e).__name__}: {e}"[:300])
        if context.collected.state is not CollectionState.MEASURED:
            return no_discover(f"the context could not be built: {context.collected.reason}")

        # P2-D6: NO_PROPOSER, never "". A baseline-only map and a proposer map
        # must never share a key, so the two terms are the role's own when the
        # role is shipped and the sentinel when it is not.
        proposing = inp.propose_discover and t_discover is not None
        memo_key = DiscoverMemoInput(
            project=inp.project_key,
            tree_hash=scan_out.tree_hash,
            context_digest=context_digest(context),
            prompt_sha=PROMPT_SHAS["discover"] if proposing else NO_PROPOSER,
            model=STAGE_MODELS["discover"] if proposing else NO_PROPOSER,
        )

        # A cache read that fails is a MISS, never a phase failure.
        def _memo_miss() -> CapabilityMap | None:
            return None

        hit = await run_or_degrade(discover_memo_load, memo_key, DISCOVER_ACT, fallback=_memo_miss)
        if hit is not None:
            return DiscoverOutcome(
                result=PhaseResult(phase=PhaseId.DISCOVER, collected=hit.collected), map=hit
            )

        proposal = None
        verification = None
        if inp.propose_discover and t_discover is not None:
            try:
                run = await t_discover.run(render_discover_prompt(context))
                # The TemporalAgent's run() is untyped generically; the
                # discover agent's output_type IS DiscoverProposal.
                proposal = cast(DiscoverProposal, run.output)
            except Exception as e:  # noqa: BLE001
                # The role shipped and was invoked, but the call failed.
                # Must fail closed rather than quietly laundering into baseline
                # (which would store a judgment-free map under the proposer's memo key).
                return no_discover(f"discover proposer failed: {type(e).__name__}: {e}")

        if proposal is not None:
            # A verification that cannot run is a REFUSAL, never a skip.
            def _verify_miss() -> RefVerification | None:
                return None

            verification = await run_or_degrade(
                verify_discover_refs,
                VerifyRefsInput(
                    repo_dir=inp.repo_dir, commit_sha=triage.commit_sha, proposal=proposal
                ),
                DISCOVER_ACT,
                fallback=_verify_miss,
            )
            if verification is None:
                # Verification could not run, so no citation is verified.
                # Applying the proposal anyway would ship exactly the
                # unverified claims DD8 exists to refuse.
                return no_discover(
                    "verify_discover_refs did not run, so no citation could "
                    "be verified (DD8 fails closed)"
                )
            tripped = guard_tripped(verification)
            if tripped:
                return no_discover(tripped)

        try:
            stamped = stamp(
                context,
                verification.proposal if verification is not None else None,
                refusals=verification.refusals if verification is not None else {},
            )
            applied = apply(context, stamped)
        except Exception as e:  # noqa: BLE001
            return no_discover(f"disposition apply failed: {type(e).__name__}: {e}"[:300])

        try:
            lock = await workflow.execute_activity(
                discover_lock,
                DiscoverLockInput(
                    project=inp.project_key,
                    run_id=workflow.info().run_id,
                    proposed=[
                        ProposedCapability(local_key=c.local_key, fingerprint=fingerprint_of(c))
                        for c in applied.locked
                    ],
                ),
                **LOCK_ACT,
            )
        except Exception as e:  # noqa: BLE001
            # E-47a's fail-closed rule (DD9): proceeding produces a complete,
            # plausible-looking map in which every id is wrong.
            return no_discover(f"identity lock failed: {type(e).__name__}: {e}"[:300])

        bc_of = {a.local_key: a.bc_id for a in lock.attachments}
        try:
            caps = capabilities_of(applied, bc_of)
            blueprint = await run_or_degrade(
                load_blueprint,
                BlueprintInput(capabilities=list(caps)),
                DISCOVER_ACT,
                fallback=lambda: not_compared("load_blueprint did not run to completion"),
            )
            finalized = await run_or_degrade(
                discover_finalize,
                DiscoverFinalizeInput(
                    repo_dir=inp.repo_dir,
                    commit_sha=triage.commit_sha,
                    members={bc_of[c.local_key]: list(c.members) for c in applied.locked},
                    entry_point_paths=list(context.entry_point_paths),
                    schema_collected=schema_collected(scan_out.scan),
                    contract_collected=contract_collected(scan_out.scan),
                ),
                DISCOVER_ACT,
                fallback=lambda: no_finalize("discover_finalize did not run to completion"),
            )
            capability_map = build_map(
                applied,
                bc_of,
                advisories=lock.advisories,
                attribution=finalized.attribution,
                decomposition=finalized.decomposition,
                ownership=finalized.ownership,
                total_references=(verification.total_references if verification is not None else 0),
                blueprint=blueprint,
                domain_model=consolidate(finalized.ownership, caps),
            )
        except Exception as e:  # noqa: BLE001
            # build_map raises only on a lock defect (a boundary with no
            # bc_id). Reporting it as a phase failure keeps the reason on the
            # artifact instead of retrying a workflow task forever.
            return no_discover(f"the map could not be assembled: {type(e).__name__}: {e}"[:300])

        await run_or_degrade(
            discover_memo_store,
            DiscoverMemoStoreInput(
                key=memo_key, registry_version=lock.registry_version, out=capability_map
            ),
            DISCOVER_ACT,
            fallback=lambda: False,
        )
        return DiscoverOutcome(
            result=PhaseResult(phase=PhaseId.DISCOVER, collected=capability_map.collected),
            map=capability_map,
        )

    async def _assess(
        self, inp: AssessmentInput, triage: RepoTriage, discover: DiscoverOutcome, scan: ScanOutcome
    ) -> AssessOutcome:
        """Phase 4 (E-49). The deterministic score, then the judgment layer.

        Nothing here executes the assessed repository's code. The only tree
        access is verify_risk_refs, which reads exactly the blobs the
        proposer cited, at the pinned commit (NFR-9).
        """
        if discover.map is None:
            return no_assess(
                f"discover did not produce a CapabilityMap "
                f"({discover.result.collected.reason}), so there is "
                f"nothing to assess"
            )

        collected = sorted(
            cat
            for s in (scan.scan.signals if scan.scan else [])
            for cat, m in s.categories.items()
            if m.state is CollectionState.MEASURED
        )

        # NO_PROPOSER, never "": a baseline-only map and a judged map must
        # never share a key (P2-D6's rule at the assess tier).
        proposing = inp.propose_risk and t_risk is not None
        memo_key = RiskMemoInput(
            project=inp.project_key,
            tree_hash=scan.tree_hash,
            map_digest=map_digest(discover.map),
            prompt_sha=PROMPT_SHAS["risk"] if proposing else NO_PROPOSER,
            model=STAGE_MODELS["risk"] if proposing else NO_PROPOSER,
        )

        # A cache read that fails is a MISS, never a phase failure.
        def _risk_memo_miss() -> UnifiedRiskMap | None:
            return None

        hit = await run_or_degrade(risk_memo_load, memo_key, ASSESS_ACT, fallback=_risk_memo_miss)
        if hit is not None:
            return self._assessed(hit)

        baseline = await run_or_degrade(
            assess_risk,
            AssessRiskInput(capability_map=discover.map, collected_categories=collected),
            ASSESS_ACT,
            fallback=lambda: no_risk("assess_risk activity failed"),
        )
        if baseline.collected.state is not CollectionState.MEASURED:
            return self._assessed(baseline)

        final = await self._judge(inp, triage, discover.map, baseline, proposing)
        # store() refuses a degraded judgment under a proposer key (P2-D3),
        # so a transient model failure costs one recompute rather than a
        # permanently judgment-free map.
        await run_or_degrade(
            risk_memo_store,
            RiskMemoStoreInput(key=memo_key, out=final),
            ASSESS_ACT,
            fallback=lambda: False,
        )
        return self._assessed(final)

    def _assessed(self, m: UnifiedRiskMap) -> AssessOutcome:
        """RD7: the phase is MEASURED whenever the COMPOSITES are, whatever
        the judgment layer did -- its own state travels on the map.

        A not_collected map yields an uncollected phase result AND passes
        risk=None to assemble, so _assess_agrees_with_its_phase holds.
        """
        if m.collected.state is not CollectionState.MEASURED:
            return AssessOutcome(
                result=PhaseResult(phase=PhaseId.ASSESS, collected=m.collected), risk=None
            )
        return AssessOutcome(
            result=PhaseResult(phase=PhaseId.ASSESS, collected=Measurement.measured(1.0)), risk=m
        )

    async def _judge(
        self,
        inp: AssessmentInput,
        triage: RepoTriage,
        cmap: CapabilityMap,
        baseline: UnifiedRiskMap,
        proposing: bool,
    ) -> UnifiedRiskMap:
        """RD7's degradation, layer-scoped: every failure returns the
        BASELINE with a reason on `judgment`, never a failed phase.

        The difference from _discover is deliberate and stated in RD7: there,
        dispositions ARE the map's content, so a tripped guard fails the
        phase. Here the composites never depended on the proposer.

        The reasons are deliberately distinct -- "no proposer is configured"
        and "the proposer ran and was refused" must not converge, which is
        unbuilt_signal vs failed_signal's rule.
        """
        if not proposing or t_risk is None:
            return degraded(
                baseline,
                "no risk proposer ran: agents/risk/ is absent or "
                "propose_risk is False, so no STRIDE applicability, "
                "vulnerability classification or control disposition was "
                "judged",
            )

        try:
            run = await t_risk.run(render_risk_prompt(cmap, baseline))
            # The risk agent's output_type IS RiskProposal.
            proposal = cast(RiskProposal, run.output)
        except Exception as e:  # noqa: BLE001
            return degraded(
                baseline, f"the risk proposer ran and failed: {type(e).__name__}: {e}"[:300]
            )

        # Same refusal rule as discover's: verification that cannot run is a
        # REFUSAL, never a skip.
        def _risk_verify_miss() -> RiskVerification | None:
            return None

        verification = await run_or_degrade(
            verify_risk_refs,
            VerifyRiskRefsInput(
                repo_dir=inp.repo_dir, commit_sha=triage.commit_sha, proposal=proposal
            ),
            ASSESS_ACT,
            fallback=_risk_verify_miss,
        )
        if verification is None:
            # Verification could not run, so no citation is verified.
            # Applying the proposal anyway would ship exactly the unverified
            # claims RD6 exists to refuse.
            return degraded(
                baseline,
                "verify_risk_refs did not run, so no citation could be verified (RD6 fails closed)",
            )

        tripped = guard_reason(verification)
        if tripped:
            return degraded(baseline, tripped)

        try:
            return apply_judgment(
                baseline, verification.proposal, total_proposed=len(proposal.rows)
            )
        except Exception as e:  # noqa: BLE001
            return degraded(
                baseline,
                f"the proposer's dispositions could not be applied: {type(e).__name__}: {e}"[:300],
            )

    async def _risk_gate(
        self, inp: AssessmentInput, discover_out: DiscoverOutcome, assess_out: AssessOutcome
    ) -> RiskGateStepOutcome:
        """E-50 (FR-917, GD1/GD2). The checks run right after ASSESS. A
        BLOCK opens a HARD gate the same way the readiness gate does;
        APPROVE stamps an audited override and REPORT/GENERATE/FINISH
        proceed; REJECT (or a HOLD timeout) leaves them unreached.

        GD2 names only APPROVE/REJECT; GateOutcome also has REVISE
        (TriageWorkflow's readiness gate uses it to mean "fix the build and
        re-triage," a round-based retry). The risk gate has no round or
        retry concept -- a deterministic verdict over the current risk map
        does not change by asking again -- so REVISE is deliberately
        treated identically to REJECT here: `decision.approved` is False
        for both, and only an explicit APPROVE unblocks. This is a decision
        recorded once, here, not an unexamined fallthrough.
        """
        if assess_out.risk is None or discover_out.map is None:
            return RiskGateStepOutcome()

        dispositions = await run_or_degrade(
            load_dispositions,
            LoadDispositionsInput(project=inp.project_key),
            ASSESS_ACT,
            fallback=lambda: (),
        )
        report = evaluate(assess_out.risk, discover_out.map, dispositions)
        if report.verdict is not RiskGateVerdict.BLOCK:
            return RiskGateStepOutcome(gates=report)

        decision = await self._gate(
            "risk", inp.gates, context=GateContext(spec_summary=_risk_gate_summary(report))
        )
        if decision.approved:
            return RiskGateStepOutcome(gates=report, override=risk_override_from(decision))
        return RiskGateStepOutcome(gates=report, blocked=True)

    async def _report(self, inp: AssessmentInput) -> PhaseResult:
        """E-52 owns this body: the five role reports."""
        return unbuilt(PhaseId.REPORT)

    async def _generate(self, inp: AssessmentInput) -> PhaseResult:
        """E-52 owns this body: the evidence bundle and its manifest."""
        return unbuilt(PhaseId.GENERATE)

    async def _finish(self, inp: AssessmentInput) -> PhaseResult:
        """E-51 owns this body: the 14 acceptance criteria as CheckResults."""
        return unbuilt(PhaseId.FINISH)

    def _done(self, a: Assessment) -> Assessment:
        self._assessment = a
        self._status = a.terminal_status
        return a

    @workflow.run
    async def run(self, inp: AssessmentInput) -> Assessment:
        init = await self._init(inp)
        if init.triage is None:
            # The child failed; admission was never consulted, and an
            # assessment that could not establish admission must never
            # proceed to assess.
            return self._done(assemble(inp.repo_dir, init, False, init.result.collected.reason))

        ok, why = admits(init.triage, require_human=True)
        if not ok:
            return self._done(assemble(inp.repo_dir, init, False, why))

        self._status = "running"
        scan_out = await self._scan(inp, init.triage)
        discover_out = await self._discover(inp, init.triage, scan_out)
        assess_out = await self._assess(inp, init.triage, discover_out, scan_out)
        gate_out = await self._risk_gate(inp, discover_out, assess_out)

        if gate_out.blocked:
            rest = [
                scan_out.result,
                discover_out.result,
                assess_out.result,
                risk_gate_skipped(PhaseId.REPORT),
                risk_gate_skipped(PhaseId.GENERATE),
                risk_gate_skipped(PhaseId.FINISH),
            ]
        else:
            rest = [
                scan_out.result,
                discover_out.result,
                assess_out.result,
                await self._report(inp),  # AFTER assess -- FR-911 dev. (a)
                await self._generate(inp),
                await self._finish(inp),
            ]
        return self._done(
            assemble(
                inp.repo_dir,
                init,
                True,
                why,
                rest,
                scan=scan_out.scan,
                discover=discover_out.map,
                risk=assess_out.risk,
                gates=gate_out.gates,
                gate_override=gate_out.override,
            )
        )
