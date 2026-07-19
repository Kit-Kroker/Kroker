from __future__ import annotations

import pathlib

from sdlc.pending import StageGatePending
from sdlc.workflows.feature import FeatureWorkflow

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_new_workflow_has_empty_pending_registry():
    wf = FeatureWorkflow()
    assert wf.pending_decisions() == []


def test_pending_decisions_query_returns_registry_values():
    wf = FeatureWorkflow()
    p = StageGatePending(key="architecture#1", gate="architecture", round=1,
                         spec_summary="x")
    wf._pending[p.key] = p
    assert wf.pending_decisions() == [p]


def test_gate_accepts_context_param():
    import inspect
    sig = inspect.signature(FeatureWorkflow._gate)
    assert "context" in sig.parameters


def test_feature_source_wires_pending_population():
    src = SRC.read_text(encoding="utf-8")
    # the query exists and is registered
    assert "def pending_decisions(" in src
    # clarify wait and gate wait both populate the registry
    assert "clarify_pending(" in src
    assert "gate_pending(" in src
    assert "self._pending" in src
    # gate population is cleared on resolution
    assert "self._pending.pop(" in src


import datetime as dt

from sdlc.models import GateDecision, GateOutcome
from sdlc.pending import ClarifyPending


def test_answer_question_pops_only_that_question():
    wf = FeatureWorkflow()
    for qid in ("Q1", "Q2"):
        wf._pending[qid] = ClarifyPending(
            key=qid, question=f"{qid}?", why_it_matters="w")

    wf.answer_question("Q1", "Use OIDC")

    assert [d.key for d in wf.pending_decisions()] == ["Q2"]
    assert wf._question_answers == {"Q1": "Use OIDC"}


def test_answer_question_is_still_first_answer_wins():
    wf = FeatureWorkflow()
    wf._pending["Q1"] = ClarifyPending(key="Q1", question="q", why_it_matters="w")

    wf.answer_question("Q1", "first")
    wf.answer_question("Q1", "second")

    assert wf._question_answers["Q1"] == "first"
    assert wf.pending_decisions() == []


def test_submit_gate_decision_pops_that_gate(monkeypatch):
    from sdlc.workflows import feature as feat
    monkeypatch.setattr(
        feat.workflow, "now",
        lambda: dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))

    wf = FeatureWorkflow()
    wf._pending["architecture#2"] = StageGatePending(
        key="architecture#2", gate="architecture", round=2, spec_summary="s")

    wf.submit_gate_decision(GateDecision(
        gate="architecture", round=2, outcome=GateOutcome.APPROVE,
        decided_by="human"))

    assert wf.pending_decisions() == []
    assert wf._gate_decisions["architecture#2"].outcome is GateOutcome.APPROVE
