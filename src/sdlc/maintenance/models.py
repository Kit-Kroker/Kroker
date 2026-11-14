"""The maintenance domain models (023a T005, data-model.md).

Pure pydantic, ``extra="forbid"`` throughout: this package owns its
artifacts and a typo'd or smuggled key is refused loudly (root AGENTS.md).
The producer-owns-artifacts rule places this module beside triage's models:
maintenance is a non-pipeline domain package that imports triage TYPES
(``RepoTriage``, ``TriageFinding``) and never calls triage code.

There is deliberately NO gate-configuration surface here (R9): the repair
gate is built in code (``gate.py``), and ``MaintenanceConfig`` exposes only
the threshold (bounded) and the gate timeout. Any ``gates`` / ``policy`` /
``on_timeout`` key is an unknown field and fails validation with the field
named.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..core.models import GateDecision
from ..triage.models import RepoTriage, TriageFinding
from ..triage.signals import build_probe, dependencies, secrets

# The signal set Detect keeps after the triage child runs (R5). The other
# four triage signals run but are ignored in 023a.
DETECT_SIGNALS: frozenset[str] = frozenset(
    {secrets.SIGNAL_ID, build_probe.SIGNAL_ID, dependencies.SIGNAL_ID}
)

# The guard on `prev`: beyond this many findings the cycle records
# detect_truncated and opens nothing, rather than guess on a partial
# picture (R6).
MAX_PREV_FINDINGS = 2000

# project slug: the workflow id is maint-<project>.
_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class IncidentState(StrEnum):
    """The incident machine (data-model.md). Terminal states keep their
    incidents in `MaintenanceState.incidents` for the query; a later NEW of
    the same key opens a fresh incident with a fresh `no`."""

    OPEN = "open"
    AWAITING_DECISION = "awaiting_decision"
    APPROVED_NOT_EXECUTED = "approved_not_executed"  # terminal in 023a
    REJECTED = "rejected"  # terminal
    TIMED_OUT = "timed_out"  # terminal
    RESOLVED_EXTERNALLY = "resolved_externally"  # terminal
    ESCALATED = "escalated"  # terminal
    WITHDRAWN = "withdrawn"  # terminal
    DEFERRED = "deferred"  # non-terminal: picked up next cycle


#: States that never match the duplicate-key rule again (R7): a NEW of the
#: same key after a terminal incident opens a fresh incident.
TERMINAL_INCIDENT_STATES: frozenset[IncidentState] = frozenset(
    {
        IncidentState.APPROVED_NOT_EXECUTED,
        IncidentState.REJECTED,
        IncidentState.TIMED_OUT,
        IncidentState.RESOLVED_EXTERNALLY,
        IncidentState.ESCALATED,
        IncidentState.WITHDRAWN,
    }
)


class MaintenanceConfig(BaseModel):
    """The registration (FR-001/002/011). Enabling a project IS registering
    it; the workflow's durable state is the record (no new store).

    Deliberately absent (R9): any gate configuration. `threshold` (bounded
    0.5..1.0) and `gate_timeout_hours` are the only gate-adjacent fields,
    because the gate config itself is built in code by `gate.py`.
    """

    model_config = ConfigDict(extra="forbid")

    project: str
    repo_dir: str
    default_branch: str = "main"
    build_probe: bool = True
    # R14/NFR-9: the probe executes the repository's own code unattended;
    # enabling it requires the explicit acknowledgement, and the CLI offers
    # --no-build-probe as the escape.
    ack_unattended_build_probe: bool = False
    advisory_source: Literal["none", "osv"] = "none"
    threshold: float = Field(default=0.8, ge=0.5, le=1.0)
    gate_timeout_hours: int = Field(default=48, ge=1, le=168)
    max_plan_attempts: int = Field(default=2, ge=1, le=3)
    max_new_incidents_per_cycle: int = Field(default=10, ge=1, le=50)
    max_cycles_per_history: int = Field(default=50, ge=1)

    @field_validator("project")
    @classmethod
    def _project_slug(cls, v: str) -> str:
        if not _PROJECT_RE.match(v):
            raise ValueError(
                "project must match ^[a-z0-9][a-z0-9-]{0,62}$ (lowercase "
                "alphanumerics and dashes, 1..63 chars); the workflow id is "
                "maint-<project>"
            )
        return v

    @field_validator("repo_dir")
    @classmethod
    def _absolute_repo_dir(cls, v: str) -> str:
        import os

        if not os.path.isabs(v):
            raise ValueError("repo_dir must be an absolute path")
        return v

    @model_validator(mode="after")
    def _probe_needs_ack(self) -> MaintenanceConfig:
        if self.build_probe and not self.ack_unattended_build_probe:
            raise ValueError(
                "build_probe=True requires ack_unattended_build_probe=True: "
                "the probe runs the repository's own code unattended (NFR-9); "
                "pass --ack-unattended-build-probe or use --no-build-probe"
            )
        return self


class MaintenanceKickInput(BaseModel):
    """The schedule kicker's input (workflow-wire.md). Lives here, in the
    domain package, so the schedules package depends on maintenance models
    only — not on the workflow module."""

    model_config = ConfigDict(extra="forbid")

    project: str

    @field_validator("project")
    @classmethod
    def _project_slug(cls, v: str) -> str:
        if not _PROJECT_RE.match(v):
            raise ValueError(
                "project must match ^[a-z0-9][a-z0-9-]{0,62}$; the kicker signals maint-<project>"
            )
        return v


class Baseline(BaseModel):
    """What already existed when the loop was enabled (FR-007): the first
    cycle records it and opens nothing."""

    model_config = ConfigDict(extra="forbid")

    identities: frozenset[str] = frozenset()
    signal_versions: dict[str, int] = Field(default_factory=dict)
    recorded_cycle: int = 1
    commit_sha: str = ""


class RepairAction(BaseModel):
    """One proposed action. In 023a nothing executes, so actions are
    recorded as proposed (FR-009)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["code_fix", "ops"]
    summary: str
    target_paths: list[str] = Field(default_factory=list)  # code_fix
    ops_action: Literal["rollback", "restart", "scale"] | None = None


