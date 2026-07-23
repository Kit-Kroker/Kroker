"""Held-out oracle fixtures for cat-cafe-monitoring (E-34). Never seen by
the run: copied into the produced worktree only at grade time. Drives the
frozen ASGI contract (app:app) via httpx. Scenarios are crafted against
the app's OWN /floorplan coordinates, so no coordinate or threshold is
pinned and the kata's "rules are up to you" freedom survives (fairness
rule, spec §4). Deterministic: no sleeps, no randomness, no wall clock —
all timestamps derive from a fixed BASE."""
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest_asyncio

# The produced repo root is the parent of this oracle/ dir once copied in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client():
    import app as produced          # contract: module app.py exposes `app`
    transport = httpx.ASGITransport(app=produced.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://testserver") as c:
        yield c


async def zone(client, kind):
    """The app's own coordinates for the first zone of the given kind."""
    r = await client.get("/floorplan")
    assert r.status_code == 200
    zones = r.json()["zones"]
    match = [z for z in zones if z["kind"] == kind]
    assert match, f"floorplan exposes no {kind!r} zone"
    return float(match[0]["x"]), float(match[0]["y"])


async def far_from_zones(client):
    """A spot unambiguously outside every zone the app declared."""
    r = await client.get("/floorplan")
    zs = r.json()["zones"]
    m = max([abs(float(z["x"])) for z in zs]
            + [abs(float(z["y"])) for z in zs])
    return m + 100.0, m + 100.0


async def feed(client, cat_id, readings):
    """POST a timestamped sequence; readings = [(offset_s, x, y, bpm)]."""
    for off, x, y, bpm in readings:
        ts = (BASE + timedelta(seconds=off)).isoformat()
        r = await client.post("/telemetry", json={
            "cat_id": cat_id, "x": x, "y": y,
            "breathing_rate": bpm, "timestamp": ts})
        assert 200 <= r.status_code < 300


async def cat(client, cat_id):
    """The cat's row from GET /cats."""
    r = await client.get("/cats")
    assert r.status_code == 200
    rows = [c for c in r.json() if str(c["id"]) == str(cat_id)]
    assert rows, f"cat {cat_id!r} not tracked"
    return rows[0]


def stationary(x, y, bpm, n=5, step=5):
    """n readings step seconds apart, not moving (collar cadence is 5s)."""
    return [(i * step, x, y, bpm) for i in range(n)]
