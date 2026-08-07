# tests/test_board_api_writes.py
"""Agent write routes: If-Match, conflict, invalid transition, authority."""
import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore
from sdlc.board.api import create_app
from sdlc.board.store import BoardStore
from sdlc.models import DevTask


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj")
    _, plan_v = seed.publish_artifact_version(
        "proj", "plan", "run-1", b"{}", actor="workflow:run-1")
    seed.sync_plan_tasks("proj", plan_v, "run-1", [
        DevTask(id="T01", title="a", description="d",
                acceptance_criteria=["x"]),
    ], actor="workflow:run-1")
    seed.close()
    c = TestClient(create_app(lambda: BoardStore(db=db, blobs=blobs)))
    c.plan_v = plan_v
    return c


def test_claim_moves_status_and_bumps_row_version(client):
    r = client.post("/projects/proj/tasks/T01/claim",
                    headers={"If-Match": "1", "X-Actor": "agent:worker-a"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "in_progress"
    assert body["row_version"] == 2


def test_claim_does_not_move_authoritative_status(client):
    body = client.post("/projects/proj/tasks/T01/claim",
                       headers={"If-Match": "1",
                                "X-Actor": "agent:a"}).json()
    assert body["authoritative_status"] == "pending", \
        "an agent claim is observational — scoring must not see it"


def test_second_claim_with_stale_if_match_is_409(client):
    client.post("/projects/proj/tasks/T01/claim",
                headers={"If-Match": "1", "X-Actor": "agent:a"})
    r = client.post("/projects/proj/tasks/T01/claim",
                    headers={"If-Match": "1", "X-Actor": "agent:b"})
    assert r.status_code == 409


def test_missing_if_match_is_428(client):
    r = client.post("/projects/proj/tasks/T01/claim",
                    headers={"X-Actor": "agent:a"})
    assert r.status_code == 428


def test_invalid_transition_is_422(client):
    r = client.patch("/projects/proj/tasks/T01",
                     json={"status": "done"},
                     headers={"If-Match": "1", "X-Actor": "agent:a"})
    assert r.status_code == 422


def test_rejected_write_appends_no_event(client):
    before = len(client.get("/projects/proj/events").json())
    client.patch("/projects/proj/tasks/T01", json={"status": "done"},
                 headers={"If-Match": "1", "X-Actor": "agent:a"})
    assert len(client.get("/projects/proj/events").json()) == before


def test_patch_records_actor_and_detail(client):
    client.patch("/projects/proj/tasks/T01",
                 json={"status": "blocked", "detail": "waiting on infra"},
                 headers={"If-Match": "1", "X-Actor": "agent:worker-a"})
    ev = client.get("/projects/proj/events").json()[-1]
    assert ev["actor"] == "agent:worker-a"
    assert ev["authority"] == "observational"
    assert ev["detail"] == "waiting on infra"


def test_unknown_task_is_404(client):
    r = client.patch("/projects/proj/tasks/T99", json={"status": "blocked"},
                     headers={"If-Match": "1", "X-Actor": "agent:a"})
    assert r.status_code == 404


def test_stale_plan_cannot_claim_on_current_plan(client, tmp_path):
    """An agent holding an old plan version addresses that plan, not the
    current one — it must not silently claim a task on today's plan."""
    r = client.post(f"/projects/proj/tasks/T01/claim?plan={client.plan_v + 99}",
                    headers={"If-Match": "1", "X-Actor": "agent:a"})
    assert r.status_code == 404
