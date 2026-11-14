# interfaces/dashboard/api/main.py
"""uvicorn entrypoint composing both operator HTTP surfaces (E-10 D2).

    uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500

Two routers, one process: the board serves durable cross-run state from
SQLite, the dashboard serves live run state from Temporal. They keep
separate factories -- all logic stays in sdlc.board.api and
sdlc.dashboard.api -- and are composed here so the frontend has one origin
and E-60 has one place to install identity.

Board paths are unchanged; anything already hitting /projects/* keeps
working. The dashboard mounts under /api.

Bound to localhost, unauthenticated, by design (spec D4 / OQ-11).
"""

import functools
import logging
import os

from sdlc.board.api import create_app
from sdlc.dashboard.api import create_router
from sdlc.observability.logfire_setup import configure as configure_logfire
from sdlc.operator import runtime
from sdlc.operator.agent import ChatConfigError, build_chat_app

log = logging.getLogger(__name__)

app = create_app()

poller = runtime.build_poller()

app.include_router(
    create_router(poller, starter=functools.partial(runtime.start_graph, poller)), prefix="/api"
)


def mount_chat(target, fleet_poller) -> bool:
    """Mount the operator chat surface at /chat when enabled (E-86).

    Opt-in and fail-soft, both deliberately. The dashboard is the surface
    operators depend on; it must never fail to boot because the chat agent
    has no API key, no assets, or a bad model id. Returns whether it mounted
    so the caller (and the tests) can tell.
    """
    if os.environ.get("SDLC_CHAT_ENABLED") != "1":
        return False
    try:
        # instrument_pydantic_ai() lives inside configure(); calling it here
        # is what gives the chat surface per-conversation traces beside the
        # pipeline's (spec 12). It is a no-op without a Logfire token.
        configure_logfire()
        # The deps shape (board as the BoardStore CLASS, starter via the
        # shared runtime seam) is composed by runtime.operator_deps; the
        # reasoning lives there and in tools._board.
        deps = runtime.operator_deps(fleet_poller, "chat:local")
        target.mount("/chat", build_chat_app(deps))
    except ChatConfigError as e:
        log.warning("chat surface not mounted: %s", e)
        return False
    except Exception as e:  # noqa: BLE001 -- never fatal to the dashboard
        log.warning("chat surface not mounted: %s: %s", type(e).__name__, e)
        return False
    log.info("chat surface mounted at /chat")
    return True


mount_chat(app, poller)


async def _shutdown() -> None:
    await poller.aclose()


app.router.add_event_handler("shutdown", _shutdown)


__all__ = ["app"]
