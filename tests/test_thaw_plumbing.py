"""C2 Task 7: the human-only, single-attempt thaw."""

from __future__ import annotations

import pytest

from sdlc.channels.contract import Reply, default_translate
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.pending import TaskEscalationPending
from sdlc.stages.code.step import _is_repair_attempt


def _pending() -> TaskEscalationPending:
    return TaskEscalationPending(
        key="task:t1", gate="task:t1", round=1, task_id="t1", analysis="", attempts=1
    )


def test_thaw_defaults_off_everywhere():
    assert Reply(outcome=GateOutcome.REVISE, text="x").thaw_tests is False
    assert (
        GateDecision(gate="g", outcome=GateOutcome.REVISE, decided_by="human").thaw_tests is False
    )


def test_translate_carries_the_thaw_into_the_decision():
    call = default_translate(
        _pending(),
        Reply(outcome=GateOutcome.REVISE, text="the assertion is wrong", thaw_tests=True),
    )
    assert call.decision.thaw_tests is True
    assert call.decision.guidance == "the assertion is wrong"


def test_translate_defaults_the_thaw_off():
    call = default_translate(_pending(), Reply(outcome=GateOutcome.REVISE, text="try again"))
    assert call.decision.thaw_tests is False


def test_guidance_text_naming_a_test_file_does_not_imply_a_thaw():
    """NO-INFERENCE REGRESSION. Guards the explicitness rule against a future
    'helpful' inference, and against a session that writes gate-facing prose
    designed to induce one."""
    call = default_translate(
        _pending(),
        Reply(
            outcome=GateOutcome.REVISE,
            text="the assertion in tests/test_auth.py is wrong, please fix the test",
        ),
    )
    assert call.decision.thaw_tests is False


def test_a_thawed_attempt_is_not_a_repair_attempt():
    assert _is_repair_attempt(3, thawed=True) is False
    assert _is_repair_attempt(3, thawed=False) is True


def test_cli_revise_accepts_thaw_and_other_verbs_do_not():
    import argparse

    from sdlc.cli import add_decision_parsers

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    add_decision_parsers(sub)
    args = p.parse_args(["revise", "--id", "r1", "--comment", "c", "--thaw-tests"])
    assert args.thaw_tests is True
    with pytest.raises(SystemExit):
        p.parse_args(["approve", "--id", "r1", "--thaw-tests"])


def test_cli_selector_forwards_the_thaw():
    import argparse

    from sdlc.cli import add_decision_parsers, selector_for

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    add_decision_parsers(sub)
    _, reply = selector_for(
        p.parse_args(["revise", "--id", "r1", "--comment", "c", "--thaw-tests"])
    )
    assert reply.thaw_tests is True


def test_dashboard_decide_body_carries_the_thaw():
    from sdlc.dashboard.api import DecideBody

    assert DecideBody(key="k", outcome=GateOutcome.REVISE).thaw_tests is False
    assert DecideBody(key="k", outcome=GateOutcome.REVISE, thaw_tests=True).thaw_tests is True


def test_mcp_operator_surface_does_not_expose_the_thaw():
    """DELIBERATE. decide_gate is an AGENT tool surface; exposing the thaw
    there would let an LLM intermediary unfreeze the tests. This assertion
    exists so nobody 'completes' the plumbing later without reading why."""
    import inspect

    from sdlc.operator import tools

    assert "thaw" not in inspect.getsource(tools.decide_gate)
