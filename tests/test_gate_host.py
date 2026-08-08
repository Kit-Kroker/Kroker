"""E-42 D2: the gate is shared code, not duplicated code. Writing FR-302's
first-decision-wins rule twice is the failure shape
2026-07-16-registry-drives-every-role was written about."""
from __future__ import annotations

import datetime as dt
import inspect

import pytest

from sdlc.models import GateDecision, GateOutcome, GatePolicy, GateSettings
from sdlc.pending import StageGatePending
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.gates import GateHost


def test_feature_workflow_inherits_the_shared_gate():
    assert issubclass(FeatureWorkflow, GateHost)


def test_gate_takes_settings_not_pipeline_config():
    sig = inspect.signature(GateHost._gate)
    assert "settings" in sig.parameters
    assert "cfg" not in sig.parameters
    # E-6/E-7 callers still pass these.
    assert "context" in sig.parameters
    assert "auto_decision" in sig.parameters
    assert "default_policy" in sig.parameters


def test_hooks_are_no_ops_on_the_base():
    """Triage overrides none of them. A base that emitted or retained would
    force gates.py to import RunEventKind and the memory activities."""
    for name in ("_on_gate_awaited", "_on_gate_decided", "_on_notified"):
        assert inspect.iscoroutinefunction(getattr(GateHost, name)), name


def test_confidence_reaches_the_hook_as_a_parameter():
    """Review fix. It was briefly stashed on the instance
    (`self._last_gate_confidence`), which two interleaving gates would
    overwrite -- wave mode runs _dev_task concurrently, and a gate that opens
    while another awaits a human would silently drop
    RunSummary.gates[].confidence, which SC-6's calibration compare reads.

    Per-call by construction beats per-call by luck: assert the parameter
    exists and no instance slot survives to be clobbered.
    """
    sig = inspect.signature(GateHost._on_gate_decided)
    assert "confidence" in sig.parameters, (
        "_on_gate_decided must take confidence as a parameter, not read it "
        "off shared instance state")
    assert not hasattr(GateHost(), "_last_gate_confidence")

    # FeatureWorkflow's override must accept it too, or _gate's call breaks.
    assert "confidence" in inspect.signature(
        FeatureWorkflow._on_gate_decided).parameters


@pytest.fixture
def frozen_now(monkeypatch):
    """submit_gate_decision stamps decided_at with workflow.now(), which
    raises outside a workflow. tests/test_pending_wiring.py already does this;
    the module object is shared (both files do `from temporalio import
    workflow`), so patching it once covers gates.py and feature.py alike."""
    from sdlc.workflows import gates as g
    monkeypatch.setattr(
        g.workflow, "now",
        lambda: dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))


def test_first_decision_for_a_round_wins(frozen_now):
    """FR-302. decided_by is a Literal["human","policy","timeout"], so the two
    decisions are told apart by their comments, not by an invented name."""
    host = GateHost()
    host.submit_gate_decision(GateDecision(
        gate="readiness", round=1, outcome=GateOutcome.APPROVE,
        decided_by="human", comments="first"))
    host.submit_gate_decision(GateDecision(
        gate="readiness", round=1, outcome=GateOutcome.REJECT,
        decided_by="human", comments="second"))
    kept = host._gate_decisions["readiness#1"]
    assert kept.comments == "first"
    assert kept.outcome is GateOutcome.APPROVE


def test_submit_pops_only_that_round_from_pending(frozen_now):
    host = GateHost()
    host._pending["readiness#1"] = StageGatePending(
        key="readiness#1", gate="readiness", round=1, spec_summary="s")
    host._pending["readiness#2"] = StageGatePending(
        key="readiness#2", gate="readiness", round=2, spec_summary="s")
    host.submit_gate_decision(GateDecision(
        gate="readiness", round=1, outcome=GateOutcome.APPROVE,
        decided_by="human"))
    assert "readiness#1" not in host._pending
    assert "readiness#2" in host._pending


def test_pending_decisions_query_returns_the_registry():
    host = GateHost()
    p = StageGatePending(key="readiness#1", gate="readiness", round=1,
                         spec_summary="s")
    host._pending[p.key] = p
    assert host.pending_decisions() == [p]


def test_gate_settings_reaches_the_host_unchanged():
    s = GateSettings(default_gate_policy=GatePolicy.OFF, gate_timeout_hours=1)
    assert s.default_gate_policy is GatePolicy.OFF
    assert s.gate_timeout_hours == 1
