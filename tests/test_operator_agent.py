"""Toolset shape, approval flags, asset loading, and per-request reset."""
import asyncio

import pytest
from pydantic_ai.models.test import TestModel

from sdlc.operator import agent as chat_agent
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps


def _test_cfg():
    """A config naming pydantic-ai's built-in 'test' model.

    build_agent() constructs the configured model eagerly, so using the real
    agent.yaml would make these tests depend on ANTHROPIC_API_KEY being in
    the environment -- which it only was by accident, via the load_dotenv()
    that sdlc.cli used to run when tools.py still imported it.
    """
    return chat_agent.ChatConfig(model="test", max_tokens=1000,
                                 instructions="test instructions")


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
    a = chat_agent.build_agent(_test_cfg())
    with a.override(model=TestModel(call_tools=[])):
        result = await a.run("hello", deps=deps)
    assert result.output is not None



@pytest.mark.asyncio
async def test_a_chat_post_clears_the_follow_streak():
    deps = OperatorDeps(poller=None, board=None, starter=None)
    deps.note_follow()
    app = chat_agent._ResetPerRequest(_noop_asgi, deps)
    await app({"type": "http", "method": "POST", "path": "/chat/api/chat"},
              _recv, _send)
    assert deps.follow_calls == 0


@pytest.mark.asyncio
async def test_loading_the_ui_page_does_not_clear_the_streak():
    """create_web_app serves the UI shell at / and /{id}. Resetting on those
    meant a second tab or a plain reload dissolved the consecutive-wait
    brake mid-conversation."""
    deps = OperatorDeps(poller=None, board=None, starter=None)
    deps.note_follow()
    app = chat_agent._ResetPerRequest(_noop_asgi, deps)
    for path in ("/chat/", "/chat/some-conversation-id"):
        await app({"type": "http", "method": "GET", "path": path},
                  _recv, _send)
    assert deps.follow_calls == 1


@pytest.mark.asyncio
async def test_a_tool_error_reaches_the_model_instead_of_killing_the_turn():
    """The whole point of errors.py. Only ModelRetry and ToolFailed become a
    tool return the model reads; any other exception propagates out of
    Agent.run and 500s the chat request. ToolFailed also leaves the retry
    budget alone, so a second miss does not become UnexpectedModelBehavior."""
    from datetime import datetime, timezone

    from pydantic_ai.models.test import TestModel

    from sdlc.dashboard.fleet import FleetSnapshot

    class EmptyFleet:
        async def snapshot(self):
            return FleetSnapshot(at=datetime.now(timezone.utc))

    deps = OperatorDeps(poller=EmptyFleet(), board=None, starter=None)
    a = chat_agent.build_agent(_test_cfg())
    with a.override(model=TestModel(call_tools=["get_run"])):
        result = await a.run("check run nope", deps=deps)
    assert result.output is not None


@pytest.mark.asyncio
async def test_the_follow_brake_also_reaches_the_model():
    from pydantic_ai.exceptions import ToolFailed

    deps = OperatorDeps(poller=None, board=None, starter=None,
                        max_follow_calls=0)
    bound = chat_agent._bind(tools.follow)

    class Ctx:
        pass

    ctx = Ctx()
    ctx.deps = deps
    with pytest.raises(ToolFailed) as e:
        await bound(ctx, run_id="r1", timeout_s=5)
    assert "report to the operator" in str(e.value)


async def _noop_asgi(scope, receive, send):
    return None


async def _recv():
    return {"type": "http.request"}


async def _send(message):
    return None


def test_asset_dir_honours_the_env_override(monkeypatch, tmp_path):
    """parents[3] is the repo root only for a source checkout; from
    site-packages it lands on <prefix>/lib. The image sets SDLC_CHAT_ASSETS
    for the same reason the Dockerfile sets SDLC_CASES_ROOT."""
    monkeypatch.setenv(chat_agent.ASSETS_ENV, str(tmp_path))
    assert chat_agent.asset_dir() == tmp_path


def test_asset_dir_falls_back_to_the_checkout(monkeypatch):
    monkeypatch.delenv(chat_agent.ASSETS_ENV, raising=False)
    assert chat_agent.asset_dir().name == "chat"
    assert (chat_agent.asset_dir() / "agent.yaml").is_file()
