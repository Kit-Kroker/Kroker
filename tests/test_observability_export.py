from datetime import UTC, datetime

from sdlc.core.models import (
    ClarificationOutcome,
    GateOutcomeSummary,
    RoleUsage,
    RunSummary,
    StageOutcome,
)
from sdlc.observability.export import render_events_jsonl, render_report_html
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def _summary():
    return RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:http://pr",
        terminal_stage="deploy",
        started_at=T0,
        ended_at=T0,
        duration_s=0.0,
        stages=[
            StageOutcome(
                stage="clarify", role="clarify", outcome="pass", duration_s=2.0, cost_usd=0.1
            )
        ],
        clarifications=[
            ClarificationOutcome(question_id="q1", question="scope?", answered_by="human")
        ],
        gates=[
            GateOutcomeSummary(
                gate="merge",
                round=1,
                policy="soft",
                decided_by="human",
                approved=True,
                overrides=["coverage"],
            )
        ],
        cost_usd_total=0.1,
        memory_enabled=True,
        memory_watermark="3",
        memory_retains=2,
    )


def test_events_jsonl_is_one_line_per_event_seq_ordered():
    trace = [
        RunEvent(seq=1, at=T0, kind=RunEventKind.STAGE_ENDED, stage="clarify"),
        RunEvent(seq=0, at=T0, kind=RunEventKind.STAGE_STARTED, stage="clarify"),
    ]
    out = render_events_jsonl(trace)
    lines = out.splitlines()
    assert len(lines) == 2
    first = RunEvent.model_validate_json(lines[0])
    assert first.seq == 0  # sorted by seq
    assert RunEvent.model_validate_json(lines[1]).seq == 1


def test_report_html_is_self_contained_and_covers_sections():
    html = render_report_html(_summary())
    assert html.lstrip().startswith("<!doctype html>")
    # self-contained: no external resource references
    assert "http://" not in html.replace("deployed:http://pr", "")
    assert "src=" not in html and "href=" not in html
    for token in ("r1", "deployed:", "clarify", "merge", "scope?", "coverage"):
        assert token in html


def test_report_html_renders_role_table():
    now = datetime.now(UTC)
    s = RunSummary(
        run_id="r1",
        mode="greenfield",
        outcome="deployed:x",
        terminal_stage="deploy",
        started_at=now,
        ended_at=now,
        duration_s=1.0,
        roles=[
            RoleUsage(
                role="architect",
                model="anthropic:o",
                calls=2,
                input_tokens=1500,
                output_tokens=300,
                cost_usd=1.25,
            )
        ],
        budget_usd=5.0,
        budget_crossings=1,
    )
    html = render_report_html(s)
    assert "architect" in html
    assert "$1.2500" in html
    assert "budget" in html.lower()


# --- FR-304 (RED): the gates table shows the full decision record --------------


def test_report_html_gates_table_shows_full_record():
    """One full-field row (reject, distinguishable from revise) and one
    pre-change row (None fields render as '-'), comments truncated at 80."""
    from sdlc.core.models import GateOutcome

    s = _summary()
    s.gates = [
        GateOutcomeSummary(
            gate="merge",
            round=2,
            policy="hard",
            decided_by="human",
            approved=False,
            outcome=GateOutcome.REJECT,
            reviewer="maksim & co",
            comments="not ready; " + "x" * 100,
            decided_at=datetime(2026, 11, 15, 9, 0, tzinfo=UTC),
        ),
        GateOutcomeSummary(
            gate="architecture", round=1, policy="hard", decided_by="human", approved=True
        ),
    ]
    html = render_report_html(s)
    flat = html.replace("\n", "")
    # the header row names every FR-304 column in order
    header = "<tr><th>gate</th><th>round</th><th>policy</th><th>decided_by</th>" \
        "<th>reviewer</th><th>outcome</th><th>confidence</th><th>overrides</th>" \
        "<th>decided_at</th><th>comments</th></tr>"
    assert header in flat
    # full-field row: escaped reviewer, the three-valued outcome, short-form
    # timestamp, truncated comments (80 + ellipsis marker)
    assert "maksim &amp; co" in html
    assert "<td>reject</td>" in html
    assert "<td>2026-11-15 09:00</td>" in html
    assert f"not ready; {'x' * 78}…" in html
    assert "x" * 79 not in html  # nothing past the truncation point
    # pre-change row renders '-' for every absent FR-304 field
    assert "<td>architecture</td><td>1</td><td>hard</td><td>human</td>" \
        "<td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td>" in html
