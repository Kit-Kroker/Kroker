"""Reference solution for cat-cafe-monitoring (T012, Phase 8).

Implements the frozen ASGI contract:
- Exposes `app:app`
- GET /floorplan
- POST /telemetry
- GET /cats
- GET /cats/{id}
- No autostart on import; simulation runs only when invoked as python app.py.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Cat Cafe Monitoring Reference")

# Café floor plan zones
ZONES = [
    {"kind": "rest_area", "x": 10.0, "y": 10.0},
    {"kind": "litter_box", "x": 20.0, "y": 20.0},
    {"kind": "water_bowl", "x": 30.0, "y": 30.0},
    {"kind": "food_bowl", "x": 40.0, "y": 40.0},
]

ZONE_RADIUS = 3.0

# In-memory telemetry storage: cat_id -> list of reading dicts
CAT_DATA: dict[str, list[dict]] = {}


def _parse_iso(ts_str: str) -> datetime:
    s = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _detect_activity(cat_id: str, latest: dict) -> str | None:
    x = float(latest["x"])
    y = float(latest["y"])
    bpm = float(latest["breathing_rate"])

    for z in ZONES:
        dist = math.hypot(x - z["x"], y - z["y"])
        if dist <= ZONE_RADIUS:
            kind = z["kind"]
            if kind == "food_bowl":
                return "eating"
            if kind == "water_bowl":
                return "drinking"
            if kind == "litter_box":
                return "litter_box"
            if kind == "rest_area":
                if bpm <= 30.0:
                    return "sleeping"
                return None

    # Away from zones: playing or fighting if colocated, fast, high bpm
    if bpm >= 70.0:
        for other_id, other_readings in CAT_DATA.items():
            if other_id == cat_id or not other_readings:
                continue
            other_latest = max(other_readings, key=lambda r: _parse_iso(r["timestamp"]))
            other_dist_to_zones = min(
                math.hypot(other_latest["x"] - z["x"], other_latest["y"] - z["y"]) for z in ZONES
            )
            if other_dist_to_zones > ZONE_RADIUS:
                cat_dist = math.hypot(x - other_latest["x"], y - other_latest["y"])
                if cat_dist <= 5.0:
                    return "playing"

    return None


def _compute_risk(readings: list[dict]) -> bool:
    if not readings:
        return False
    recent = readings[-5:]
    avg_bpm = sum(float(r["breathing_rate"]) for r in recent) / len(recent)
    return bool(avg_bpm >= 100.0 or avg_bpm <= 10.0)


@app.post("/telemetry", status_code=200)
async def post_telemetry(payload: dict) -> dict:
    cat_id = str(payload["cat_id"])
    reading = {
        "cat_id": cat_id,
        "x": float(payload["x"]),
        "y": float(payload["y"]),
        "breathing_rate": float(payload["breathing_rate"]),
        "timestamp": str(payload["timestamp"]),
    }
    CAT_DATA.setdefault(cat_id, []).append(reading)
    return {"status": "ok"}


@app.get("/floorplan")
async def get_floorplan() -> dict:
    return {"zones": ZONES}


@app.get("/cats")
async def get_cats() -> list[dict]:
    result = []
    for cat_id, readings in CAT_DATA.items():
        if not readings:
            continue
        latest = max(readings, key=lambda r: _parse_iso(r["timestamp"]))
        activity = _detect_activity(cat_id, latest)
        at_risk = _compute_risk(readings)
        result.append(
            {
                "id": cat_id,
                "x": latest["x"],
                "y": latest["y"],
                "activity": activity,
                "at_risk": at_risk,
            }
        )
    return result


@app.get("/cats/{cat_id}")
async def get_cat_detail(cat_id: str) -> dict:
    if cat_id not in CAT_DATA or not CAT_DATA[cat_id]:
        raise HTTPException(status_code=404, detail="Unknown cat")
    readings = CAT_DATA[cat_id]
    newest = max(readings, key=lambda r: _parse_iso(r["timestamp"]))
    newest_dt = _parse_iso(newest["timestamp"])
    cutoff = newest_dt - timedelta(hours=24)
    history = [
        {
            "timestamp": r["timestamp"],
            "x": r["x"],
            "y": r["y"],
            "breathing_rate": r["breathing_rate"],
        }
        for r in readings
        if _parse_iso(r["timestamp"]) >= cutoff
    ]
    return {
        "id": cat_id,
        "latest": {
            "timestamp": newest["timestamp"],
            "x": newest["x"],
            "y": newest["y"],
            "breathing_rate": newest["breathing_rate"],
        },
        "history": history,
    }


if __name__ == "__main__":
    import random
    import threading
    import time

    import uvicorn

    def _run_generator() -> None:
        cat_ids = [f"cat-{i}" for i in range(1, 11)]
        while True:
            time.sleep(5)
            now_iso = datetime.now(timezone.utc).isoformat()
            for cid in cat_ids:
                x = random.uniform(0.0, 50.0)
                y = random.uniform(0.0, 50.0)
                bpm = random.uniform(15.0, 45.0)
                CAT_DATA.setdefault(cid, []).append(
                    {
                        "cat_id": cid,
                        "x": x,
                        "y": y,
                        "breathing_rate": bpm,
                        "timestamp": now_iso,
                    }
                )

    gen_thread = threading.Thread(target=_run_generator, daemon=True)
    gen_thread.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
