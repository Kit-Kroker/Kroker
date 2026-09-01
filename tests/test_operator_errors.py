"""Domain exceptions become typed, actionable, traceback-free ToolErrors."""

import pytest

from sdlc.board.store import ConflictError, InvalidTransition, NotFoundError
from sdlc.channels.transport import Ambiguous, NoMatch
from sdlc.operator.errors import ToolError, guard, translate


def test_nomatch_tells_the_model_to_re_read():
    err = translate(NoMatch("no pending item with key 'Q9' on this run"))
    assert isinstance(err, ToolError)
    assert "Q9" in err.message
    assert "re-read" in err.message.lower()


def test_ambiguous_is_reported_as_needing_narrowing():
    err = translate(Ambiguous("ambiguous -- 2 gates pending:\n  a\n  b"))
    assert "narrow" in err.message.lower()


def test_board_not_found_keeps_the_stores_own_message():
    err = translate(NotFoundError("no project 'kroker'"))
    assert "no project 'kroker'" in err.message


def test_conflict_and_invalid_transition_are_distinguishable():
    assert "conflict" in translate(ConflictError("row_version")).message.lower()
    assert "transition" in translate(InvalidTransition("PENDING -> DONE")).message.lower()


def test_unknown_exception_leaks_no_detail():
    err = translate(RuntimeError("D:\\own\\Kroker\\secret\\path.py exploded"))
    assert "secret" not in err.message
    assert "RuntimeError" in err.message


def test_hint_is_appended_when_given():
    err = translate(NotFoundError("no project 'x'"), hint="call list_projects")
    assert "call list_projects" in err.message


@pytest.mark.asyncio
async def test_guard_converts_a_raised_domain_error():
    @guard
    async def boom():
        raise NotFoundError("no project 'x'")

    with pytest.raises(ToolError) as e:
        await boom()
    assert "no project 'x'" in e.value.message


@pytest.mark.asyncio
async def test_guard_passes_tool_errors_through_unchanged():
    @guard
    async def boom():
        raise ToolError("already typed")

    with pytest.raises(ToolError) as e:
        await boom()
    assert e.value.message == "already typed"
