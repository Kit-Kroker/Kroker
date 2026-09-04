# tests/test_board_api_reads.py
"""Board read API: shapes, filters, content resolution, error codes."""

import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.api import create_app
from sdlc.board.models import TaskStatus
from sdlc.board.store import BoardStore
from sdlc.stages.plan.models import DevTask


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj", repo="git@example:acme/x")
    _, vid = seed.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"first"}', actor="workflow:run-1"
    )
    _, plan_v = seed.publish_artifact_version(
        "proj", "plan", "run-1", b'{"tasks":[]}', actor="workflow:run-1"
    )
    seed.sync_plan_tasks(
        "proj",
        plan_v,
        "run-1",
        [
            DevTask(id="T01", title="a", description="d", acceptance_criteria=["x"]),
            DevTask(id="T02", title="b", description="d", acceptance_criteria=["x"]),
        ],
        actor="workflow:run-1",
    )
    seed.set_task_authoritative("proj", plan_v, "T01", TaskStatus.IN_PROGRESS, actor="workflow:r")
    seed.attach_task_evidence("proj", plan_v, "T01", "run-1", "qa", b"{}")
    seed.close()

    app = create_app(lambda: BoardStore(db=db, blobs=blobs))
    c = TestClient(app)
    c.plan_v = plan_v
    c.arch_v = vid
    return c


def test_list_projects(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert [p["key"] for p in r.json()] == ["proj"]


def test_project_detail_lists_artifacts_and_task_rollup(client):
    body = client.get("/projects/proj").json()
    assert {a["key"] for a in body["artifacts"]} == {"architecture", "plan"}
    assert body["stats"]["tasks_by_status"] == {"in_progress": 1, "pending": 1}


def test_artifact_versions_carry_lineage(client):
    body = client.get("/projects/proj/artifacts/architecture").json()
    assert [v["n"] for v in body] == [1]
    assert body[0]["supersedes"] is None


def test_version_content_is_returned(client):
    r = client.get(f"/projects/proj/artifacts/architecture/versions/{client.arch_v}")
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == '{"overview":"first"}'
    assert body["truncated"] is False
    assert body["sha256"]


def test_tasks_default_to_current_plan_version(client):
    body = client.get("/projects/proj/tasks").json()
    assert {t["task_id"] for t in body} == {"T01", "T02"}


def test_tasks_filter_by_status(client):
    body = client.get("/projects/proj/tasks?status=in_progress").json()
    assert [t["task_id"] for t in body] == ["T01"]


def test_task_detail_includes_evidence(client):
    body = client.get("/projects/proj/tasks/T01").json()
    assert body["task"]["task_id"] == "T01"
    assert [e["kind"] for e in body["evidence"]] == ["qa"]


def test_events_are_the_change_log(client):
    body = client.get("/projects/proj/events").json()
    subjects = [e["subject"] for e in body]
    assert "artifact:architecture" in subjects
    assert f"task:{client.plan_v}:T01" in subjects


def test_events_since_filters(client):
    everything = client.get("/projects/proj/events").json()
    tail = client.get(f"/projects/proj/events?since={everything[0]['id']}").json()
    assert len(tail) == len(everything) - 1


def test_unknown_project_is_404(client):
    assert client.get("/projects/nope").status_code == 404


def test_unknown_artifact_is_404(client):
    assert client.get("/projects/proj/artifacts/requirements").status_code == 404


def test_missing_blob_is_410(client):
    from types import SimpleNamespace

    v = client.get("/projects/proj/artifacts/architecture").json()[0]
    ref_to_path(SimpleNamespace(uri=v["uri"])).unlink()
    r = client.get(f"/projects/proj/artifacts/architecture/versions/{v['id']}")
    assert r.status_code == 410
    assert r.json()["detail"]["sha256"] == v["sha256"]


def test_content_over_cap_is_truncated(tmp_path):
    from sdlc.board import api as api_mod

    db = tmp_path / "b2.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs2")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("p")
    _, vid = seed.publish_artifact_version(
        "p", "plan", "r", b"x" * (api_mod.MAX_CONTENT_BYTES + 10), actor="workflow:r"
    )
    seed.close()
    c = TestClient(create_app(lambda: BoardStore(db=db, blobs=blobs)))
    body = c.get(f"/projects/p/artifacts/plan/versions/{vid}").json()
    assert body["truncated"] is True
    assert len(body["content"]) == api_mod.MAX_CONTENT_BYTES
