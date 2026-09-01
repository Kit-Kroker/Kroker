"""Dashboard route shapes, error codes, and identity handling."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sdlc.channels.transport import SubmitResult
from sdlc.dashboard.api import create_router
from sdlc.dashboard.fleet import FleetSnapshot
from sdlc.models import RunState
from sdlc.pending import ClarifyPending, StageGatePending

AT = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
ARCH = StageGatePending(key="architecture#1", gate="architecture", round=1, spec_summary="s")
Q1 = ClarifyPending(key="Q1", question="q", why_it_matters="w")
UNCONFIRMED = StageGatePending(key="unconfirmed#1", gate="unconfirmed", round=1, spec_summary="s")


class _FakePoller:
    def __init__(self, snap):
        self._snap = snap

    async def snapshot(self):
        return self._snap


@pytest.fixture
def snap():
    return FleetSnapshot(
        at=AT,
        total_open_runs=1,
        runs=[
            RunState(
                run_id="feature-add-sso",
                title="Add SSO",
                mode="brownfield",
                status="awaiting:architecture",
                started_at=AT,
            )
        ],
    )


@pytest.fixture
def submitted():
    return []


@pytest.fixture
def client(snap, submitted, monkeypatch):
    pendings = {ARCH.key: ARCH, Q1.key: Q1, UNCONFIRMED.key: UNCONFIRMED}

    async def fake_resolve_key(handle, key):
        if key not in pendings:
            from sdlc.channels.transport import NoMatch

            raise NoMatch(f"no pending item with key '{key}' on this run")
        return pendings[key]

    async def fake_submit(handle, pending, reply, channel=None):
        call = channel.translate(pending, reply)
        submitted.append(call)
        if pending.key == "unconfirmed#1":
            return SubmitResult(confirmed=False, message="still pending")
        return SubmitResult(confirmed=True, message="approved")

    async def fake_handle(poller, run_id):
        return object()

    import sdlc.dashboard.api as mod

    monkeypatch.setattr(mod, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(mod, "submit", fake_submit)
    monkeypatch.setattr(mod, "_handle", fake_handle)

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap)))
    return TestClient(app)


def test_get_runs_returns_the_snapshot_runs(client):
    r = client.get("/runs")
    assert r.status_code == 200
    assert [x["run_id"] for x in r.json()] == ["feature-add-sso"]


def test_get_run_returns_one_run(client):
    r = client.get("/runs/feature-add-sso")
    assert r.status_code == 200
    assert r.json()["title"] == "Add SSO"


def test_get_run_404s_on_an_unknown_id(client):
    assert client.get("/runs/nope").status_code == 404


def test_get_inbox_returns_the_snapshot_inbox_and_errors(client):
    r = client.get("/inbox")
    assert r.status_code == 200
    assert r.json()["total_open_runs"] == 1


def test_decide_stamps_the_actor_onto_reviewer(client, submitted):
    r = client.post(
        "/runs/feature-add-sso/decide",
        json={"key": "architecture#1", "outcome": "approve", "text": "ok"},
        headers={"X-Actor": "human:mika"},
    )
    assert r.status_code == 200
    assert submitted[0].decision.reviewer == "human:mika"


def test_decide_leaves_decided_by_as_human(client, submitted):
    client.post(
        "/runs/feature-add-sso/decide",
        json={"key": "architecture#1", "outcome": "approve"},
        headers={"X-Actor": "human:mika"},
    )
    assert submitted[0].decision.decided_by == "human"


def test_decide_defaults_the_actor_when_no_header_is_sent(client, submitted):
    client.post(
        "/runs/feature-add-sso/decide", json={"key": "architecture#1", "outcome": "approve"}
    )
    assert submitted[0].decision.reviewer == "human:unknown"


def test_decide_404s_when_the_key_is_not_pending(client):
    r = client.post("/runs/feature-add-sso/decide", json={"key": "merge#9", "outcome": "approve"})
    assert r.status_code == 404


def test_answer_404s_when_the_key_is_a_gate(client):
    """/answer is for questions: a gate key would build a GateDecision with
    no outcome and 500. Same 404 shape as NoMatch (E-10 review B4)."""
    r = client.post("/runs/feature-add-sso/answer", json={"key": "architecture#1", "text": "x"})
    assert r.status_code == 404


def test_decide_404s_when_the_key_is_a_question(client):
    """/decide is for gates: a clarify key would signal answer_question with
    a None answer (E-10 review B4)."""
    r = client.post("/runs/feature-add-sso/decide", json={"key": "Q1", "outcome": "approve"})
    assert r.status_code == 404


def test_decide_returns_the_submit_result_verbatim(client):
    r = client.post(
        "/runs/feature-add-sso/decide", json={"key": "architecture#1", "outcome": "approve"}
    )
    assert r.json() == {"confirmed": True, "message": "approved"}


def test_answer_routes_a_clarify_key_to_the_answer_question_signal(client, submitted):
    r = client.post("/runs/feature-add-sso/answer", json={"key": "Q1", "text": "OIDC"})
    assert r.status_code == 200
    assert submitted[0].signal == "answer_question"
    assert submitted[0].question_id == "Q1"
    assert submitted[0].answer == "OIDC"


def test_an_unconfirmed_submit_is_reported_as_200_not_an_error(client):
    """confirmed=False is informational: the dominant cause is another
    surface winning the race, which is FR-302 working as designed
    (transport._message). It must never surface as an HTTP error."""
    r = client.post(
        "/runs/feature-add-sso/decide", json={"key": "unconfirmed#1", "outcome": "approve"}
    )
    assert r.status_code == 200
    assert r.json() == {"confirmed": False, "message": "still pending"}


class _AlreadyStarted(Exception):
    pass


@pytest.fixture
def start_client(snap):
    started = []

    async def starter(idea, cfg, wf_id):
        # The route maps any "already started" failure to 409; this stands in
        # for temporalio's WorkflowAlreadyStartedError without importing it.
        if wf_id == "feature-taken":
            raise _AlreadyStarted("Workflow already started")
        started.append((idea, wf_id))
        return wf_id

    app = FastAPI()
    app.include_router(create_router(_FakePoller(snap), starter=starter))
    c = TestClient(app)
    c.started = started
    return c


def test_start_run_builds_the_workflow_id_from_the_title(start_client):
    r = start_client.post(
        "/runs",
        json={
            "title": "Add SSO to portal",
            "description": "d",
            "mode": "brownfield",
            "repo": "git@example:acme/portal",
        },
    )
    assert r.status_code == 200
    assert r.json()["run_id"] == "feature-add-sso-to-portal"
    idea, wf_id = start_client.started[0]
    assert idea.title == "Add SSO to portal"
    assert idea.repo_url == "git@example:acme/portal"


def test_start_run_409s_on_a_duplicate_id(start_client):
    r = start_client.post(
        "/runs", json={"title": "taken", "description": "d", "mode": "greenfield"}
    )
    assert r.status_code == 409
