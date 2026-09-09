"""Board Markdown routes (F4): status mapping, headers, caching."""

import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board import api as api_mod
from sdlc.board.api import create_app
from sdlc.board.models import ArtifactStatus
from sdlc.board.store import BoardStore
from sdlc.stages.clarify.models import ClarifiedRequirements

MD = "text/markdown"


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj", repo="git@example:acme/x")

    good = ClarifiedRequirements(
        summary="a readable summary",
        functional_requirements=["it works"],
        non_functional_requirements=[],
        out_of_scope=[],
        open_questions=[],
    )
    # ORDER MATTERS. Publishing CURRENT moves the pointer, so the junk
    # version of `requirements` is seeded FIRST and the good one second --
    # that leaves v2 (good) current, while junk_v stays reachable by version
    # id for the 422 test. Seed them the other way round and
    # test_current_markdown_serves_a_document breaks.
    #
    # b"xxxx" is not JSON at all: it reaches the same ValidationError handler
    # as schema drift by a different failure class, which is why the spec
    # lists both.
    _, junk_v = seed.publish_artifact_version(
        "proj", "requirements", "run-1", b"xxxx", actor="workflow:run-1"
    )
    _, req_v = seed.publish_artifact_version(
        "proj",
        "requirements",
        "run-1",
        good.model_dump_json().encode("utf-8"),
        actor="workflow:run-1",
    )
    # Deliberately invalid: ArchitectureSpec requires `decisions`. Mirrors
    # the seed in tests/test_board_api_reads.py:21.
    _, arch_v = seed.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"first"}', actor="workflow:run-1"
    )
    _, big_v = seed.publish_artifact_version(
        "proj",
        "plan",
        "run-1",
        b"x" * (api_mod.MAX_CONTENT_BYTES + 10),
        actor="workflow:run-1",
    )
    # A rejected gate writes history without moving the pointer
    # (workflows/board_host.py:52-53), leaving current_version NULL. This is
    # the only way to reach the "has versions but none current" branch.
    seed.publish_artifact_version(
        "proj",
        "rejected_key",
        "run-1",
        b"{}",
        status=ArtifactStatus.REJECTED,
        actor="workflow:run-1",
    )
    seed.close()

    app = create_app(lambda: BoardStore(db=db, blobs=blobs))
    c = TestClient(app)
    c.req_v, c.arch_v, c.big_v, c.junk_v = req_v, arch_v, big_v, junk_v
    c.blobs = blobs
    c.db = db
    return c


def md_url(key: str, version_id: int | None = None) -> str:
    base = f"/projects/proj/artifacts/{key}"
    return f"{base}/versions/{version_id}/markdown" if version_id else f"{base}/current/markdown"


def test_current_markdown_serves_a_document(client):
    r = client.get(md_url("requirements"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(MD)
    assert r.text.startswith("# Requirements -- proj")
    assert "a readable summary" in r.text


def test_versioned_markdown_serves_the_same_document(client):
    r = client.get(md_url("requirements", client.req_v))
    assert r.status_code == 200
    assert "a readable summary" in r.text


def test_content_disposition_names_the_file(client):
    r = client.get(md_url("requirements"))
    # v2, not v1: the junk version is seeded first (see the ORDER MATTERS
    # note above), so the good -- and current -- version is n=2.
    assert 'filename="proj-requirements-v2.md"' in r.headers["content-disposition"]


def test_unknown_key_is_404(client):
    r = client.get(md_url("nonsense"))
    assert r.status_code == 404


def test_key_with_versions_but_no_current_is_404_and_says_why(client):
    r = client.get("/projects/proj/artifacts/rejected_key/current/markdown")
    assert r.status_code == 404
    assert "no current version" in r.text.lower()
    assert "rejected" in r.text.lower()


def test_unknown_project_is_404(client):
    r = client.get("/projects/ghost/artifacts/requirements/current/markdown")
    assert r.status_code == 404


def test_schema_drift_is_422_and_names_the_escape_hatch(client):
    r = client.get(md_url("architecture", client.arch_v))
    assert r.status_code == 422
    assert "ArchitectureSpec" in r.text
    assert "/versions/" in r.text  # points at the raw-JSON route


@pytest.mark.parametrize(
    "url",
    [
        "/projects/proj/artifacts/nonsense/current/markdown",
        "/projects/ghost/artifacts/requirements/current/markdown",
    ],
)
def test_errors_are_markdown_not_json(client, url):
    # The whole point of these routes is that a non-engineer never meets raw
    # JSON. A failed link must not hand them {"detail": ...}.
    r = client.get(url)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith(MD)
    assert r.text.startswith("# ")
    assert "detail" not in r.text


def test_unparseable_bytes_are_422_at_the_route(client):
    # Distinct from schema drift: these bytes are not JSON at all. The spec
    # lists both because the one-step model_validate_json parse is what
    # collapses them into the same handler -- it deserves a route-level pin,
    # not only a unit test.
    r = client.get(md_url("requirements", client.junk_v))
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(MD)


def test_oversize_blob_is_413(client):
    r = client.get(md_url("plan", client.big_v))
    assert r.status_code == 413


def test_pruned_blob_is_410(client):
    st = BoardStore(db=client.db, blobs=client.blobs)
    v = st.get_version("proj", client.req_v)
    st.close()
    ref_to_path(v).unlink()
    r = client.get(md_url("requirements", client.req_v))
    assert r.status_code == 410


def test_version_belonging_to_another_key_is_404(client):
    r = client.get(md_url("requirements", client.arch_v))
    assert r.status_code == 404


def test_etag_and_cache_control_are_set(client):
    r = client.get(md_url("requirements"))
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["etag"].startswith('W/"')


def test_matching_if_none_match_returns_304_with_no_body(client):
    first = client.get(md_url("requirements"))
    again = client.get(md_url("requirements"), headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.text == ""


def test_non_matching_if_none_match_returns_the_document(client):
    r = client.get(md_url("requirements"), headers={"If-None-Match": 'W/"stale"'})
    assert r.status_code == 200
    assert "a readable summary" in r.text
