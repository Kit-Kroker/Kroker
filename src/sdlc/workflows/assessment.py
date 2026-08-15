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

import asyncio
from collections.abc import Mapping
from datetime import timedelta

from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..assessment.activities import (
        AssessmentTree, AssessmentTreeInput, DiscoverContextInput,
        DiscoverFinalizeInput, DiscoverLockInput, DiscoverMemoInput,
        DiscoverMemoStoreInput, ScanSignalInput, assessment_resolve_tree,
        discover_context, discover_finalize, discover_lock,
        discover_memo_load, discover_memo_store, no_finalize, scan_ci,
        scan_config_infra, scan_coverage, scan_entrypoints, scan_frontend,
        scan_packages, scan_schema, scan_security_static, scan_sensitivity,
        scan_testability, scan_tests_inventory,
    )
    from ..assessment.models import (
        PHASE_ORDER,
        Assessment,
        InitOutcome,
        PhaseId,
        PhaseResult,
        terminal_status,
    )
    from ..assessment.discover.apply import (
        apply, build_map, fingerprint_of, stamp,
    )
    from ..assessment.discover.context import (
        contract_collected, schema_collected,
    )
    from ..assessment.discover.map import CapabilityMap, context_digest
    from ..assessment.scan.inherit import InheritedHalf, inherited_halves
    from ..assessment.scan.merge import MergeOutput, merge
    from ..assessment.scan.models import (
        C_MERGE, CATEGORIES, SCAN_ORDER, ScanResult, ScanSignalId,
        ScanSignalResult, ScanUpstream, SignalOutput, SignalSource,
        family_of,
    )
    from ..assessment.scan.registry import SCAN_SIGNALS, WAVES
    from ..capability.models import ProposedCapability
    from ..measurement import CollectionState, Measurement
    from ..memoization.cache import NO_PROPOSER
    from ..models import GateSettings
    from ..triage.admission import admits
    from ..triage.models import RepoTriage
    from .fanout import run_or_degrade
    from .gates import GateHost
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


# The E-item owing each unbuilt phase body, so an empty assessment says WHY
# it is empty rather than merely being empty. SCAN dropped here in E-46 and
# DISCOVER in E-48: their bodies are built, so nothing owes them.
PHASE_OWNER: dict[PhaseId, str] = {
    PhaseId.ASSESS: "E-49",
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
            f"{phase.value} not implemented ({PHASE_OWNER[phase]})"))


def skipped(phase: PhaseId) -> PhaseResult:
    """A phase that exists but was never reached, because the repository was
    not admitted (FR-903 / ADR-18)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected(
            "not run: repository not admitted (FR-903)"))


# Deterministic given a tree; the retry covers FS/git blips only. Mirrors
# triage's SIGNAL_ACT, which these signals are the Tier 2 analogue of.
SCAN_ACT = dict(start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=2))
TREE_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3))

# Registry `activity` names resolved to the callables. A name the registry
# declares and this table lacks is a boot-time KeyError in _scan rather than a
# silent skip, which is why test_scan_stub_activities asserts they agree.
SCAN_ACTIVITIES = {
    "scan_packages": scan_packages,
    "scan_schema": scan_schema,
    "scan_entrypoints": scan_entrypoints,
    "scan_frontend": scan_frontend,
    "scan_security_static": scan_security_static,
    "scan_config_infra": scan_config_infra,
    "scan_sensitivity": scan_sensitivity,
    "scan_tests_inventory": scan_tests_inventory,
    "scan_coverage": scan_coverage,
    "scan_testability": scan_testability,
    "scan_ci": scan_ci,
}


class ScanOutcome(BaseModel):
    """scan's two halves, mirroring InitOutcome: a failed phase yields a row
    but no artifact.

    `tree_hash` travels with them because discover keys its memo on the same
    tree scan did (DD10). Resolving it a second time would let the two phases
    describe different trees if a concurrent write landed between them.
    """
    result: PhaseResult
    scan: ScanResult | None = None
    tree_hash: str = ""


DISCOVER_ACT = dict(start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=RetryPolicy(maximum_attempts=2))
# Three attempts, not two: an IdentityConflictError means a concurrent
# assessment wrote first, and a retry re-reads the registry and re-matches
# (E-47a's loser behaviour) rather than replaying computed attachments.
LOCK_ACT = dict(start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=3))


class DiscoverOutcome(BaseModel):
    """discover's two halves, mirroring ScanOutcome."""
    result: PhaseResult
    map: CapabilityMap | None = None


