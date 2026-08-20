"""Toolset shape, approval flags, asset loading, and per-request reset."""
import asyncio

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.operator import agent as chat_agent
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps


def test_twelve_tools_nine_read_three_write():
    assert len(chat_agent.READ_TOOLS) == 9
    assert len(chat_agent.WRITE_TOOLS) == 3
    names = {f.__name__ for f in chat_agent.READ_TOOLS + chat_agent.WRITE_TOOLS}
    assert names == {
        "list_runs", "get_run", "follow", "inbox", "list_projects",
        "get_project", "list_tasks", "project_events", "read_artifact",
        "start_run", "answer_question", "decide_gate"}


def test_only_the_writes_require_approval():
    ts = chat_agent.build_toolset()
    approval = {name: t.requires_approval for name, t in ts.tools.items()}
    assert approval["decide_gate"] is True
    assert approval["answer_question"] is True
    assert approval["start_run"] is True
    assert approval["list_runs"] is False
    assert approval["follow"] is False


def test_binding_hides_deps_from_the_model_schema():
    ts = chat_agent.build_toolset()
    assert "deps" not in ts.tools["get_run"].function_schema.json_schema[
        "properties"]
    assert "run_id" in ts.tools["get_run"].function_schema.json_schema[
        "properties"]


def test_chat_config_loads_the_versioned_assets():
    cfg = chat_agent.load_chat_config()
    assert cfg.model
    assert cfg.instructions.strip()
    assert "key" in cfg.instructions.lower()


def test_missing_asset_directory_is_a_clear_error(tmp_path):
    with pytest.raises(chat_agent.ChatConfigError) as e:
        chat_agent.load_chat_config(tmp_path)
    assert "agent.yaml" in str(e.value)


def test_empty_instructions_are_refused(tmp_path):
    (tmp_path / "agent.yaml").write_text("model: anthropic:claude-sonnet-4-6\n",
                                         encoding="utf-8")
    (tmp_path / "instructions.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(chat_agent.ChatConfigError) as e:
        chat_agent.load_chat_config(tmp_path)
    assert "empty" in str(e.value)


@pytest.mark.asyncio
async def test_the_orientation_line_reaches_the_prompt(monkeypatch):
    class FakePoller:
        async def snapshot(self):
            from datetime import datetime, timezone

            from sdlc.dashboard.fleet import FleetSnapshot
            from sdlc.models import RunState
            at = datetime(2026, 8, 20, tzinfo=timezone.utc)
            return FleetSnapshot(
                at=at, total_open_runs=1,
                runs=[RunState(run_id="r1", title="t", mode="greenfield",
                               status="running", started_at=at)])

    deps = OperatorDeps(poller=FakePoller(), board=None, starter=None)
    a = chat_agent.build_agent()
    with a.override(model=TestModel(call_tools=[])):
        result = await a.run("hello", deps=deps)
    assert result.output is not None



@pytest.mark.asyncio
async def test_each_http_request_clears_the_follow_streak():
    deps = OperatorDeps(poller=None, board=None, starter=None)
    deps.note_follow()
    app = chat_agent._ResetPerRequest(_noop_asgi, deps)
    await app({"type": "http"}, _recv, _send)
    assert deps.follow_calls == 0


async def _noop_asgi(scope, receive, send):
    return None


async def _recv():
    return {"type": "http.request"}


async def _send(message):
    return None
