# tests/test_crew_turn.py
"""E-88 §3: a turn is not idempotent. An infrastructure retry must resume the
same session; an agent-level failure must not be retried at all."""

from __future__ import annotations

import tempfile

import pytest
from temporalio.exceptions import ApplicationError

from sdlc.core.models import (
    HarnessKind,
)
from sdlc.crew import activities as crew_acts
from sdlc.crew.activities import (
    AGENT_FAILURE,
    CREW_CONTAINMENT_REFUSED,
    CrewTurnInput,
    run_crew_turn,
)
from sdlc.crew.worktree import orchestration_dir, round_dir
from sdlc.harness.models import (
    ContainmentLayer,
    ContainmentReport,
    HarnessRunResult,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_fake_harness():
    FakeHarness.applied = []
    yield
    FakeHarness.applied = []


class FakeHarness:
    kind = HarnessKind.OPENCODE

    # A harness with NO containment layer fails closed under ADR-17; these
    # tests are about the crew's wiring, not about that refusal, so the fake
    # declares a layer and records what it was asked to compile.
    containment = frozenset({ContainmentLayer.NATIVE})
    applied: list = []

    def apply_containment(self, policy, req, grants=None):
        self.applied.append((policy, req, list(grants or [])))
        return ContainmentReport(
            enabled=True, layers_active=[ContainmentLayer.NATIVE], rules_unenforceable=[]
        )

    def __init__(self, result=None, calls=None):
        self._result = result or HarnessRunResult(
            harness=HarnessKind.OPENCODE,
            exit_code=0,
            summary="ok",
            session_id="s-1",
            cost_usd=0.5,
            input_tokens=100,
            output_tokens=20,
        )
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


# The activity mkdirs the round dir under the worktree, so the default must
# be a writable temp location: a POSIX-looking "/w" is a root-owned path on
# Linux and the mkdir raises PermissionError there.
_DEFAULT_WORKTREE = tempfile.mkdtemp(prefix="sdlc-crew-turn-test-")


def _inp(**kw):
    base = dict(
        worktree=_DEFAULT_WORKTREE,
        layout="code",
        role="coder",
        harness=HarnessKind.OPENCODE,
        model="glm-5.3",
        prompt="do it",
        session_id=None,
        round=1,
        attempt=1,
        turn_timeout_s=60,
        task_id="t1",
    )
    base.update(kw)
    return CrewTurnInput(**base)


async def test_turn_records_cost_and_session(monkeypatch):
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    out = await run_crew_turn(_inp())
    assert out.record.session_id == "s-1"
    assert out.record.cost_usd == 0.5
    assert out.record.cost_incomplete is False


async def test_the_round_directory_exists_before_the_harness_runs(monkeypatch, tmp_path):
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
    fake = FakeHarness(
        result=HarnessRunResult(
            harness=HarnessKind.OPENCODE,
            exit_code=3,
            summary="refused",
            session_id="s-1",
            cost_usd=0.1,
        )
    )
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp())
    assert e.value.non_retryable is True
    assert e.value.type == AGENT_FAILURE


async def test_a_non_retryable_failure_carries_its_cost_reading(monkeypatch):
    """spec §3: an abandoned attempt's cost is recovered from the error's
    details, never silently dropped."""
    fake = FakeHarness(
        result=HarnessRunResult(
            harness=HarnessKind.OPENCODE,
            exit_code=3,
            summary="refused",
            session_id="s-1",
            cost_usd=0.1,
        )
    )
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(_inp())
    assert e.value.details[0]["cost_usd"] == 0.1
    assert e.value.details[0]["session_id"] == "s-1"


async def test_a_contained_turn_compiles_the_policy_instead_of_refusing(monkeypatch, tmp_path):
    """Step 1 refused every contained crew turn, because the fence was not
    wired -- and run.deferred exists ONLY because a containment escalate rule
    matched, so that refusal also made every gate in E-88 step 2 unreachable."""
    policy = tmp_path / "containment.yaml"
    policy.write_text("version: 1\nrules: []\n", encoding="utf-8")
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    out = await run_crew_turn(
        _inp(
            worktree=str(tmp_path),
            writes=True,
            containment_enabled=True,
            containment_policy_path=str(policy),
        )
    )
    assert out.run.exit_code == 0
    assert fake.applied, "the policy was never compiled into the request"
    assert out.run.containment is not None
    assert out.run.containment.enabled is True


async def test_a_non_lead_turn_is_confined_to_the_orchestration_tree(monkeypatch, tmp_path):
    """spec §A: the lead may write repository files; every other role writes
    only under .workspace/orchestration/<layout>/. cwd stays the worktree so
    the role can READ the diff it is criticising."""
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    await run_crew_turn(_inp(worktree=str(tmp_path), role="critic", writes=False))
    req = fake.calls[-1]
    assert req.cwd == str(tmp_path)
    assert req.write_root == str(orchestration_dir(str(tmp_path), "code"))


async def test_the_lead_is_not_confined(monkeypatch, tmp_path):
    """A lead with a write_root could not write the repository at all, which
    is the entire job of the writing role."""
    fake = FakeHarness()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    await run_crew_turn(_inp(worktree=str(tmp_path), writes=True))
    assert fake.calls[-1].write_root is None


async def test_an_unenforceable_policy_still_fails_closed(monkeypatch, tmp_path):
    """ADR-17 is not relaxed by this task: a harness that cannot enforce a
    layer must refuse, non-retryably -- retrying a config error spends
    money to learn the same thing."""
    policy = tmp_path / "containment.yaml"
    policy.write_text("version: 1\nrules: []\n", encoding="utf-8")
    fake = FakeHarness()
    fake.containment = frozenset()
    monkeypatch.setitem(crew_acts.HARNESSES, HarnessKind.OPENCODE, fake)
    with pytest.raises(ApplicationError) as e:
        await run_crew_turn(
            _inp(
                worktree=str(tmp_path),
                writes=True,
                containment_enabled=True,
                containment_policy_path=str(policy),
            )
        )
    assert e.value.type == CREW_CONTAINMENT_REFUSED
    assert e.value.non_retryable is True
