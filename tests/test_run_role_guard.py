"""RoleHost._run_role forwards the run's override and guards the label
(004 T026, FR-002; contracts/model-resolution-contract.md).

The contract table:

| forwarded_model(cfg, role) | Call made                                  |
|----------------------------|--------------------------------------------|
| None (no / equal override) | agent.run(*args, **kwargs) exactly as today |
| override, label agrees     | agent.run(*args, model=<override>, **kwargs)|
| override, label differs    | none — non-retryable error                  |
| kwargs carries `model`     | none — non-retryable error                  |

Pricing, usage tracking and the return value are unchanged (the recording
host below pins that _track_usage still sees the label model). Cases 1 and 2
pin today's behaviour and must stay green through 004; cases 3-5 are RED on
main — main never forwards `model=` and never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.agents.roles import REGISTRY
from sdlc.core.models import PipelineConfig, RoleConfig
from sdlc.workflows.role_host import RoleHost

_OVERRIDE = "openai:gpt-5.2"
_REGISTRY_MODEL = REGISTRY["architect"].model
assert _REGISTRY_MODEL is not None and _REGISTRY_MODEL != _OVERRIDE


def _cfg(override: str | None) -> PipelineConfig:
    cfg = PipelineConfig()
    if override is not None:
        cfg.roles["architect"] = RoleConfig(kind="proposer", model=override)
    return cfg


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class _RunResult:
    output: str = "ok"
    usage: _Usage = field(default_factory=_Usage)


class _RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(self, *args: object, **kwargs: object) -> _RunResult:
        self.calls.append({"args": args, "kwargs": kwargs})
        return _RunResult()


class _Host(RoleHost):
    """RoleHost without the ReportHost MRO piece it never touches here —
    zero-usage results skip pricing, so only _track_usage needs a stub."""

    def __init__(self) -> None:
        super().__init__()
        self.tracked: list[dict[str, object]] = []

    def _track_usage(self, **kw: object) -> None:
        self.tracked.append(kw)


@pytest.mark.asyncio
async def test_no_override_calls_run_without_model_kwarg():
    host, agent = _Host(), _RecordingAgent()
    result = await host._run_role(_cfg(None), "architect", _REGISTRY_MODEL, agent, "prompt")
    assert result.output == "ok"
    assert agent.calls == [{"args": ("prompt",), "kwargs": {}}]


@pytest.mark.asyncio
async def test_override_equal_to_registry_model_calls_as_today():
    """E1: an override naming the registry model behaves exactly like no
    override — no model= kwarg, no guard."""
    host, agent = _Host(), _RecordingAgent()
    await host._run_role(_cfg(_REGISTRY_MODEL), "architect", _REGISTRY_MODEL, agent, "prompt")
    assert agent.calls == [{"args": ("prompt",), "kwargs": {}}]


@pytest.mark.asyncio
async def test_override_with_matching_label_forwards_the_model():
    host, agent = _Host(), _RecordingAgent()
    await host._run_role(_cfg(_OVERRIDE), "architect", _OVERRIDE, agent, "prompt")
    assert agent.calls == [{"args": ("prompt",), "kwargs": {"model": _OVERRIDE}}]
    assert host.tracked and host.tracked[0]["model"] == _OVERRIDE


@pytest.mark.asyncio
async def test_override_with_disagreeing_label_fails_non_retryably():
    """FR-002/V11: a call site whose label disagrees with what would be
    forwarded must fail loudly, before any model call, rather than record a
    label the model never had."""
    host, agent = _Host(), _RecordingAgent()
    with pytest.raises(ApplicationError) as excinfo:
        await host._run_role(_cfg(_OVERRIDE), "architect", _REGISTRY_MODEL, agent, "prompt")
    assert excinfo.value.non_retryable, "the guard must be a non-retryable failure"
    message = str(excinfo.value)
    assert "architect" in message
    assert _REGISTRY_MODEL in message, "the message must name the caller's label"
    assert _OVERRIDE in message, "the message must name the forwarded override"
    assert not agent.calls, "the guarded call must not reach the model"


@pytest.mark.asyncio
async def test_caller_supplied_model_kwarg_is_rejected():
    """`model` is _run_role's own positional parameter (signature unchanged
    per the contract), so a keyword `model=` can never enter **kwargs — it
    fails loudly at the call boundary and cannot silently reach agent.run.
    The contract's non-retryable guard covers the label-disagreement row;
    this row is enforced by the signature itself."""
    host, agent = _Host(), _RecordingAgent()
    with pytest.raises(TypeError, match="multiple values"):
        await host._run_role(
            _cfg(_OVERRIDE), "architect", _OVERRIDE, agent, "prompt", model="smuggled"
        )
    assert not agent.calls
