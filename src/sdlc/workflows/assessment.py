"""AssessmentWorkflow (E-45) -- Tier 2's shell.

The EDCR DAG (init -> scan -> discover -> assess -> report -> generate ->
finish) as a durable workflow, with six of seven phase bodies deliberately
unbuilt: scan is E-46, discover E-48, assess E-49, finish E-51, report and
generate E-52.

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

from pydantic import BaseModel, Field
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ..assessment.models import (
        PHASE_ORDER,
        Assessment,
        InitOutcome,
        PhaseId,
        PhaseResult,
        terminal_status,
    )
    from ..measurement import Measurement
    from ..models import GateSettings
    from ..triage.admission import admits
    from ..triage.models import RepoTriage
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


# The E-item owing each unbuilt phase body, so an empty assessment says WHY
# it is empty rather than merely being empty.
PHASE_OWNER: dict[PhaseId, str] = {
    PhaseId.SCAN: "E-46",
    PhaseId.DISCOVER: "E-48",
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


def assemble(repo_dir: str, init: InitOutcome, admitted: bool, reason: str,
             rest: list[PhaseResult] | None = None) -> Assessment:
    """The ONLY constructor of an Assessment and the only caller of
    terminal_status: one place where the artifact is built means the derived
    status cannot disagree with the phase list it was derived from.

    Unreached phases are filled rather than omitted, so `phases` is always
    the whole DAG and anything rendering it can rely on that.
    """
    by_id = {p.phase: p for p in (rest or [])}
    phases = [init.result] + [by_id.get(p, skipped(p))
                              for p in PHASE_ORDER if p is not PhaseId.INIT]
    t = init.triage
    return Assessment(
        repo_dir=repo_dir,
        commit_sha=t.commit_sha if t else "",
        toolchain=t.toolchain if t else None,
        triage=t, admitted=admitted, admission_reason=reason,
        phases=phases, terminal_status=terminal_status(admitted, phases))


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

    async def _scan(self, inp: AssessmentInput) -> PhaseResult:
        """E-46 owns this body: S1-S5 / SS1-SS4 / QS1-QS4 signals, memoized
        on (tree hash, signal version) per FR-912."""
        return unbuilt(PhaseId.SCAN)

    async def _discover(self, inp: AssessmentInput) -> PhaseResult:
        """E-48 owns this body: D1-D8 discover proposers."""
        return unbuilt(PhaseId.DISCOVER)

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
        rest = [
            await self._scan(inp),
            await self._discover(inp),
            await self._assess(inp),
            await self._report(inp),      # AFTER assess -- FR-911 dev. (a)
            await self._generate(inp),
            await self._finish(inp),
        ]
        return self._done(assemble(inp.repo_dir, init, True, why, rest))