class RepairProposal(BaseModel):
    """The maintainer's `output_type`. Field order is evidence first
    (AP-1.4 / ADR-24): the analysis justifies the actions, which justify
    the self-rating — never the reverse."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(max_length=4000)
    actions: list[RepairAction] = Field(min_length=0, max_length=5)
    self_confidence: float = Field(ge=0.0, le=1.0)


class RepairPlan(BaseModel):
    """What the workflow records on the incident: the proposal plus the
    code-computed floor and the effective confidence — the lower of the two
    (FR-010)."""

    model_config = ConfigDict(extra="forbid")

    analysis: str = Field(max_length=4000)
    actions: list[RepairAction] = Field(min_length=0, max_length=5)
    self_confidence: float = Field(ge=0.0, le=1.0)
    floor: float = Field(ge=0.0, le=1.0)
    effective: float = Field(ge=0.0, le=1.0)
    author_model: str

    @model_validator(mode="after")
    def _effective_is_the_lower(self) -> RepairPlan:
        if self.effective != min(self.self_confidence, self.floor):
            raise ValueError(
                f"effective must equal min(self_confidence={self.self_confidence}, "
                f"floor={self.floor}); got {self.effective} — the cap is the whole "
                f"point of FR-010"
            )
        return self


class Incident(BaseModel):
    """One incident, keyed by a finding identity or the synthetic
    `<signal>:not_collected::` (FR-008)."""

    model_config = ConfigDict(extra="forbid")

    no: int  # INC-<no> when rendered; code-assigned, never reused
    key: str
    kind: Literal["finding", "detect_escalation"]
    finding: TriageFinding | None = None
    commit_sha: str  # the commit pinned at the detecting cycle
    first_seen_cycle: int
    last_seen_cycle: int
    seen_count: int = 1
    state: IncidentState = IncidentState.OPEN
    plan: RepairPlan | None = None
    plan_attempts: int = 0
    decision: GateDecision | None = None  # carries decided_by (FR-012)
    note: str = ""  # reason text: analysis_failed / withdrawn / deferred / ...


class MaintenanceState(BaseModel):
    """The workflow input and the `continue_as_new` carry (R4/FR-013).
    Temporal is the single source of truth (ADR-8): this object IS the
    loop's durable record."""

    model_config = ConfigDict(extra="forbid")

    config: MaintenanceConfig
    cycle: int = 1
    baseline: Baseline | None = None
    prev: RepoTriage | None = None
    incidents: list[Incident] = Field(default_factory=list)
    not_collected_streak: dict[str, int] = Field(default_factory=dict)
    next_incident_no: int = 1  # code-assigned incident numbers, never reused
    nudged: bool = False  # carried so a boundary nudge is not lost

    @model_validator(mode="after")
    def _unique_keys_among_non_terminal(self) -> MaintenanceState:
        """R7: no two NON-terminal incidents may share a key. Terminal
        incidents stay in the list; a NEW of the same key afterwards opens a
        fresh incident with a fresh `no`."""
        seen: dict[str, int] = {}
        for inc in self.incidents:
            if inc.state in TERMINAL_INCIDENT_STATES:
                continue
            if inc.key in seen:
                raise ValueError(
                    f"duplicate incident key {inc.key!r} among non-terminal "
                    f"incidents (INC-{seen[inc.key]} and INC-{inc.no}): no two "
                    f"open incidents may share an identity (FR-008)"
                )
            seen[inc.key] = inc.no
        return self


class MaintenanceSummary(BaseModel):
    """The `maintenance_state` query payload (workflow-wire.md)."""

    model_config = ConfigDict(extra="forbid")

    project: str
    cycle: int
    baseline_recorded: bool
    running_cycle: bool
    open_gates: int
    not_collected_streak: dict[str, int] = Field(default_factory=dict)
    ack_unattended_build_probe: bool
