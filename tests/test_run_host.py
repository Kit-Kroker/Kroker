"""E-74 §4.3: RunHost carries what the pipeline workflows share (020: GraphWorkflow)."""

from __future__ import annotations

from sdlc.workflows.gates import GateHost
from sdlc.workflows.graph import GraphWorkflow
from sdlc.workflows.run_host import RunHost

_MOVED = ("_on_gate_awaited", "_on_gate_decided", "_on_notified", "_retro", "_snapshot_run_state")


def test_feature_workflow_composes_run_host_before_gate_host():
    mro = GraphWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_moved_members_resolve_to_run_host():
    for name in _MOVED:
        assert getattr(GraphWorkflow, name) is getattr(RunHost, name), name
        assert name not in vars(GraphWorkflow), name


def test_run_host_declares_no_workflow_handlers():
    # workflows/AGENTS.md rule 4: handlers live on the concrete class or GateHost.
    for name, member in vars(RunHost).items():
        assert not hasattr(member, "__temporal_query_definition"), name
        assert not hasattr(member, "__temporal_signal_definition"), name


def test_run_state_query_delegates_to_the_snapshot():
    wf = GraphWorkflow()
    assert wf.run_state() is None  # no brief stashed yet
    assert wf._run_id == "" and wf._run_summary is None


def test_snapshot_run_state_carries_the_cfg_project_key():
    """002 R-1: the fleet snapshot's project_key comes from the config the
    host already holds (`self._cfg.project_key if self._cfg else None`) --
    a host queried before setup snapshots None, never a fabricated key."""
    from datetime import UTC, datetime

    from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode

    wf = GraphWorkflow()
    # Minimal live-run state: the snapshot returns None until the brief and
    # a start time are stashed; everything else it reads (_status, _trace,
    # _role_usage, _gate_decisions, _budget_crossings) is mixin state a
    # bare instance already initializes.
    wf._idea = IdeaBrief(title="t", description="d", mode=ProjectMode.GREENFIELD)
    wf._started_at = datetime(2026, 9, 24, tzinfo=UTC)
    wf._run_id = "r"
    wf._cfg = PipelineConfig(project_key="kroker")

    snap = wf._snapshot_run_state()
    assert snap is not None
    assert snap.project_key == "kroker"

    wf._cfg = None
    assert wf._snapshot_run_state().project_key is None


# --- FR-304 (RED): GATE_DECIDED carries the full decision record ---------------


def _drive_on_gate_decided(decision, policy, confidence=None):
    """Drive _on_gate_decided on a bare GraphWorkflow, capturing the kwargs
    it hands _emit. _cfg None keeps the method off _retain/workflow.info, so
    no Temporal context is needed."""
    import asyncio

    from sdlc.core.models import GatePolicy

    wf = GraphWorkflow()
    wf._cfg = None
    emitted: list[dict] = []
    wf._emit = lambda kind, stage=None, **data: emitted.append(  # type: ignore[method-assign]
        {"kind": kind, "stage": stage, **data}
    )
    gate = decision.gate
    rnd = decision.round
    asyncio.run(wf._on_gate_decided(gate, rnd, policy or GatePolicy.HARD, decision, confidence))
    return emitted


def test_on_gate_decided_emits_full_field_set():
    from datetime import UTC, datetime

    from sdlc.core.models import GateDecision, GateOutcome, GatePolicy

    (data,) = _drive_on_gate_decided(
        GateDecision(
            gate="merge",
            round=1,
            outcome=GateOutcome.REJECT,
            decided_by="human",
            reviewer="maksim",
            comments="not ready",
            decided_at=datetime(2026, 11, 15, 9, 0, tzinfo=UTC),
        ),
        GatePolicy.HARD,
    )
    assert data["outcome"] == "reject"
    assert data["reviewer"] == "maksim"
    assert data["comments"] == "not ready"
    assert data["decided_at"] == "2026-11-15T09:00:00+00:00"


def test_on_gate_decided_emits_absent_optionals_only_when_set():
    """A decision with no reviewer/comments (e.g. a SOFT auto-approve; the
    timeout path does carry a comments string) emits neither key, while
    decided_at — stamped by GateHost._gate for every path — is always set."""
    from datetime import UTC, datetime

    from sdlc.core.models import GateDecision, GateOutcome, GatePolicy

    (data,) = _drive_on_gate_decided(
        GateDecision(
            gate="architecture",
            round=1,
            outcome=GateOutcome.APPROVE,
            decided_by="policy",
            decided_at=datetime(2026, 11, 15, 9, 5, tzinfo=UTC),
        ),
        GatePolicy.SOFT,
        confidence=0.92,
    )
    assert "reviewer" not in data
    assert "comments" not in data
    assert data["decided_at"] == "2026-11-15T09:05:00+00:00"
