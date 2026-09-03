# tests/test_crew_models.py
"""E-88 §2: round files are UNTRUSTED input produced by a model inside a
worktree. An unknown schema is a hard error, not best-effort parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.crew.models import (
    MAX_NOTE_BYTES,
    NOTE_SCHEMA,
    CrewRunResult,
    RoundNote,
    RoundRecord,
    TurnBeat,
    TurnRecord,
)
from sdlc.models import (
    HarnessRunResult,
)


def _note(**kw):
    base = dict(
        schema=NOTE_SCHEMA,
        what_changed="added greet()",
        why="the brief asked for it",
        verification="ran pytest",
    )
    base.update(kw)
    return RoundNote(**base)


def test_note_parses_the_shipped_shape():
    n = _note()
    assert n.schema_name == NOTE_SCHEMA
    assert n.left_undone == ""


def test_note_rejects_an_unknown_schema():
    with pytest.raises(ValidationError):
        _note(schema="notes-v2")


def test_note_rejects_an_oversized_body():
    with pytest.raises(ValidationError):
        _note(what_changed="x" * (MAX_NOTE_BYTES + 1))


def test_turn_record_marks_a_lost_cost_rather_than_zeroing_it():
    """spec §3: a missing record is recorded, never a silent understatement."""
    t = TurnRecord(
        role="coder",
        round=1,
        attempt=2,
        harness=HarnessKind.OPENCODE,
        model="glm-5.3",
        session_id=None,
        cost_usd=None,
        exit_code=None,
        cost_incomplete=True,
    )
    assert t.cost_incomplete is True
    assert t.cost_usd is None


def test_round_cost_sums_every_attempt_including_abandoned_ones():
    """spec §3/§4: restarted rounds count in FULL. Hiding an aborted
    attempt's cost understates spend exactly where things break."""
    r = RoundRecord(
        round=1,
        turns=[
            TurnRecord(
                role="coder",
                round=1,
                attempt=1,
                harness=HarnessKind.OPENCODE,
                model="glm-5.3",
                cost_usd=0.40,
            ),
            TurnRecord(
                role="coder",
                round=1,
                attempt=2,
                harness=HarnessKind.OPENCODE,
                model="glm-5.3",
                cost_usd=0.25,
            ),
        ],
    )
    assert r.cost_usd() == pytest.approx(0.65)


def test_round_cost_is_none_when_any_attempt_is_incomplete():
    r = RoundRecord(
        round=1,
        turns=[
            TurnRecord(
                role="coder",
                round=1,
                attempt=1,
                harness=HarnessKind.OPENCODE,
                model="glm-5.3",
                cost_usd=0.40,
            ),
            TurnRecord(
                role="coder",
                round=1,
                attempt=2,
                harness=HarnessKind.OPENCODE,
                model="glm-5.3",
                cost_incomplete=True,
            ),
        ],
    )
    assert r.cost_usd() is None


def test_crew_result_carries_the_lead_session_on_the_shared_contract():
    """spec §1: run.session_id is the LEAD's, so the token fields and the
    session id describe one context window rather than a meaningless sum."""
    run = HarnessRunResult(
        harness=HarnessKind.OPENCODE, exit_code=0, summary="done", session_id="s-lead"
    )
    res = CrewRunResult(run=run, sessions={"coder": "s-lead"})
    assert res.run.session_id == "s-lead"
    assert res.rounds == []


def test_turn_beat_round_trips_as_a_plain_dict():
    """Heartbeat details cross the Temporal boundary as JSON."""
    b = TurnBeat(session_id="s1", round=2, phase="streaming", cost_usd=0.1)
    assert TurnBeat(**b.model_dump()) == b
