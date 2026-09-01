"""Per-dimension coverage is E-85's primary metric (spec §10), and
ClarificationOutcome is built from the EVENT TRACE, not the artifact -- so the
dimension has to ride on the event or it never reaches the rollup.

RunEvent.data is a flat dict[str, str] ("events.jsonl stays a stable,
greppable line format"), so the dimension travels as its code and an absent
one is the empty string, never None."""

from datetime import UTC, datetime

from sdlc.models import ClarificationDimension as CD
from sdlc.observability.summary import build_run_summary
from sdlc.observability.trace import RunEvent, RunEventKind

AT = datetime(2026, 8, 20, tzinfo=UTC)


def _ev(seq, kind, **data):
    return RunEvent(seq=seq, at=AT, kind=kind, stage="clarify", data=data)


def _summary(*events):
    return build_run_summary(
        run_id="r",
        mode="brownfield",
        outcome="deployed",
        trace=list(events),
        memory_enabled=False,
        memory_watermark=None,
    )


def test_the_dimension_survives_into_the_summary():
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?", dimension="C4"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="human"),
    )
    assert s.clarifications[0].dimension is CD.INTERFACE_SPEC


def test_a_pre_e85_event_without_a_dimension_still_summarises():
    # Events written before E-85 carry no `dimension` key at all.
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?"),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="human"),
    )
    assert s.clarifications[0].dimension is None
    assert s.clarifications[0].answered_by == "human"


def test_an_empty_dimension_string_reads_as_no_dimension():
    # The flag-off path emits "" rather than None, because data is str->str.
    s = _summary(
        _ev(0, RunEventKind.CLARIFICATION_ASKED, question_id="Q1", question="q?", dimension=""),
        _ev(1, RunEventKind.CLARIFICATION_ANSWERED, question_id="Q1", answered_by="suggested"),
    )
    assert s.clarifications[0].dimension is None
