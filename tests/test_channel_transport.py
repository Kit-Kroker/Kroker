from __future__ import annotations

import argparse

import pytest

from sdlc.channels.transport import (
    Ambiguous, NoMatch, Selector, describe, match,
)
from sdlc.pending import (
    ClarifyPending, MergeGatePending, StageGatePending, TaskEscalationPending,
)

ARCH = StageGatePending(key="architecture#2", gate="architecture", round=2,
                        spec_summary="s")
MERGE = MergeGatePending(key="merge#1", gate="merge", round=1)
Q1 = ClarifyPending(key="Q1", question="OIDC or SAML?", why_it_matters="auth")
Q2 = ClarifyPending(key="Q2", question="Which DB?", why_it_matters="storage")
TASK = TaskEscalationPending(key="task:T1#1", gate="task:T1", round=1,
                             task_id="T1", analysis="flaky", attempts=3)


def test_match_single_gate_without_name():
    got = match([ARCH, Q1], Selector(reply_kind="gate"))
    assert got is ARCH


def test_match_carries_the_pending_round_not_a_default():
    got = match([ARCH], Selector(reply_kind="gate", name="architecture"))
    assert got.round == 2


def test_match_filters_by_reply_kind():
    got = match([ARCH, Q1], Selector(reply_kind="text"))
    assert got is Q1


def test_match_by_gate_name():
    got = match([ARCH, MERGE], Selector(reply_kind="gate", name="merge"))
    assert got is MERGE


def test_match_by_question_id():
    got = match([Q1, Q2], Selector(reply_kind="text", name="Q2"))
    assert got is Q2


def test_match_task_escalation_by_prefixed_gate_name():
    got = match([ARCH, TASK], Selector(reply_kind="gate", name="task:T1"))
    assert got is TASK


def test_ambiguous_lists_only_same_kind_candidates():
    with pytest.raises(Ambiguous) as e:
        match([ARCH, MERGE, Q1], Selector(reply_kind="gate"))
    assert e.value.candidates == [ARCH, MERGE]
    assert "architecture (round 2)" in e.value.message
    assert "merge (round 1)" in e.value.message
    assert "OIDC" not in e.value.message


def test_no_match_on_unknown_name_lists_what_is_pending():
    with pytest.raises(NoMatch) as e:
        match([ARCH], Selector(reply_kind="gate", name="planning"))
    assert "planning" in e.value.message
    assert "architecture (round 2)" in e.value.message


def test_no_match_on_empty_pending():
    with pytest.raises(NoMatch) as e:
        match([], Selector(reply_kind="gate"))
    assert e.value.candidates == []


def test_messages_are_ascii():
    with pytest.raises(Ambiguous) as e:
        match([ARCH, MERGE], Selector(reply_kind="gate"))
    e.value.message.encode("ascii")   # raises UnicodeEncodeError if not


def test_describe_gate_and_clarify():
    assert describe(ARCH) == "architecture (round 2)"
    assert describe(Q1) == "Q1: OIDC or SAML?"


from sdlc.channels.contract import Reply
from sdlc.channels.transport import SubmitResult, resolve, submit
from sdlc.models import GateOutcome


class StubHandle:
    """Records signals; returns scripted query results, one per call.

    Results are raw JSON-shaped dicts, matching what a by-name query returns
    through pydantic_data_converter before validation.
    """

    def __init__(self, id: str, responses):
        self.id = id
        self._responses = list(responses)
        self.signals = []

    async def query(self, name, *a, **kw):
        assert name == "pending_decisions"
        return self._responses.pop(0)

    async def signal(self, name, arg=None, *, args=()):
        self.signals.append((name, arg, list(args)))


def _raw(*items):
    return [i.model_dump(mode="json") for i in items]


@pytest.mark.asyncio
async def test_resolve_validates_the_discriminated_union():
    h = StubHandle("run-1", [_raw(ARCH, Q1)])
    got = await resolve(h, Selector(reply_kind="gate"))
    assert isinstance(got, StageGatePending)
    assert got.gate == "architecture" and got.round == 2


