"""read_artifact: 32 KB budget, offset paging, no fishing, pruned blobs."""

import pytest

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board.store import BoardStore
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError

BIG = "x" * (80 * 1024)


@pytest.fixture
def board_factory(tmp_path):
    db = tmp_path / "board.db"
    blobs = tmp_path / "runs"

    def make():
        return BoardStore(db, blobs=LocalFileStore(root=blobs))

    seed = make()
    seed.ensure_project("kroker")
    seed.publish_artifact_version(
        "kroker",
        "spec",
        run_id="feature-x",
        content=BIG.encode("utf-8"),
        actor="workflow:feature-x",
    )
    seed.close()
    return make


@pytest.fixture
def deps(board_factory):
    return OperatorDeps(poller=None, board=board_factory, starter=None)


@pytest.mark.asyncio
async def test_first_page_is_capped_at_the_deps_budget(deps):
    got = await tools.read_artifact(deps, "kroker", "spec")
    assert len(got.content) == deps.max_artifact_bytes
    assert got.truncated is True
    assert got.next_offset == deps.max_artifact_bytes
    assert got.total_bytes == len(BIG)


@pytest.mark.asyncio
async def test_paging_reaches_the_end_and_stops(deps):
    offset, seen = 0, 0
    for _ in range(10):
        got = await tools.read_artifact(deps, "kroker", "spec", offset=offset)
        seen += len(got.content)
        if got.next_offset is None:
            break
        offset = got.next_offset
    assert seen == len(BIG)
    assert got.truncated is False


@pytest.mark.asyncio
async def test_a_small_artifact_is_not_marked_truncated(deps, board_factory):
    st = board_factory()
    try:
        st.publish_artifact_version(
            "kroker", "plan", run_id="feature-x", content=b"short", actor="workflow:feature-x"
        )
    finally:
        st.close()
    got = await tools.read_artifact(deps, "kroker", "plan")
    assert got.content == "short"
    assert got.truncated is False
    assert got.next_offset is None


@pytest.mark.asyncio
async def test_unknown_key_is_refused_and_points_at_get_project(deps):
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "invented")
    assert "get_project" in e.value.message


@pytest.mark.asyncio
async def test_offset_past_the_end_is_a_tool_error_not_an_empty_read(deps):
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "spec", offset=len(BIG) + 10)
    assert "offset" in e.value.message.lower()


@pytest.mark.asyncio
async def test_pruned_blob_reports_metadata_instead_of_crashing(deps, board_factory):
    st = board_factory()
    try:
        _, version_id = st.publish_artifact_version(
            "kroker", "arch", run_id="feature-x", content=b"temp", actor="workflow:feature-x"
        )
        v = st.get_version("kroker", version_id)
    finally:
        st.close()
    ref_to_path(v).unlink()
    with pytest.raises(ToolError) as e:
        await tools.read_artifact(deps, "kroker", "arch")
    assert "pruned" in e.value.message.lower()
    assert v.sha256 in e.value.message


@pytest.mark.asyncio
async def test_read_artifact_resets_the_follow_streak(deps):
    deps.note_follow()
    await tools.read_artifact(deps, "kroker", "spec")
    assert deps.follow_calls == 0
