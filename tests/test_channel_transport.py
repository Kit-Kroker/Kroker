from __future__ import annotations

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