@pytest.mark.asyncio
async def test_submit_gate_sends_decision_with_the_pending_round():
    h = StubHandle("run-1", [_raw()])          # nothing left pending
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE, text="lgtm"))

    name, arg, _ = h.signals[0]
    assert name == "submit_gate_decision"
    assert arg.gate == "architecture" and arg.round == 2
    assert arg.outcome is GateOutcome.APPROVE and arg.comments == "lgtm"
    assert res.confirmed is True
    assert res.message == "approved gate 'architecture' (round 2) on run-1"


@pytest.mark.asyncio
async def test_submit_clarify_sends_answer_question_positionally():
    h = StubHandle("run-1", [_raw()])
    res = await submit(h, Q1, Reply(text="Use OIDC"))

    name, arg, args = h.signals[0]
    assert name == "answer_question"
    assert arg is None and args == ["Q1", "Use OIDC"]
    assert res.message == "answered Q1 on run-1"


@pytest.mark.asyncio
async def test_submit_revise_reports_revision_requested():
    h = StubHandle("run-1", [_raw()])
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.REVISE, text="split it"))

    _, arg, _ = h.signals[0]
    assert arg.outcome is GateOutcome.REVISE and arg.guidance == "split it"
    assert res.confirmed is True
    assert "revision requested on" in res.message


@pytest.mark.asyncio
async def test_submit_not_confirmed_when_item_survives_the_requery():
    h = StubHandle("run-1", [_raw(ARCH)])      # still pending afterwards
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE))

    assert res.confirmed is False
    assert res.message.startswith("not confirmed:")
    assert "decided it first" in res.message
    assert "failed" not in res.message         # never claims failure
    res.message.encode("ascii")


@pytest.mark.asyncio
async def test_submit_confirms_when_a_different_item_remains():
    h = StubHandle("run-1", [_raw(Q1)])        # unrelated item still pending
    res = await submit(h, ARCH, Reply(outcome=GateOutcome.APPROVE))
    assert res.confirmed is True


import sdlc.cli


def _parse(argv):
    """Build the CLI parser the same way main() does, and parse argv."""
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sdlc.cli.add_decision_parsers(sub)
    return p.parse_args(argv)


def test_gate_verbs_no_longer_accept_round():
    with pytest.raises(SystemExit):
        _parse(["approve", "--id", "X", "--round", "2"])


def test_gate_selector_is_optional():
    args = _parse(["approve", "--id", "X"])
    assert args.cmd == "approve" and args.gate is None


def test_revise_verb_exists_and_takes_comment():
    args = _parse(["revise", "--id", "X", "--comment", "split it"])
    assert args.cmd == "revise" and args.comment == "split it"


def test_answer_question_id_is_optional_but_text_required():
    args = _parse(["answer", "--id", "X", "--text", "yes"])
    assert args.q is None and args.text == "yes"
    with pytest.raises(SystemExit):
        _parse(["answer", "--id", "X"])


def test_selector_for_builds_gate_and_text_selectors():
    a = _parse(["approve", "--id", "X", "--gate", "merge"])
    sel, reply = sdlc.cli.selector_for(a)
    assert sel.reply_kind == "gate" and sel.name == "merge"
    assert reply.outcome is GateOutcome.APPROVE

    a = _parse(["answer", "--id", "X", "--q", "Q1", "--text", "yes"])
    sel, reply = sdlc.cli.selector_for(a)
    assert sel.reply_kind == "text" and sel.name == "Q1"
    assert reply.text == "yes"


def test_revise_reply_carries_comment_as_text():
    a = _parse(["revise", "--id", "X", "--comment", "split it"])
    _, reply = sdlc.cli.selector_for(a)
    assert reply.outcome is GateOutcome.REVISE and reply.text == "split it"


def test_inbox_verb_takes_no_arguments():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inbox")
    args = p.parse_args(["inbox"])
    assert args.cmd == "inbox"
