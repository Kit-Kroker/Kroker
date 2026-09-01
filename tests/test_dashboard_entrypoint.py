"""D2: two routers, one process. The board's existing paths must not move --
any agent client hitting /projects/* keeps working."""

from interfaces.dashboard.api.main import app


def _paths():
    # FastAPI 0.141 keeps include_router() results as _IncludedRouter
    # wrappers in app.routes instead of flattening; expand them to the
    # effective (prefix-applied) routes the app actually serves.
    def walk(routes):
        for r in routes:
            expand = getattr(r, "effective_candidates", None)
            if expand is None:
                yield r.path
            else:
                yield from walk(expand())

    return set(walk(app.routes))


def test_board_routes_keep_their_existing_paths():
    assert "/projects" in _paths()
    assert "/projects/{project}/tasks" in _paths()


def test_dashboard_routes_are_served_under_api():
    p = _paths()
    assert "/api/runs" in p
    assert "/api/inbox" in p
    assert "/api/events" in p


def test_dashboard_write_routes_are_present():
    p = _paths()
    assert "/api/runs/{run_id}/answer" in p
    assert "/api/runs/{run_id}/decide" in p
