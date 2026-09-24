"""E-74 §4.3: RunHost carries what FeatureWorkflow and GraphWorkflow share."""

from __future__ import annotations

from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost
from sdlc.workflows.run_host import RunHost

_MOVED = ("_on_gate_awaited", "_on_gate_decided", "_on_notified", "_retro", "_snapshot_run_state")


def test_feature_workflow_composes_run_host_before_gate_host():
    mro = FeatureWorkflow.__mro__
    assert mro.index(RunHost) < mro.index(GateHost)


def test_moved_members_resolve_to_run_host():
    for name in _MOVED:
        assert getattr(FeatureWorkflow, name) is getattr(RunHost, name), name
        assert name not in vars(FeatureWorkflow), name


def test_run_host_declares_no_workflow_handlers():
    # workflows/AGENTS.md rule 4: handlers live on the concrete class or GateHost.
    for name, member in vars(RunHost).items():
        assert not hasattr(member, "__temporal_query_definition"), name
        assert not hasattr(member, "__temporal_signal_definition"), name


def test_run_state_query_delegates_to_the_snapshot():
    wf = FeatureWorkflow()
    assert wf.run_state() is None  # no brief stashed yet
    assert wf._run_id == "" and wf._run_summary is None


def test_snapshot_run_state_carries_the_cfg_project_key():
    """002 R-1: the fleet snapshot's project_key comes from the config the
    host already holds (`self._cfg.project_key if self._cfg else None`) --
    a host queried before setup snapshots None, never a fabricated key."""
    from datetime import UTC, datetime

    from sdlc.core.models import IdeaBrief, PipelineConfig, ProjectMode

    wf = FeatureWorkflow()
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