def no_discover(reason: str) -> DiscoverOutcome:
    """DD9's phase-level failure: the capability set itself could not be
    produced, so there is no map. Everything short of that degrades
    per-report INSIDE the map instead."""
    return DiscoverOutcome(result=PhaseResult(
        phase=PhaseId.DISCOVER, collected=Measurement.not_collected(reason)))


def skipped_scan_signal(signal_id: ScanSignalId,
                        reason: str) -> ScanSignalResult:
    """A signal that did not run. Its owed categories come from the artifact's
    declaration, so a failed signal reports not_collected for exactly those
    rather than leaving them unreported (the E-42 D8a discipline)."""
    nc = Measurement.not_collected(reason)
    return ScanSignalResult(
        signal=signal_id, family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.COMPUTED, collected=nc,
        categories={k: nc for k in CATEGORIES[signal_id]})


def fold_row(activity_row: ScanSignalResult,
             half: InheritedHalf | None) -> ScanSignalResult:
    """Union the activity's computed half with the inherited half (D7).

    The inherited half wins its OWN categories and nothing else -- it is the
    authority on what Tier 0 measured, and the activity is the authority on
    what this phase computed. Neither can overwrite the other's keys.
    """
    if half is None:
        return activity_row
    return activity_row.model_copy(update={
        "source": SignalSource.EXTENDED,
        "producer": half.producer,
        "categories": activity_row.categories | half.categories,
    })


def _collected_from_categories(
        categories: Mapping[str, Measurement]) -> Measurement:
    """A signal's overall collected state, DERIVED from its category
    measurements: measured (record count) when every owed category measured,
    else not_collected carrying a representative reason.

    The row-level analogue of compute_readiness deriving a verdict from its
    dimensions. Used for a purely-inherited signal (SS2), whose row has no
    activity to set `collected` -- hardcoding not_collected would report a
    measured inherited fact as unmeasured, the reverse of the FR-915
    conflation the type exists to prevent.
    """
    if categories and all(
            m.state is CollectionState.MEASURED for m in categories.values()):
        return Measurement.measured(
            sum(m.value or 0.0 for m in categories.values()))
    nc = next((m for m in categories.values()
               if m.state is not CollectionState.MEASURED), None)
    return Measurement.not_collected(
        nc.reason if nc and nc.reason
        else "one or more owed categories not measured")


def _inherited_row(signal_id: ScanSignalId,
                   half: InheritedHalf) -> ScanSignalResult:
    """A purely-inherited signal's row (SS2): the half IS the whole signal.

    source is INHERITED, not EXTENDED -- D12 cut the computed half, so there
    is no activity contribution to extend. `collected` is derived from the
    categories the half carried, so a triage signal that collected reads as
    collected here (FR-915).
    """
    return ScanSignalResult(
        signal=signal_id, family=family_of(signal_id),
        version=SCAN_SIGNALS[signal_id].version,
        source=SignalSource.INHERITED,
        collected=_collected_from_categories(half.categories),
        categories=dict(half.categories),
        producer=half.producer)


def upstream_for(signal_id: ScanSignalId,
                 outputs: Mapping[ScanSignalId, SignalOutput]) -> ScanUpstream:
    """Everything one signal is allowed to read: the payloads AND the row
    states of the signals it declares in `consumes`.

    `consumes` already drives the fan-out wave (wave_of) and the memo key
    (rules_sha). Driving the payload from the SAME declaration makes reading
    undeclared data impossible rather than merely discouraged -- otherwise a
    wave-2 signal could read an S1 candidate while declaring only S3, and
    editing S1's pattern table would not move its memo key. That is the
    precise stale-cache setup D10 exists to prevent.

    `collected` travels with the payloads so a dependent signal can tell "the
    upstream measured zero" from "the upstream did not collect" (P3-D4) --
    the same pair merge() has always taken.
    """
    consumes = SCAN_SIGNALS[signal_id].consumes
    present = [c for c in consumes if c in outputs]
    return ScanUpstream(
        sources=sorted((c for sid in present for c in outputs[sid].sources),
                       key=lambda c: (c.signal.value, c.local_id)),
        tests=sorted((t for sid in present for t in outputs[sid].tests),
                     key=lambda t: t.path),
        collected={sid: outputs[sid].row.collected for sid in present})


