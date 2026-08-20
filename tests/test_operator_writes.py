"""Write verbs: kind enforcement, derived rounds, receipts, actor identity."""
import pytest

from sdlc.channels.transport import SubmitResult
from sdlc.models import GateOutcome, ProjectMode
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError
from sdlc.pending import ClarifyPending, StageGatePending

GATE = StageGatePending(key="architecture#2", gate="architecture", round=2,
                        spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")


class FakeHandle:
    def __init__(self, run_id, pending):
        self.id = run_id
        self._pending = list(pending)


class FakeClient:
    def __init__(self, handle):
        self._handle = handle

    def get_workflow_handle(self, run_id):
        return self._handle


class FakePoller:
    def __init__(self, handle):
        self._handle = handle

    async def _client_or_connect(self):
        return FakeClient(self._handle)


@pytest.fixture
def submitted():
    return []


@pytest.fixture
def deps(monkeypatch, submitted):
    handle = FakeHandle("feature-add-sso", [GATE, Q1])

    async def fake_resolve_key(h, key):
        for d in h._pending:
            if d.key == key:
                return d
        from sdlc.channels.transport import NoMatch
        raise NoMatch(f"no pending item with key '{key}' on this run")

    async def fake_submit(h, pending, reply, channel=None):
        call = channel.translate(pending, reply)
        submitted.append((h.id, pending.key, reply, call))
        return SubmitResult(confirmed=True, message=f"ok on {h.id}")

    monkeypatch.setattr(tools, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(tools, "submit", fake_submit)
    started = []

    async def fake_starter(idea, cfg, wf_id):
        started.append((idea, cfg, wf_id))
        return wf_id

    d = OperatorDeps(poller=FakePoller(handle), board=None,
                     starter=fake_starter, actor="chat:mika")
    d.started = started
    return d


@pytest.mark.asyncio
async def test_decide_gate_returns_a_confirmed_receipt(deps, submitted):
    got = await tools.decide_gate(deps, "feature-add-sso", "architecture#2",
                                  GateOutcome.APPROVE)
    assert got.confirmed is True
    assert got.run_id == "feature-add-sso"
    assert got.key == "architecture#2"


@pytest.mark.asyncio
async def test_decide_gate_never_types_the_round(deps, submitted):
    await tools.decide_gate(deps, "feature-add-sso", "architecture#2",
                            GateOutcome.APPROVE)
    _, _, _, call = submitted[0]
    assert call.decision.round == 2          # from the pending item, not typed


@pytest.mark.asyncio
async def test_decide_gate_stamps_the_actor_as_reviewer(deps, submitted):
    await tools.decide_gate(deps, "feature-add-sso", "architecture#2",
                            GateOutcome.REVISE, text="split the queue")
    _, _, _, call = submitted[0]
    assert call.decision.reviewer == "chat:mika"
    assert call.decision.decided_by == "human"
    assert call.decision.guidance == "split the queue"


@pytest.mark.asyncio
async def test_decide_gate_refuses_a_question_key(deps):
    with pytest.raises(ToolError) as e:
        await tools.decide_gate(deps, "feature-add-sso", "Q1",
                                GateOutcome.APPROVE)
    assert "answer_question" in e.value.message


@pytest.mark.asyncio
async def test_answer_question_refuses_a_gate_key(deps):
    with pytest.raises(ToolError) as e:
        await tools.answer_question(deps, "feature-add-sso", "architecture#2",
                                    "sure")
    assert "decide_gate" in e.value.message


@pytest.mark.asyncio
async def test_answer_question_sends_the_text(deps, submitted):
    got = await tools.answer_question(deps, "feature-add-sso", "Q1", "Okta")
    assert got.confirmed is True
    _, _, reply, call = submitted[0]
    assert call.signal == "answer_question"
    assert call.answer == "Okta"


@pytest.mark.asyncio
async def test_stale_key_is_a_tool_error_telling_the_model_to_re_read(deps):
    with pytest.raises(ToolError) as e:
        await tools.answer_question(deps, "feature-add-sso", "Q9", "x")
    assert "re-read" in e.value.message.lower()


@pytest.mark.asyncio
async def test_unconfirmed_is_reported_not_raised(deps, monkeypatch):
    async def unconfirmed(h, pending, reply, channel=None):
        return SubmitResult(confirmed=False, message="not confirmed: still "
                                                     "pending")
    monkeypatch.setattr(tools, "submit", unconfirmed)
    got = await tools.decide_gate(deps, "feature-add-sso", "architecture#2",
                                  GateOutcome.APPROVE)
    assert got.confirmed is False
    assert "not confirmed" in got.detail


@pytest.mark.asyncio
async def test_start_run_builds_the_workflow_id_from_the_title(deps):
    run_id = await tools.start_run(deps, title="Add SSO",
                                   mode=ProjectMode.BROWNFIELD,
                                   repo="git@example.com:k.git")
    assert run_id.startswith("feature-")
    idea, _, wf_id = deps.started[0]
    assert wf_id == run_id
    assert idea.repo_url == "git@example.com:k.git"
    assert idea.mode is ProjectMode.BROWNFIELD


@pytest.mark.asyncio
async def test_start_run_requires_a_repo_for_brownfield(deps):
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="Add SSO",
                              mode=ProjectMode.BROWNFIELD)
    assert "repo" in e.value.message.lower()


@pytest.mark.asyncio
async def test_start_run_reports_a_duplicate_id_clearly(deps):
    async def already(idea, cfg, wf_id):
        raise RuntimeError("Workflow execution already started")
    deps.starter = already
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="Add SSO",
                              mode=ProjectMode.GREENFIELD)
    assert "already" in e.value.message.lower()


@pytest.mark.asyncio
async def test_writes_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.answer_question(deps, "feature-add-sso", "Q1", "Okta")
    assert deps.follow_calls == 0


@pytest.mark.asyncio
async def test_start_run_uses_the_id_the_starter_returns(deps):
    async def renaming_starter(idea, cfg, wf_id):
        return wf_id + "-2"
    deps.starter = renaming_starter
    got = await tools.start_run(deps, title="Add SSO",
                                mode=ProjectMode.GREENFIELD)
    assert got == "feature-add-sso-2"


@pytest.mark.asyncio
async def test_a_title_with_no_alphanumerics_is_refused(deps):
    """slug() strips everything else, so this would start a run called
    bare 'feature-'."""
    with pytest.raises(ToolError) as e:
        await tools.start_run(deps, title="!!!", mode=ProjectMode.GREENFIELD)
    assert "descriptive title" in e.value.message
