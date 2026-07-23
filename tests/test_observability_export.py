from datetime import datetime, timezone

from sdlc.models import (
    ClarificationOutcome, GateOutcomeSummary, RoleUsage, RunSummary,
    StageOutcome,
)
from sdlc.observability.export import render_events_jsonl, render_report_html
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _summary():
    return RunSummary(
        run_id="r1", mode="greenfield", outcome="deployed:http://pr",
        terminal_stage="deploy", started_at=T0, ended_at=T0, duration_s=0.0,
        stages=[StageOutcome(stage="clarify", role="clarify", outcome="pass",
                             duration_s=2.0, cost_usd=0.1)],
        clarifications=[ClarificationOutcome(question_id="q1", question="scope?",
                                             answered_by="human")],
        gates=[GateOutcomeSummary(gate="merge", round=1, policy="soft",
                                  decided_by="human", approved=True,
                                  overrides=["coverage"])],
        cost_usd_total=0.1, memory_enabled=True, memory_watermark="3",
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
    now = datetime.now(timezone.utc)
    s = RunSummary(run_id="r1", mode="greenfield", outcome="deployed:x",
                   terminal_stage="deploy", started_at=now, ended_at=now,
                   duration_s=1.0,
                   roles=[RoleUsage(role="architect", model="anthropic:o",
                                    calls=2, input_tokens=1500,
                                    output_tokens=300, cost_usd=1.25)],
                   budget_usd=5.0, budget_crossings=1)
    html = render_report_html(s)
    assert "architect" in html
    assert "$1.2500" in html
    assert "budget" in html.lower()