def _merged_row(out: MergeOutput) -> ScanSignalResult:
    """S5's row. COMPUTED with no producer: S5 inherits nothing -- it is a
    derivation over signals this phase computed, which is why it runs in
    workflow code rather than as an activity (D6)."""
    return ScanSignalResult(
        signal=ScanSignalId.S5, family=family_of(ScanSignalId.S5),
        version=SCAN_SIGNALS[ScanSignalId.S5].version,
        source=SignalSource.COMPUTED,
        collected=out.collected,
        categories={C_MERGE: out.collected})


def assemble(repo_dir: str, init: InitOutcome, admitted: bool, reason: str,
             rest: list[PhaseResult] | None = None,
             scan: ScanResult | None = None,
             discover: CapabilityMap | None = None) -> Assessment:
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
                f"unreached phases; supply every non-init result")
    phases = [init.result] + [by_id.get(p, skipped(p)) for p in owed]
    t = init.triage
    return Assessment(
        repo_dir=repo_dir,
        commit_sha=t.commit_sha if t else "",
        toolchain=t.toolchain if t else None,
        triage=t, admitted=admitted, admission_reason=reason,
        phases=phases, terminal_status=terminal_status(admitted, phases),
        scan=scan, discover=discover)


@workflow.defn
class AssessmentWorkflow(GateHost):
    """Inherits GateHost although it opens no gate of its own: status,
    pending_decisions and submit_gate_decision come free, and E-50's
    assessment gate checks will open gates here."""

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
                TriageInput(repo_dir=inp.repo_dir, commit=inp.commit,
                            build_probe=inp.build_probe,
                            advisory_source=inp.advisory_source,
                            gates=inp.gates),
                id=f"{workflow.info().workflow_id}-triage",
                task_queue=workflow.info().task_queue)
        except Exception as e:                        # noqa: BLE001
            return InitOutcome(result=PhaseResult(
                phase=PhaseId.INIT,
                collected=Measurement.not_collected(
                    f"triage child failed: "
                    f"{type(e).__name__}: {e}"[:300])))
        return InitOutcome(
            result=PhaseResult(phase=PhaseId.INIT,
                               collected=Measurement.measured(1.0)),
            triage=triage)

    async def _scan(self, inp: AssessmentInput,
                    triage: RepoTriage) -> ScanOutcome:
        """Phase 2 (E-46). Thirteen signals: eleven activities across two
        waves, plus S5's merge and SS2's pure inheritance in workflow code.

        Nothing here executes the assessed repository's code -- every signal
        reads blob bytes at the pinned commit (NFR-9, D12).
        """
        try:
            tree: AssessmentTree = await workflow.execute_activity(
                assessment_resolve_tree,
                AssessmentTreeInput(repo_dir=inp.repo_dir,
                                    commit_sha=triage.commit_sha),
                **TREE_ACT)
        except Exception as e:                          # noqa: BLE001
            # Without a tree hash nothing can be memoized or reproduced, so a
            # scan that proceeded would be unverifiable.
            return ScanOutcome(result=PhaseResult(
                phase=PhaseId.SCAN,
                collected=Measurement.not_collected(
                    f"could not resolve the tree hash: "
                    f"{type(e).__name__}: {e}"[:300])))

        halves = inherited_halves(triage)
        outputs: dict[ScanSignalId, SignalOutput] = {}

        for wave in WAVES:
            jobs = []
            for sid in wave:
                # D10: each signal's upstream is filtered to the signals it
                # declares in `consumes`, so reading undeclared data is
                # impossible and rules_sha (same `consumes`) cannot miss it.
                arg = ScanSignalInput(
                    repo_dir=inp.repo_dir, commit_sha=triage.commit_sha,
                    tree_hash=tree.tree_hash,
                    upstream=upstream_for(sid, outputs))
                jobs.append(run_or_degrade(
                    SCAN_ACTIVITIES[SCAN_SIGNALS[sid].activity], arg,
                    SCAN_ACT,
                    fallback=lambda sid=sid: SignalOutput(
                        row=skipped_scan_signal(
                            sid, f"{sid.value} activity failed or timed out"))))
            results = await asyncio.gather(*jobs)
            outputs.update(zip(wave, results))

        # SS2 is purely inherited (D12 cut its computed half), so the half IS
        # the signal: it reads INHERITED and collected when triage collected,
        # not as a skipped stub.
        for sid in SCAN_ORDER:
            if sid in outputs or SCAN_SIGNALS[sid].activity \
                    or sid is ScanSignalId.S5:
                continue
            half = halves.get(sid)
            outputs[sid] = SignalOutput(
                row=_inherited_row(sid, half) if half is not None
                else skipped_scan_signal(
                    sid, f"{sid.value} has no activity and no inherited half"))

        # S5 last: it is a merge over the other source signals' candidates,
        # filtered by its declared `consumes` (the same declaration that
        # drives its wave and its memo key), so it cannot read undeclared
        # data. Its candidates are the phase's headline output.
        merged_upstream = upstream_for(ScanSignalId.S5, outputs)
        merged = merge(merged_upstream.sources, merged_upstream.collected)
        outputs[ScanSignalId.S5] = SignalOutput(row=_merged_row(merged))

        # Activity signals get their inherited half folded in (D7); the
        # synthesized rows above are already final (SS2 IS its half; S5 has
        # no half to fold), so fold_row would wrongly promote SS2 to EXTENDED.
        rows = [fold_row(outputs[sid].row, halves.get(sid))
                if SCAN_SIGNALS[sid].activity else outputs[sid].row
                for sid in SCAN_ORDER]
        sources = sorted(
            (c for out in outputs.values() for c in out.sources),
            key=lambda c: (c.signal.value, c.local_id))
        scan = ScanResult(
            signals=rows,
            sources=sources,
            candidates=merged.candidates,
            data_sensitivity=sorted(
                (r for out in outputs.values() for r in out.data_sensitivity),
                key=lambda r: (r.classification.value, r.entity)),
            testability=sorted(
                (f for out in outputs.values() for f in out.testability),
                key=lambda f: (f.path, f.pattern, f.key)),
            security=sorted(
                (o for out in outputs.values() for o in out.security),
                key=lambda o: (o.signal.value, o.category, o.path, o.rule,
                               o.line or 0)),
            tests=sorted((t for out in outputs.values() for t in out.tests),
                         key=lambda t: t.path),
            coverage=sorted(
                (c for out in outputs.values() for c in out.coverage),
                key=lambda c: (c.scope, c.path)),
            ci=sorted((c for out in outputs.values() for c in out.ci),
                      key=lambda c: (c.workflow, c.order, c.stage)),
            environments=sorted(
                (e for out in outputs.values() for e in out.environments),
                key=lambda e: e.name))
        measured = sum(
            1 for r in rows
            if r.collected.state is CollectionState.MEASURED)
        return ScanOutcome(
            result=PhaseResult(phase=PhaseId.SCAN,
                               collected=Measurement.measured(float(measured))),
            scan=scan, tree_hash=tree.tree_hash)

    async def _discover(self, inp: AssessmentInput, triage: RepoTriage,
                        scan_out: ScanOutcome) -> DiscoverOutcome:
        """Phase 3 (E-48). DD4's pipeline, minus the proposer plan 3 inserts
        between `baseline_dispositions` and `stamp`.

        Nothing here executes the assessed repository's code -- both
        activities read blob bytes at the pinned commit (NFR-9).
        """
        if scan_out.scan is None:
            return no_discover(
                f"scan produced no result: {scan_out.result.collected.reason}")
        s5 = next((r for r in scan_out.scan.signals
                   if r.signal is ScanSignalId.S5), None)
        if s5 is None or s5.collected.state is not CollectionState.MEASURED:
            # DD9's first row. Without a candidate set there is nothing to
            # dispose over, and an empty map would claim the repository has
            # no capabilities rather than that the scan could not see them.
            return no_discover(
                f"S5 did not collect: "
                f"{s5.collected.reason if s5 else 'no S5 row'}")

        try:
            context = await workflow.execute_activity(
                discover_context,
                DiscoverContextInput(
                    repo_dir=inp.repo_dir, commit_sha=triage.commit_sha,
                    tree_hash=scan_out.tree_hash, scan=scan_out.scan),
                **DISCOVER_ACT)
        except Exception as e:                          # noqa: BLE001
            return no_discover(
                f"discover_context failed: {type(e).__name__}: {e}"[:300])
        if context.collected.state is not CollectionState.MEASURED:
            return no_discover(
                f"the context could not be built: {context.collected.reason}")

        # P2-D6: NO_PROPOSER, never "". Plan 3 passes the role's prompt_sha
        # and model here, and a baseline-only map must never share a key with
        # a proposer map.
        memo_key = DiscoverMemoInput(
            project=inp.project_key, tree_hash=scan_out.tree_hash,
            context_digest=context_digest(context),
            prompt_sha=NO_PROPOSER, model=NO_PROPOSER)
        # A cache read that fails is a MISS, never a phase failure.
        hit = await run_or_degrade(discover_memo_load, memo_key,
                                   DISCOVER_ACT, fallback=lambda: None)
        if hit is not None:
            return DiscoverOutcome(
                result=PhaseResult(phase=PhaseId.DISCOVER,
                                   collected=hit.collected), map=hit)

        # Plan 3 replaces `None` with the proposer's DiscoverProposal; stamp()
        # already knows what to do with either (DD7).
        applied = apply(context, stamp(context, None))

        try:
            lock = await workflow.execute_activity(
                discover_lock,
                DiscoverLockInput(
                    project=inp.project_key, run_id=workflow.info().run_id,
                    proposed=[ProposedCapability(local_key=c.local_key,
                                                 fingerprint=fingerprint_of(c))
                              for c in applied.locked]),
                **LOCK_ACT)
        except Exception as e:                          # noqa: BLE001
            # E-47a's fail-closed rule (DD9): proceeding produces a complete,
            # plausible-looking map in which every id is wrong.
            return no_discover(
                f"identity lock failed: {type(e).__name__}: {e}"[:300])

        bc_of = {a.local_key: a.bc_id for a in lock.attachments}
        try:
            finalized = await run_or_degrade(
                discover_finalize,
                DiscoverFinalizeInput(
                    repo_dir=inp.repo_dir, commit_sha=triage.commit_sha,
                    members={bc_of[c.local_key]: list(c.members)
                             for c in applied.locked},
                    entry_point_paths=list(context.entry_point_paths),
                    schema_collected=schema_collected(scan_out.scan),
                    contract_collected=contract_collected(scan_out.scan)),
                DISCOVER_ACT,
                fallback=lambda: no_finalize(
                    "discover_finalize did not run to completion"))
            capability_map = build_map(
                applied, bc_of, advisories=lock.advisories,
                attribution=finalized.attribution,
                decomposition=finalized.decomposition,
                ownership=finalized.ownership)
        except Exception as e:                          # noqa: BLE001
            # build_map raises only on a lock defect (a boundary with no
            # bc_id). Reporting it as a phase failure keeps the reason on the
            # artifact instead of retrying a workflow task forever.
            return no_discover(
                f"the map could not be assembled: "
                f"{type(e).__name__}: {e}"[:300])

        await run_or_degrade(
            discover_memo_store,
            DiscoverMemoStoreInput(key=memo_key,
                                   registry_version=lock.registry_version,
                                   out=capability_map),
            DISCOVER_ACT, fallback=lambda: False)
        return DiscoverOutcome(
            result=PhaseResult(phase=PhaseId.DISCOVER,
                               collected=capability_map.collected),
            map=capability_map)

    async def _assess(self, inp: AssessmentInput) -> PhaseResult:
        """E-49 owns this body: UnifiedRiskMap + risk proposers."""
        return unbuilt(PhaseId.ASSESS)

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
            return self._done(assemble(inp.repo_dir, init, False,
                                       init.result.collected.reason))

        ok, why = admits(init.triage, require_human=True)
        if not ok:
            return self._done(assemble(inp.repo_dir, init, False, why))

        self._status = "running"
        scan_out = await self._scan(inp, init.triage)
        discover_out = await self._discover(inp, init.triage, scan_out)
        rest = [
            scan_out.result,
            discover_out.result,
            await self._assess(inp),
            await self._report(inp),      # AFTER assess -- FR-911 dev. (a)
            await self._generate(inp),
            await self._finish(inp),
        ]
        return self._done(assemble(inp.repo_dir, init, True, why, rest,
                                   scan=scan_out.scan,
                                   discover=discover_out.map))
