# tests/test_crew_turn.py
"""E-88 §3: a turn is not idempotent. An infrastructure retry must resume the
same session; an agent-level failure must not be retried at all."""
from __future__ import annotations

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.crew import activities as crew_acts
from sdlc.crew.activities import AGENT_FAILURE, CrewTurnInput, run_crew_turn
from sdlc.crew.worktree import round_dir
from sdlc.models import HarnessKind, HarnessRunResult, ToolGrant

pytestmark = pytest.mark.asyncio


class FakeHarness:
    kind = HarnessKind.OPENCODE

    def __init__(self, result=None, calls=None):
        self._result = result or HarnessRunResult(
            harness=HarnessKind.OPENCODE, exit_code=0, summary="ok",
            session_id="s-1", cost_usd=0.5, input_tokens=100,
            output_tokens=20)
        self.calls = calls if calls is not None else []

    async def run(self, req, heartbeat=None):
        self.calls.append(req)
        if heartbeat:
            heartbeat({"session_id": "s-1", "round": 1, "phase": "streaming"})
        return self._result

    def normalise_denials(self, raw):
        return []

    def normalise_deferral(self, raw):
        return None


def _inp(**kw):
    base = dict(worktree="/w", layout="code", role="coder",
                harness=HarnessKind.OPENCODE, model="glm-5.3",
                prompt="do it", session_id=None, round=1, attempt=1,
                turn_timeout_s=60, task_id="t1")
    base.update(kw)
    return CrewTurnInput(**base)


async def test_turn_records_cost_and_session(monkeypatch):
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    out = await run_crew_turn(_inp())
    assert out.record.session_id == "s-1"
    assert out.record.cost_usd == 0.5
    assert out.record.cost_incomplete is False


async def test_the_round_directory_exists_before_the_harness_runs(
        monkeypatch, tmp_path):
    """The ACTIVITY owns the round dir: the agent must not have to mkdir to
    follow the protocol, because a missing notes.md reads as
    EXIT_PROTOCOL_VIOLATION -- misdiagnosed as 'the agent never ran the
    protocol' when really nobody created the dir."""
    probe = {}

    class Probe(FakeHarness):
        async def run(self, req, heartbeat=None):
            probe["dir"] = round_dir(req.cwd, "code", 1)
            return await super().run(req, heartbeat)

    fake = Probe()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    await run_crew_turn(_inp(worktree=str(tmp_path)))
    assert probe["dir"].is_dir()


async def test_turn_resumes_the_session_it_is_given(monkeypatch):
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    await run_crew_turn(_inp(session_id="s-prior"))
    assert fake.calls[0].session_id == "s-prior"


async def test_a_nonzero_exit_is_non_retryable(monkeypatch):
    """spec §3: an agent-level failure is a RESULT. Retrying it with the same
    prompt is spend without signal."""
    fake = FakeHarness(result=HarnessRunResult(
        harness=HarnessKind.OPENCODE, exit_code=3, summary="refused",
        session_id="s-1", cost_usd=0.1))
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp())
    assert e.value.non_retryable is True
    assert e.value.type == AGENT_FAILURE


async def test_a_non_retryable_failure_carries_its_cost_reading(monkeypatch):
    """spec §3: an abandoned attempt's cost is recovered from the error's
    details, never silently dropped."""
    fake = FakeHarness(result=HarnessRunResult(
        harness=HarnessKind.OPENCODE, exit_code=3, summary="refused",
        session_id="s-1", cost_usd=0.1))
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp())
    assert e.value.details[0]["cost_usd"] == 0.1
    assert e.value.details[0]["session_id"] == "s-1"


async def test_containment_enabled_fails_closed(monkeypatch):
    """ADR-17's worst case: a crew lead running unfenced while the run
    believes it is policed. Containment arrives for crew turns only in
    E-88 step 2; until then the turn refuses rather than run exposed."""
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp(containment_enabled=True))
    assert e.value.non_retryable is True
    assert e.value.type == "crew_containment_unsupported"
    assert "coder" in e.value.message
    assert fake.calls == []               # it never ran unfenced


async def test_grants_fail_closed(monkeypatch):
    """A granted (human-approved) call is exactly as unfenced as a policy
    fence: both must refuse until step 2 wires them in."""
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    grant = ToolGrant(tool_use_id="tu-1", tool="Bash", input_digest="d:aa",
                      rule_id="net", approved=True)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp(grants=[grant]))
    assert e.value.non_retryable is True
    assert e.value.type == "crew_containment_unsupported"
    assert fake.calls == []
