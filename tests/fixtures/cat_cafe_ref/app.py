"""Reference implementation of the cat-cafe interface contract (spec §3).

Exists ONLY to exercise the held-out oracle in CI
(tests/test_cat_cafe_oracle.py). Never shipped to a worktree, never seen
by any run — it validates the oracle, it is not an answer key. Pure ASGI,
no framework, and no simulator at all (the contract forbids auto-starting
one on import; this module simply has none).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

RISK_ENABLED = True          # the broken-variant self-test flips this
ZONES = [
    {"kind": "rest_area", "x": 0.0, "y": 0.0},
    {"kind": "litter_box", "x": 10.0, "y": 0.0},
    {"kind": "water_bowl", "x": 0.0, "y": 10.0},
    {"kind": "food_bowl", "x": 10.0, "y": 10.0},
]
ZONE_RADIUS = 1.0            # "at" a zone = within this distance
NEAR_CAT = 5.0               # co-located cats = within this distance

_readings: dict[str, list[dict]] = {}


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _dist(ax, ay, bx, by) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _latest(cid: str) -> dict:
    return _readings[cid][-1]


def _history(cid: str) -> list[dict]:
    """Readings within 24h of this cat's newest reading (never wall clock)."""
    rs = sorted(_readings[cid], key=lambda r: _parse_ts(r["timestamp"]))
    lo = _parse_ts(rs[-1]["timestamp"]) - timedelta(hours=24)
    return [r for r in rs if _parse_ts(r["timestamp"]) >= lo]


def _speed(cid: str) -> float:
    rs = _history(cid)
    if len(rs) < 2:
        return 0.0
    a, b = rs[-2], rs[-1]
    dt = (_parse_ts(b["timestamp"]) - _parse_ts(a["timestamp"])).total_seconds()
    if dt <= 0:
        return 0.0
    return _dist(a["x"], a["y"], b["x"], b["y"]) / dt


def _activity(cid: str) -> str | None:
    latest = _latest(cid)
    x, y, bpm = latest["x"], latest["y"], latest["breathing_rate"]
    for z in ZONES:
        if _dist(x, y, z["x"], z["y"]) <= ZONE_RADIUS:
            if z["kind"] == "food_bowl":
                return "eating"
            if z["kind"] == "water_bowl":
                return "drinking"
            if z["kind"] == "litter_box":
                return "litter_box"
            return "sleeping" if bpm <= 30 else None   # rest_area
    for other in _readings:
        if other == cid:
            continue
        o = _latest(other)
        if (_dist(x, y, o["x"], o["y"]) <= NEAR_CAT
                and _speed(cid) > 0.2 and bpm >= 50):
            return "playing"
    return None


def _at_risk(cid: str) -> bool:
    if not RISK_ENABLED:
        return False
    bpm = _latest(cid)["breathing_rate"]
    return bpm > 60 or bpm < 10


async def _read_json(receive) -> dict:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    return json.loads(body or b"{}")


async def _send_json(send, status: int, payload) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body",
                "body": json.dumps(payload).encode()})


async def app(scope, receive, send):
    assert scope["type"] == "http"
    method, path = scope["method"], scope["path"]
    if method == "POST" and path == "/telemetry":
        r = await _read_json(receive)
        _readings.setdefault(str(r["cat_id"]), []).append({
            "timestamp": r["timestamp"], "x": float(r["x"]),
            "y": float(r["y"]),
            "breathing_rate": float(r["breathing_rate"])})
        return await _send_json(send, 202, {"ok": True})
    if method == "GET" and path == "/floorplan":
        return await _send_json(send, 200, {"zones": ZONES})
    if method == "GET" and path == "/cats":
        return await _send_json(send, 200, [
            {"id": cid, "x": _latest(cid)["x"], "y": _latest(cid)["y"],
             "activity": _activity(cid), "at_risk": _at_risk(cid)}
            for cid in _readings])
    if method == "GET" and path.startswith("/cats/"):
        cid = path[len("/cats/"):]
        if cid not in _readings:
            return await _send_json(send, 404, {"error": "unknown cat"})
        return await _send_json(send, 200, {
            "id": cid, "latest": _latest(cid), "history": _history(cid)})
    return await _send_json(send, 404, {"error": "not found"})
