"""FR-911 (E-45): the EDCR assessment artifact.

Pure by design -- Pydantic, measurement.py and triage/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
triage/models.py and capability/models.py must not: a dependency here would
appear as a reviewable import.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ..measurement import CollectionState, Measurement
from ..triage.models import RepoTriage
from .scan.models import ScanResult


class PhaseId(str, Enum):
    """The EDCR DAG in execution order.

    REPORT follows ASSESS deliberately -- FR-911 deviation (a). The source
    methodology numbers report 4th and assess 5th, but reports render risk
    scores only assess produces, and /finish requires all five reports
    complete. Declaration order IS the DAG order (see PHASE_ORDER), so there
    is no second list to disagree with this one.
    """
    INIT = "init"
    SCAN = "scan"
    DISCOVER = "discover"
    ASSESS = "assess"
    REPORT = "report"
    GENERATE = "generate"
    FINISH = "finish"


# Derived from the enum, never restated: a hand-written tuple beside the enum
# is a second registry, and this codebase has paid for one of those before.
PHASE_ORDER: tuple[PhaseId, ...] = tuple(PhaseId)

BLOCKED = "blocked:admission"
NO_PHASES = "admitted:no-phases-implemented"
PARTIAL = "assessed:partial"
ASSESSED = "assessed"


class PhaseResult(BaseModel):
    """One phase's outcome.

    `collected` is a Measurement, not a bool: a phase whose body is a later
    E-item reports not_collected naming that item, which is distinguishable
    from a phase that ran and found nothing (FR-915). There is deliberately
    NO generic payload field -- each later item adds its own TYPED field to
    Assessment, because an untyped bag would be a schema-less hole in the one
    artifact handed to a customer under FR-921.
    """
    phase: PhaseId
    collected: Measurement


class InitOutcome(BaseModel):
    """init's two halves: the phase row that lands in `phases`, and the
    artifact the admission rule reads. Separate because a failed triage child
    yields a row but no triage."""
    result: PhaseResult
    triage: RepoTriage | None = None


def terminal_status(admitted: bool, phases: list[PhaseResult]) -> str:
    """Derived, never assigned (D6), so E-46 landing changes the status with
    no workflow edit and no second place to update.

    Judged on post-init phases: init is the admission step, not an assessment
    of anything, so an admitted run whose every real phase is a stub reports
    NO_PHASES rather than a misleading ASSESSED.
    """
    if not admitted:
        return BLOCKED
    rest = [p for p in phases if p.phase is not PhaseId.INIT]
    done = [p for p in rest
            if p.collected.state is CollectionState.MEASURED]
    if not done:
        return NO_PHASES
    if len(done) < len(rest):
        return PARTIAL          # the seam FR-922's budgets (E-55) reuse
    return ASSESSED


class Assessment(BaseModel):
    repo_dir: str
    commit_sha: str = ""            # "" only when init failed to pin one
    toolchain: str | None = None
    # init's artifact -- in-history evidence (D3). None ONLY when the child
    # workflow itself failed, which is the one case where admission was never
    # consulted.
    triage: RepoTriage | None = None
    admitted: bool
    admission_reason: str           # admits()' reason, verbatim
    phases: list[PhaseResult] = Field(default_factory=list)
    terminal_status: str
    # E-46's typed field. There is deliberately no generic payload bag: each
    # later item adds its OWN typed field, because an untyped bag would be a
    # schema-less hole in the one artifact handed to a customer (FR-921).
    scan: ScanResult | None = None

    @model_validator(mode="after")
    def _no_triage_means_not_admitted(self) -> Assessment:
        if self.triage is None and self.admitted:
            raise ValueError(
                "admitted with no triage -- admission is a function of a "
                "RepoTriage (FR-903), so this state is a contradiction")
        return self

    @model_validator(mode="after")
    def _phases_are_the_whole_dag(self) -> Assessment:
        got = tuple(p.phase for p in self.phases)
        if got != PHASE_ORDER:
            raise ValueError(
                f"phases must be the whole DAG in order -- expected "
                f"{[p.value for p in PHASE_ORDER]}, got "
                f"{[p.value for p in got]}")
        return self

    @model_validator(mode="after")
    def _terminal_status_matches_derivation(self) -> Assessment:
        # terminal_status is DERIVED from (admitted, phases), never assigned
        # (D6) -- enforced at the type, like the two above, so a deserialized
        # or second-construction-path payload cannot silently disagree (E-45
        # review finding 2). `terminal_status(...)` here is the module
        # function; `self.terminal_status` is the field.
        expected = terminal_status(self.admitted, self.phases)
        if self.terminal_status != expected:
            raise ValueError(
                f"terminal_status {self.terminal_status!r} does not match "
                f"the derived {expected!r} for admitted={self.admitted} "
                f"and these phases -- the status is derived, never assigned "
                f"(D6)")
        return self

    @model_validator(mode="after")
    def _scan_agrees_with_its_phase(self) -> Assessment:
        """The payload and its phase row cannot contradict each other, the
        same guarantee _terminal_status_matches_derivation gives the status.

        A not_collected SCAN phase carrying a ScanResult would be an
        assessment claiming it did not scan while shipping scan output.
        """
        row = next((p for p in self.phases if p.phase is PhaseId.SCAN), None)
        if row is None:                       # unreachable: the DAG validator
            return self                       # already required every phase
        measured = row.collected.state is CollectionState.MEASURED
        if measured and self.scan is None:
            raise ValueError(
                "scan phase is measured but no ScanResult is present -- a "
                "measured phase produced an artifact by definition")
        if not measured and self.scan is not None:
            raise ValueError(
                f"scan phase is {row.collected.state.value} but a ScanResult "
                f"is present -- an assessment cannot claim it did not scan "
                f"while shipping scan output")
        return self
