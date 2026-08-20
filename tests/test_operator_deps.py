"""OperatorDeps carries collaborators and enforces the follow-call brake."""
import pytest

from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError


def deps(**kw):
    return OperatorDeps(poller=object(), board=object(), starter=object(), **kw)


def test_defaults_match_the_spec():
    d = deps()
    assert d.max_artifact_bytes == 32 * 1024
    assert d.max_follow_calls == 10
    assert d.actor.startswith("chat:")


def test_follow_calls_accumulate():
    d = deps()
    d.note_follow()
    d.note_follow()
    assert d.follow_calls == 2


def test_refuses_past_the_cap_with_actionable_text():
    d = deps(max_follow_calls=2)
    d.note_follow()
    d.note_follow()
    with pytest.raises(ToolError) as e:
        d.note_follow()
    assert "report to the operator" in e.value.message


def test_any_other_tool_resets_the_streak():
    d = deps(max_follow_calls=2)
    d.note_follow()
    d.note_other_tool()
    d.note_follow()
    d.note_follow()          # streak restarted, so this is still allowed
    assert d.follow_calls == 2


def test_reset_request_state_clears_the_counter():
    d = deps()
    d.note_follow()
    d.reset_request_state()
    assert d.follow_calls == 0
