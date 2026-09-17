# tests/graph_workflow/test_host_attribution.py
"""E-75 spec §4.3: hosts attribute spend and pendings to the running activation.

Memory-only and FeatureWorkflow-neutral: with ACTIVATION unset nothing is
attributed. `workflow.now` is patched because _emit stamps events with it.
"""

from __future__ import annotations

import contextvars
from datetime import UTC, datetime

import pytest
from temporalio import workflow

from sdlc.graph import ACTIVATION, PendingFact
from sdlc.pending import ClarifyPending, StageGatePending, TaskEscalationPending
from sdlc.workflows.gates import GateHost
from sdlc.workflows.report_host import ReportHost

AT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


class _Host(ReportHost, GateHost):
    pass


@pytest.fixture(autouse=True)
def _now(monkeypatch):
    monkeypatch.setattr(workflow, "now", lambda: AT)


def _in(aid: str | None, fn):
    def run():
        if aid is not None:
            ACTIVATION.set(aid)
        fn()

    contextvars.copy_context().run(run)


def test_spend_folds_into_the_running_activation_and_totals_reconcile():
    h = _Host()
    _in("a#1", lambda: h._track_usage(role="architect", model="m", cost_usd=1.0))
    _in("a#1", lambda: h._track_usage(role="architect", model="m", cost_usd=0.5))
    _in("b#1", lambda: h._track_usage(role="planner", model="m", cost_usd=None))
    _in("b#1", lambda: h._track_usage(role="planner", model="m", cost_usd=2.0))
    _in(None, lambda: h._track_usage(role="retro", model="m", cost_usd=0.25))
    assert h._activation_spend == {"a#1": (1.5, True), "b#1": (2.0, False)}
    assert h._unattributed_spend == (0.25, True)
    total = sum(u.cost_usd for u in h._role_usage.values() if u.cost_usd is not None)
    attributed = sum(cost for cost, _ in h._activation_spend.values())
    assert attributed + h._unattributed_spend[0] == pytest.approx(total)  # spec §4.3 invariant


def test_nothing_is_attributed_without_an_activation():
    h = _Host()
    h._track_usage(role="architect", model="m", cost_usd=1.0)
    assert h._activation_spend == {}


def test_pending_facts_iterate_pending_and_join_attribution():
    h = _Host()
    h._pending["architecture#1"] = StageGatePending(
        key="architecture#1", gate="architecture", round=1, spec_summary="s"
    )
    h._pending["Q1"] = ClarifyPending(key="Q1", question="q", why_it_matters="w")
    h._pending["task:t1#1"] = TaskEscalationPending(
        key="task:t1#1", gate="task:t1", round=1, task_id="t1", analysis="a", attempts=2
    )
    h._pending_activation.update({"architecture#1": "architecture#1", "Q1": "clarify#1"})
    h._pending_activation["stale#1"] = "gone#1"  # no longer pending: must not surface
    assert h._pending_facts() == (
        PendingFact(key="Q1", activation_id="clarify#1", kind="clarify"),
        PendingFact(key="architecture#1", activation_id="architecture#1", kind="gate"),
        PendingFact(key="task:t1#1", activation_id=None, kind="escalation"),
    )
