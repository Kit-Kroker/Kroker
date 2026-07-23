"""Task 2 oracle: movement reflection, per-cat history, the 24h window
relative to the cat's newest reading, and 404 on unknown ids."""
import pytest

from conftest import cat, feed

H = 3600


@pytest.mark.asyncio
async def test_post_moves_cat_on_cats_view(client):
    await feed(client, "c-move", [(0, 1.0, 1.0, 40), (5, 3.0, 4.0, 40)])
    row = await cat(client, "c-move")
    assert (float(row["x"]), float(row["y"])) == (3.0, 4.0)


@pytest.mark.asyncio
async def test_history_contains_injected_readings(client):
    await feed(client, "c-hist", [(0, 1.0, 2.0, 40), (5, 1.5, 2.0, 41)])
    r = await client.get("/cats/c-hist")
    assert r.status_code == 200
    hist = r.json()["history"]
    assert len(hist) >= 2
    rates = {float(h["breathing_rate"]) for h in hist}
    assert {40.0, 41.0} <= rates


@pytest.mark.asyncio
async def test_history_window_is_24h_from_newest_reading(client):
    await feed(client, "c-old", [
        (0, 1.0, 1.0, 30),           # 25h before newest -> outside window
        (25 * H, 2.0, 2.0, 44),      # newest reading
        (2 * H, 1.5, 1.5, 33),       # 23h before newest -> inside window
    ])
    r = await client.get("/cats/c-old")
    assert r.status_code == 200
    rates = [float(h["breathing_rate"]) for h in r.json()["history"]]
    assert 30.0 not in rates, "reading older than 24h leaked into history"
    assert 33.0 in rates and 44.0 in rates


@pytest.mark.asyncio
async def test_unknown_cat_is_404(client):
    r = await client.get("/cats/no-such-cat")
    assert r.status_code == 404
