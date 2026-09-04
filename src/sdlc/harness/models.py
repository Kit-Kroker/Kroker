"""Harness session, containment, and result models (spec A §2.2).

Owned by the horizontal harness package. HarnessKind stays in core/models.py
per Rule 6.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
)

from ..core.models import (
    ArtifactRef,
    HarnessKind,
)


class SessionEvent(BaseModel):
    """One normalised harness-transcript event (ADR-16). Harness-agnostic;
    adapters map their native streams onto this schema."""

    kind: str  # model_turn | tool_call | tool_result | file_read
    # | file_write | command | compaction | result
    # | tool_denied
    tool: str | None = None
    target: str | None = None  # file path or command line (scrubbed)
    exit_code: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    text: str | None = None  # payload (scrubbed)


class HarnessSession(BaseModel):
    """Canonical transcript of one harness run (ADR-16). NEVER enters
    workflow state — serialized to JSONL and claim-checked (E-38)."""

    harness: HarnessKind
    session_id: str | None = None
    model: str | None = None
    events: list[SessionEvent] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class SessionDigest(BaseModel):
    """BENCHMARK §4.3 waste aggregates + decision-skeleton. Small and
    bounded — travels inline on HarnessRunResult; always kept, even when
    the full transcript is downgraded at retro (OQ-B7)."""

    tool_calls: int = 0
    file_reads: int = 0
    file_rereads: int = 0  # same path read more than once
    files_written: int = 0  # distinct paths written
    rewrite_churn: int = 0  # paths written more than once
    failed_commands: int = 0  # command events with exit_code not in (0, None)
    model_turns: int = 0
    compacted: bool = False
    denials: int = 0  # E-16: blocked tool calls
    escalations: int = 0  # E-17: tool calls that raised a gate
    input_tokens: int | None = None
    output_tokens: int | None = None
    decision_skeleton: list[str] = Field(default_factory=list)


class ContainmentLayer(StrEnum):
    """Where a containment rule is enforced (E-15/E-16, ADR-17)."""

    NATIVE = "native"  # declarative deny inside the harness CLI's own config
    HOOK = "hook"  # per-call inspection callback


class ToolDenial(BaseModel):
    """One blocked tool call. Small and bounded — travels inline on
    HarnessRunResult, same discipline as SessionDigest."""

    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None  # path or command line (scrubbed)
    # E-17: this denial was an ESCALATE rule the hook could not escalate
    # (batched call, or an unreadable transcript). No human was asked. It is
    # marked so the BATCHED outcome stays countable — see EscalationOutcome.
    escalation_declined: bool = False


class ContainmentReport(BaseModel):
    """What containment was ACTUALLY in force for a run. Partial coverage
    is recorded rather than refused, so a harness with fewer layers is
    visibly less contained instead of silently so (spec §5)."""

    enabled: bool = False
    layers_active: list[ContainmentLayer] = Field(default_factory=list)
    rules_enforced: list[str] = Field(default_factory=list)
    rules_unenforceable: list[str] = Field(default_factory=list)
    # E-17: rules that can actually raise a gate on THIS harness. Empty on a
    # harness without `defer`, so degradation is visible rather than silent.
    rules_escalatable: list[str] = Field(default_factory=list)


class DeferredToolUse(BaseModel):
    """A tool call the harness suspended at, awaiting a human decision
    (E-17). Built activity-side from the CLI's `deferred_tool_use` payload;
    travels inline on HarnessRunResult — bounded, like ToolDenial."""

    tool_use_id: str  # the CLI replays THIS id on resume
    tool: str
    input_digest: str  # canonical digest of tool_input
    rule_id: str
    reason: str
    target: str | None = None  # scrubbed path/command, for the human


class ToolGrant(BaseModel):
    """One human decision about one suspended call. Single-use falls out of
    tool_use_id: the replayed call reuses it, a genuinely new call gets a
    fresh one and matches nothing."""

    tool_use_id: str
    tool: str
    input_digest: str
    rule_id: str
    approved: bool  # False = rejected / timed out / capped
    reason: str = ""  # reaches the model verbatim


class EscalationOutcome(StrEnum):
    """How an escalation ended. BATCHED and CAPPED never reached a human."""

    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CAPPED = "capped"
    BATCHED = "batched"


class ToolEscalation(BaseModel):
    """The workflow's record of one escalation, for events.jsonl + E-36."""

    tool: str
    rule_id: str
    target: str | None = None
    outcome: EscalationOutcome
    decided_by: str = ""  # "" when nobody was asked
    round: int = 0  # the (gate, round) identity; 0 = no gate


class HarnessRunResult(BaseModel):
    """Normalized result from any coding harness invocation."""

    harness: HarnessKind
    session_id: str | None = None
    exit_code: int
    summary: str  # harness's final text (truncated)
    cost_usd: float | None = None
    commit_sha: str | None = None  # checkpoint commit after the run
    diff_ref: ArtifactRef | None = None
    # Observability for the context-ceiling trigger (Finding #7):
    input_tokens: int | None = None
    output_tokens: int | None = None
    context_window: int | None = None
    compacted: bool = False  # harness signalled a mid-run compaction
    # E-38 (ADR-16): full scrubbed transcript as a claim-checked ref; waste
    # digest inline. The raw stdout rides a PrivateAttr so it can never
    # serialize into workflow state.
    session_ref: ArtifactRef | None = None
    session_digest: SessionDigest | None = None
    # E-15/E-16: containment outcome. Bounded and inline — the workflow and
    # the E-36 heatmap read these without loading the session artifact.
    denials: list[ToolDenial] = Field(default_factory=list)
    deferred: DeferredToolUse | None = None  # E-17: suspended tool call
    escalations: list[ToolEscalation] = Field(default_factory=list)
    containment: ContainmentReport | None = None
    _raw_stdout: str = PrivateAttr(default="")

    def near_context_ceiling(self, fraction: float = 0.75) -> bool:
        """True when the run is at/over the usable context budget. A
        harness-signalled compaction always counts; otherwise compare
        input tokens to a fraction of the window. Unknown token data is
        treated as 'not at ceiling' so callers fall back to the resume
        counter rather than mis-triggering."""
        if self.compacted:
            return True
        if self.input_tokens is None or not self.context_window:
            return False
        return self.input_tokens > fraction * self.context_window
