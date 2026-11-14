"""RoleHost._run_role forwards each role's configured validated-output
retry budget (FR-202, VR-3): OUTPUT_RETRIES is the registry-derived map,
and the single model-egress point is where a proposer's widened budget
reaches the model -- `run(..., retries={"output": n})`, only when n != 1
(the 004 D7a only-when-set precedent: a default role's call carries no
retries kwarg at all, byte-identical to a call that never knew about
the knob).

Import discipline (the harvest-file precedent): this file imports
nothing that does not exist on the pre-Task-3 commit and monkeypatches
the module attribute with raising=False, so it collects and runs there
-- the forwarding test fails on behaviour (no retries kwarg yet), while
the default-role and setdefault tests pass (PIN): nothing is forwarded
today, and a caller's explicit retries already flows through **kwargs
untouched. After the cutover all three are green."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from sdlc.core.models import PipelineConfig
from sdlc.workflows import role_host
from sdlc.workflows.role_host import RoleHost


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class _RunResult:
    """The guard-file result shape: .output and .usage, no new_messages.
    Zero usage prices nothing and harvests nothing, so the only thing
    under observation is the kwargs agent.run received."""

    output: str = "ok"
    usage: _Usage = field(default_factory=_Usage)


class _RecordingAgent:
    """Records every kwargs dict agent.run received -- the forwarding is
    observable only on the calling side."""

    def __init__(self, result: _RunResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def run(self, *args: Any, **kwargs: Any) -> _RunResult:
        self.calls.append(kwargs)
        return self.result


class _Host(RoleHost):
    """RoleHost with _track_usage recorded (the guard-file stub): a
    zero-usage result tracks one row and schedules no activity."""

    def __init__(self) -> None:
        super().__init__()
        self.tracked: list[dict[str, object]] = []

    def _track_usage(self, **kw: object) -> None:
        self.tracked.append(kw)


async def _forwarded(
    monkeypatch: pytest.MonkeyPatch, patched: dict[str, int], role: str = "planner"
) -> dict:
    """One _run_role call with role_host.OUTPUT_RETRIES patched to
    `patched`; returns the (single) kwargs dict agent.run received."""
    monkeypatch.setattr(role_host, "OUTPUT_RETRIES", patched, raising=False)
    host = _Host()
    agent = _RecordingAgent(_RunResult())
    await host._run_role(PipelineConfig(), role, "m", agent, "p")
    assert len(agent.calls) == 1
    return agent.calls[0]


@pytest.mark.asyncio
async def test_configured_role_gets_its_budget_forwarded(monkeypatch):
    """VR-3 (RED): a role configured 3 in the registry map makes the
    single model-egress point call run with retries={"output": 3} --
    pydantic-ai's per-call override of the construction default, which is
    how the registry budget reaches the model without pinning it in every
    agent.py."""
    kwargs = await _forwarded(monkeypatch, {"planner": 3})
    assert kwargs.get("retries") == {"output": 3}


@pytest.mark.asyncio
async def test_role_at_default_forwards_nothing(monkeypatch):
    """VR-3 (PIN): a role at 1 -- the registry default, and the
    .get(role, 1) fallback for a role the map does not carry -- forwards
    NO retries kwarg: the call is byte-identical to one that never knew
    about the knob."""
    assert "retries" not in await _forwarded(monkeypatch, {"planner": 1})
    assert "retries" not in await _forwarded(monkeypatch, {})


@pytest.mark.asyncio
async def test_explicit_caller_retries_are_not_clobbered(monkeypatch):
    """VR-3 (PIN): setdefault semantics -- a caller that already passes
    retries keeps it; the configured budget must not overwrite an explicit
    value. No caller passes retries today; this pins the choice the
    idiom makes."""
    monkeypatch.setattr(role_host, "OUTPUT_RETRIES", {"planner": 3}, raising=False)
    host = _Host()
    agent = _RecordingAgent(_RunResult())
    await host._run_role(PipelineConfig(), "planner", "m", agent, "p", retries={"output": 5})
    assert agent.calls[0]["retries"] == {"output": 5}
