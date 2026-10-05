"""The token-free dry run (`python -m sdlc.demo`).

The fast tests pin what keeps the shipped command honest without a server:
its scripted seams still carry production names, and its placeholder keys
never clobber a real one. The temporal test runs it end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from sdlc.agents.roles import ALL_TEMPORAL_AGENTS
from sdlc.channels.contract import Reply
from sdlc.core.models import GateOutcome
from sdlc.demo.canned import AGENT_SPECS, demo_config, demo_idea
from sdlc.demo.env import PLACEHOLDER, PROVIDER_KEYS, use_placeholder_keys
from sdlc.demo.fakes import REAL, SCRIPTED, demo_activities
from sdlc.demo.run import DemoResult, _reply_for, demo_run_id, render_result, run_demo
from sdlc.pending import ClarifyPending, StageGatePending
from sdlc.worker import get_worker_activities
from sdlc.workflows.graph_catalog import build_run_input


def _name(fn) -> str:
    return fn.__temporal_activity_definition.name


def test_placeholder_keys_fill_unset_and_empty_only(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a-real-key")
    monkeypatch.setenv("OPENAI_API_KEY", "another-real-key")

    filled = use_placeholder_keys()

    assert sorted(filled) == ["EXA_API_KEY", "ZAI_API_KEY"]
    import os

    assert os.environ["EXA_API_KEY"] == PLACEHOLDER
    assert os.environ["ZAI_API_KEY"] == PLACEHOLDER
    assert os.environ["ANTHROPIC_API_KEY"] == "a-real-key"
    assert os.environ["OPENAI_API_KEY"] == "another-real-key"
    assert set(filled) <= set(PROVIDER_KEYS)


def test_every_scripted_activity_carries_a_production_name():
    """A stand-in dispatches only because its name matches. Rename the real
    activity and the dry run would fail mid-run on an unregistered type;
    this fails here instead, naming it."""
    production = {_name(a) for a in get_worker_activities()}
    scripted = [_name(a) for a in SCRIPTED]
    assert [n for n in scripted if n not in production] == []
    assert len(scripted) == len(set(scripted))


def test_real_activities_are_the_production_objects():
    production = list(get_worker_activities())
    assert all(any(a is p for p in production) for a in REAL)


def test_no_activity_name_is_registered_twice():
    # Worker() refuses duplicates at construction, before any workflow runs.
    names = [_name(a) for a in demo_activities(AGENT_SPECS)]
    assert len(names) == len(set(names))


def test_scripted_agents_are_registry_agents():
    registry = {a.name for a in ALL_TEMPORAL_AGENTS}
    assert [name for name, _, _ in AGENT_SPECS if name not in registry] == []


def test_canned_outputs_match_their_declared_types():
    assert all(isinstance(value, typ) for _, typ, value in AGENT_SPECS)


def test_demo_input_passes_start_validation():
    # The same validation `sdlc.cli start` runs; raises GraphStartError if not.
    run_input = build_run_input(demo_idea(), demo_config())
    assert run_input.idea.title == "Add a health endpoint"


def test_run_id_is_stamped():
    assert demo_run_id(datetime(2026, 10, 5, 12, 0, 0, tzinfo=UTC)) == "demo-20261005T120000Z"


def test_reply_answers_a_question_with_its_suggestion():
    pending = ClarifyPending(key="q1", question="Q?", why_it_matters="w", suggested_answer="no")
    reply, command = _reply_for(pending)
    assert reply == Reply(text="no")
    assert command == 'answer --q q1 --text "no"'


def test_reply_approves_a_gate():
    pending = StageGatePending(key="plan:1", gate="plan", round=1, spec_summary="s")
    reply, command = _reply_for(pending)
    assert reply == Reply(outcome=GateOutcome.APPROVE)
    assert command == "approve --gate plan"


def test_render_result_without_a_summary_still_names_the_report():
    result = DemoResult(run_id="demo-x", outcome="deployed: v1", summary=None, report_dir=Path("r"))
    text = render_result(result)
    assert "outcome: deployed: v1" in text
    assert "report.html" in text
    assert text.isascii()
    assert result.ok


def test_a_run_that_did_not_deploy_is_not_ok():
    result = DemoResult(run_id="demo-x", outcome="rejected: plan", summary=None, report_dir=Path())
    assert not result.ok


@pytest.mark.temporal
@pytest.mark.asyncio
async def test_demo_runs_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    lines: list[str] = []
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        # Each gate opens a durable timer; with skipping on, the test server
        # can jump to its expiry before the driver's signal lands.
        with env.auto_time_skipping_disabled():
            result = await run_demo(env.client, emit=lines.append, timeout_s=60)

    assert result.ok, result.outcome
    assert result.summary is not None
    assert {g.gate for g in result.summary.gates} >= {"architecture", "plan", "deploy"}
    assert all(g.decided_by == "human" and g.approved for g in result.summary.gates)
    assert (tmp_path / result.run_id / "report.html").is_file()
    assert (tmp_path / result.run_id / "summary.json").is_file()
    assert any("answered q1" in line for line in lines)
    assert all(line.isascii() for line in lines)
