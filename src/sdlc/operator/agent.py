"""The chat surface's Pydantic AI agent (E-86).

The ONLY module in sdlc/operator that imports pydantic_ai. tools.py stays
framework-free so E-11's MCP server can import the same functions; this file
is the chat-shaped adapter, and mcp.py will be its sibling.

Two things here are load-bearing and non-obvious:

* _bind rewrites each verb's signature to swap `deps` for a RunContext.
  Pydantic AI derives a tool's JSON schema from the signature, so the
  rewrite is what keeps `deps` out of the schema the model sees.
* _ResetPerRequest zeroes the follow streak per HTTP request. create_web_app
  holds ONE deps object for the life of the mount, so without this the brake
  would be per-process rather than per-conversation-turn.
"""
from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import FunctionToolset
try:
    from pydantic_ai.ui import create_web_app
except ImportError:
    from pydantic_ai.ui._web import create_web_app


from ..models import GateOutcome, ProjectMode
from . import render, tools
from .deps import OperatorDeps
from .tools import ArtifactRead, ChangeReport, ReplyReceipt


ASSET_DIR = Path(__file__).resolve().parents[3] / "interfaces" / "chat"

READ_TOOLS = (tools.list_runs, tools.get_run, tools.follow, tools.inbox,
              tools.list_projects, tools.get_project, tools.list_tasks,
              tools.project_events, tools.read_artifact)
WRITE_TOOLS = (tools.start_run, tools.answer_question, tools.decide_gate)


class ChatConfigError(Exception):
    """The chat assets are missing or unusable. Never fatal to the dashboard;
    main.py catches this and skips the mount."""


@dataclass
class ChatConfig:
    model: str
    max_tokens: int
    instructions: str


def load_chat_config(root: Path | None = None) -> ChatConfig:
    root = Path(root) if root is not None else ASSET_DIR
    cfg_file = root / "agent.yaml"
    if not cfg_file.is_file():
        raise ChatConfigError(f"missing {cfg_file}: the chat surface needs an "
                              f"agent.yaml naming its model")
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
    model = data.get("model")
    if not model:
        raise ChatConfigError(f"{cfg_file} declares no model")
    prompt_file = root / "instructions.md"
    if not prompt_file.is_file():
        raise ChatConfigError(f"missing {prompt_file}")
    instructions = prompt_file.read_text(encoding="utf-8")
    if not instructions.strip():
        raise ChatConfigError(
            f"{prompt_file} is empty -- an empty system prompt is a boot-time "
            f"bug, not a runtime surprise")
    return ChatConfig(model=model,
                      max_tokens=int(data.get("max_tokens", 64000)),
                      instructions=instructions)


def _bind(fn):
    """Adapt `fn(deps, ...)` into `tool(ctx, ...)` without leaking deps.

    __signature__ and __annotations__ are both rewritten because Pydantic AI
    reads the signature to build the schema and the annotations to resolve
    types.
    """
    sig = inspect.signature(fn)
    rest = [p for name, p in sig.parameters.items() if name != "deps"]

    async def tool(ctx: RunContext[OperatorDeps], **kwargs):
        return await fn(ctx.deps, **kwargs)

    ctx_param = inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                  annotation=RunContext[OperatorDeps])
    tool.__name__ = fn.__name__
    tool.__doc__ = fn.__doc__
    tool.__signature__ = sig.replace(parameters=[ctx_param, *rest])
    tool.__annotations__ = {p.name: p.annotation for p in rest}
    tool.__annotations__["ctx"] = RunContext[OperatorDeps]
    tool.__annotations__["return"] = sig.return_annotation
    return tool


def build_toolset() -> FunctionToolset:
    ts: FunctionToolset = FunctionToolset()
    for fn in READ_TOOLS:
        ts.add_function(_bind(fn), name=fn.__name__)
    for fn in WRITE_TOOLS:
        # The model proposes; the operator disposes (spec D4).
        ts.add_function(_bind(fn), name=fn.__name__, requires_approval=True)
    return ts


def build_agent(cfg: ChatConfig | None = None) -> Agent:
    cfg = cfg or load_chat_config()
    agent: Agent = Agent(
        cfg.model,
        deps_type=OperatorDeps,
        toolsets=[build_toolset()],
        model_settings=ModelSettings(max_tokens=cfg.max_tokens),
        instructions=cfg.instructions)

    @agent.instructions
    async def _orientation(ctx: RunContext[OperatorDeps]) -> str:
        """One line per open run, recomputed each turn (spec 5.4)."""
        if ctx.deps is None or ctx.deps.poller is None:
            return ""
        try:
            snap = await ctx.deps.poller.snapshot()
        except Exception:       # noqa: BLE001 -- orientation is a nicety
            return "fleet state unavailable right now; use the tools"
        return "Current fleet:\n" + render.orientation(snap)

    return agent


class _ResetPerRequest:
    """ASGI wrapper clearing per-request tool state before the app runs."""

    def __init__(self, app, deps: OperatorDeps) -> None:
        self.app = app
        self.deps = deps

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            self.deps.reset_request_state()
        return await self.app(scope, receive, send)


def build_chat_app(deps: OperatorDeps, cfg: ChatConfig | None = None):
    """The mountable Starlette app: chat UI at /, API under /api."""
    cfg = cfg or load_chat_config()
    app = create_web_app(build_agent(cfg), deps=deps)
    return _ResetPerRequest(app, deps)
