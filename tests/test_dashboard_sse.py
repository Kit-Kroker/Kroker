"""SSE: emit on change, suppress identical snapshots, heartbeat when idle.

Driven at the ASGI message level rather than through TestClient: this
starlette's _TestClientTransport runs the app to completion and buffers
the whole body into one response, so client.stream() on an endless
event-stream hangs at context entry no matter how correct the endpoint
is (starlette/testclient.py: handle_request -> portal.call(self.app, ...)).
Reading the raw body messages keeps the three behaviors under test --
frame shape, dedupe, heartbeat -- without a real socket.
"""
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI

from sdlc.dashboard.api import create_router
from sdlc.dashboard.fleet import FleetSnapshot

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)

_SCOPE = {
    "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
    "http_version": "1.1", "method": "GET", "scheme": "http",
    "path": "/events", "raw_path": b"/events", "query_string": b"",
    "headers": [(b"host", b"testserver")], "client": ("testclient", 50000),
    "server": ("testserver", 80),
}


class _ScriptedPoller:
    """Yields a fixed list of snapshots to one subscriber, then idles."""

    def __init__(self, snaps):
        self._snaps = list(snaps)

    async def snapshot(self):
        return self._snaps[0]

    @contextlib.asynccontextmanager
    async def subscribe(self):
        q = asyncio.Queue()
        for s in self._snaps:
            q.put_nowait(s)
        yield q


async def _stream(snaps, stop):
    """Serve GET /events in-process, returning (content_type, lines) as
    decoded off the ASGI body messages until stop(line) fires."""
    app = FastAPI()
    app.include_router(create_router(_ScriptedPoller(snaps)))
    content_type = ""
    lines = []
    done = asyncio.Event()
    buf = ""
    request_seen = False

    async def receive():
        nonlocal request_seen
        if request_seen:
            # No client will ever disconnect mid-conversation here.
            await asyncio.Event().wait()
        request_seen = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal content_type, buf
        if message["type"] == "http.response.start":
            headers = dict(message.get("headers", []))
            content_type = headers[b"content-type"].decode()
        elif message["type"] == "http.response.body":
            buf += message.get("body", b"").decode()
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                lines.append(line)
                if stop(line):
                    done.set()
                    return

    task = asyncio.create_task(app(_SCOPE, receive, send))
    try:
        async with asyncio.timeout(5):
            await done.wait()
    except TimeoutError:
        pytest.fail("no matching frame within 5s")
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    return content_type, lines


async def _events(snaps, want: int):
    """Read `want` data: frames off the stream, then stop."""
    seen = 0

    def stop(line):
        nonlocal seen
        if line.startswith("data: "):
            seen += 1
        return seen >= want

    content_type, lines = await _stream(snaps, stop)
    assert content_type.startswith("text/event-stream")
    return [l[len("data: "):] for l in lines if l.startswith("data: ")]


@pytest.mark.asyncio
async def test_stream_emits_a_snapshot_as_a_data_frame():
    snap = FleetSnapshot(at=AT, total_open_runs=1)
    [frame] = await _events([snap], 1)
    assert FleetSnapshot.model_validate_json(frame).total_open_runs == 1


@pytest.mark.asyncio
async def test_stream_suppresses_a_snapshot_that_differs_only_by_its_clock():
    """The poller re-fans-out every interval; an unchanged fleet must not
    produce a frame just because `at` moved."""
    a = FleetSnapshot(at=AT, total_open_runs=1)
    same = FleetSnapshot(at=AT + timedelta(seconds=2), total_open_runs=1)
    changed = FleetSnapshot(at=AT + timedelta(seconds=4), total_open_runs=2)
    frames = await _events([a, same, changed], 2)
    assert [FleetSnapshot.model_validate_json(f).total_open_runs
            for f in frames] == [1, 2]


@pytest.mark.asyncio
async def test_stream_sends_a_heartbeat_comment_when_idle(monkeypatch):
    import sdlc.dashboard.api as mod
    monkeypatch.setattr(mod, "HEARTBEAT_S", 0.01)
    _, lines = await _stream([], lambda line: line.startswith(":"))
    assert "heartbeat" in lines[-1]
