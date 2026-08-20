"""Board read verbs against a real BoardStore on a temp sqlite file."""
import pytest

from sdlc.board.store import BoardStore
from sdlc.operator import tools
from sdlc.operator.deps import OperatorDeps
from sdlc.operator.errors import ToolError


@pytest.fixture
def board_factory(tmp_path):
    """A zero-arg factory, matching production: tools._board opens and closes
    a store per call inside its worker thread, because a sqlite connection
    belongs to the thread that opened it."""
    db = tmp_path / "board.db"
    seed = BoardStore(db)
    seed.ensure_project("kroker", repo="git@example.com:kroker.git")
    seed.close()
    return lambda: BoardStore(db)


@pytest.fixture
def deps(board_factory):
    return OperatorDeps(poller=None, board=board_factory, starter=None)


@pytest.mark.asyncio
async def test_list_projects_names_key_and_repo(deps):
    out = await tools.list_projects(deps)
    assert "kroker" in out
    assert "example.com" in out


@pytest.mark.asyncio
async def test_list_projects_empty_is_explicit(tmp_path):
    db = tmp_path / "empty.db"
    out = await tools.list_projects(
        OperatorDeps(poller=None, board=lambda: BoardStore(db), starter=None))
    assert "no projects" in out.lower()


@pytest.mark.asyncio
async def test_a_bare_store_instead_of_a_factory_is_refused_clearly(tmp_path):
    """The failure mode this factory contract exists to prevent is a sqlite
    connection crossing threads, which surfaces as an obscure
    ProgrammingError. Refuse it up front instead."""
    store = BoardStore(tmp_path / "board.db")
    try:
        with pytest.raises(ToolError) as e:
            await tools.list_projects(
                OperatorDeps(poller=None, board=store, starter=None))
        assert "callable" in e.value.message
    finally:
        store.close()


@pytest.mark.asyncio
async def test_get_project_lists_artifact_keys_so_read_artifact_has_a_source(
        deps):
    out = await tools.get_project(deps, "kroker")
    assert "kroker" in out


@pytest.mark.asyncio
async def test_get_project_unknown_is_a_tool_error(deps):
    with pytest.raises(ToolError) as e:
        await tools.get_project(deps, "nope")
    assert "nope" in e.value.message


@pytest.mark.asyncio
async def test_list_tasks_without_a_plan_says_so_instead_of_raising_typeerror(
        deps):
    with pytest.raises(ToolError) as e:
        await tools.list_tasks(deps, "kroker")
    assert "plan" in e.value.message.lower()


@pytest.mark.asyncio
async def test_list_tasks_rejects_an_unknown_status(deps):
    with pytest.raises(ToolError) as e:
        await tools.list_tasks(deps, "kroker", plan_version=1,
                               status="sideways")
    assert "sideways" in e.value.message


@pytest.mark.asyncio
async def test_project_events_empty_is_explicit(deps):
    out = await tools.project_events(deps, "kroker")
    assert "no events" in out.lower()


@pytest.mark.asyncio
async def test_board_reads_reset_the_follow_streak(deps):
    deps.note_follow()
    await tools.list_projects(deps)
    assert deps.follow_calls == 0
