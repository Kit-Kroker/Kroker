"""Task 2 oracle: movement reflection, per-cat history, the 24h window
relative to the cat's newest reading, and 404 on unknown ids."""
import pytest

from conftest import cat, cats, detail, feed, floorplan, post_reading

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


@pytest.mark.asyncio
async def test_latest_reading_wins_cat_position(client):
    """mon_movement: Task 2. Monitoring: Show in real time on the café floor plan: the movement of all cats."""
    await feed(client, "c-seq", [(0, 1.0, 1.0, 40), (5, 2.0, 2.0, 40), (10, 4.0, 5.0, 40)])
    row = await cat(client, "c-seq")
    assert (float(row["x"]), float(row["y"])) == (4.0, 5.0)


@pytest.mark.asyncio
async def test_two_cats_move_independently(client):
    """mon_movement: Task 2. Monitoring: Show in real time on the café floor plan: the movement of all cats."""
    await feed(client, "c-ind-a", [(0, 2.0, 3.0, 40)])
    await feed(client, "c-ind-b", [(0, 6.0, 7.0, 40)])
    row_a = await cat(client, "c-ind-a")
    row_b = await cat(client, "c-ind-b")
    assert (float(row_a["x"]), float(row_a["y"])) == (2.0, 3.0)
    assert (float(row_b["x"]), float(row_b["y"])) == (6.0, 7.0)


@pytest.mark.asyncio
async def test_floorplan_returns_200_and_zones_list(client):
    """mon_floorplan: Interface contract: GET /floorplan -> 200 {"zones": [{kind, x, y}, ...]}; richer zone shapes are allowed and all coordinates are your choice."""
    r = await floorplan(client)
    assert r.status_code == 200
    zones = r.json().get("zones")
    assert isinstance(zones, list) and len(zones) >= 4


@pytest.mark.asyncio
async def test_floorplan_coordinates_are_numbers(client):
    """mon_floorplan: Case text: The café floor plan includes the coordinates of rest areas, litter boxes, water bowls, and food bowls."""
    r = await floorplan(client)
    for z in r.json()["zones"]:
        assert isinstance(z["x"], (int, float))
        assert isinstance(z["y"], (int, float))


@pytest.mark.asyncio
async def test_floorplan_contains_all_four_zone_kinds(client):
    """mon_floorplan: Interface contract: with kind one of rest_area | litter_box | water_bowl | food_bowl."""
    r = await floorplan(client)
    kinds = {z["kind"] for z in r.json()["zones"]}
    assert {"rest_area", "litter_box", "water_bowl", "food_bowl"} <= kinds
    assert kinds <= {"rest_area", "litter_box", "water_bowl", "food_bowl"}


@pytest.mark.asyncio
async def test_cats_row_contains_all_five_fields(client):
    """mon_cats_shape: Interface contract: GET /cats -> 200 [{id, x, y, activity, at_risk}, ...]."""
    await feed(client, "c-shape", [(0, 1.0, 1.0, 40)])
    row = await cat(client, "c-shape")
    assert {"id", "x", "y", "activity", "at_risk"} <= set(row.keys())


@pytest.mark.asyncio
async def test_cats_row_at_risk_is_boolean(client):
    """mon_cats_shape: Interface contract: at_risk is a boolean."""
    await feed(client, "c-shape-bool", [(0, 1.0, 1.0, 40)])
    row = await cat(client, "c-shape-bool")
    assert isinstance(row["at_risk"], bool)


@pytest.mark.asyncio
async def test_detail_contains_latest_reading_fields(client):
    """mon_detail: Interface contract: GET /cats/{id} -> 200 detail with the latest reading and history: that cat's readings {timestamp, x, y, breathing_rate}."""
    await feed(client, "c-detail-fields", [(0, 2.5, 3.5, 42)])
    r = await detail(client, "c-detail-fields")
    assert r.status_code == 200
    data = r.json()
    candidates = []
    if isinstance(data, dict):
        candidates.append(data)
        if isinstance(data.get("latest"), dict):
            candidates.append(data["latest"])
        if isinstance(data.get("history"), list):
            candidates.extend([h for h in data["history"] if isinstance(h, dict)])
    matching = [
        c
        for c in candidates
        if (float(c.get("x", -1)), float(c.get("y", -1)), float(c.get("breathing_rate", -1)))
        == (2.5, 3.5, 42.0)
    ]
    assert matching, f"detail response {data} does not carry posted latest reading values"


@pytest.mark.asyncio
async def test_detail_history_is_isolated_to_that_cat(client):
    """mon_detail: Task 2. Monitoring: For each cat the user must also be able to see detailed sensor data and movement history for the last 24 hours."""
    await feed(client, "c-iso-a", [(0, 1.0, 1.0, 45)])
    await feed(client, "c-iso-b", [(0, 2.0, 2.0, 99)])
    r = await detail(client, "c-iso-a")
    assert r.status_code == 200
    rates = [float(h["breathing_rate"]) for h in r.json()["history"]]
    assert 99.0 not in rates


@pytest.mark.asyncio
async def test_history_window_includes_reading_inside_24h(client):
    """mon_history_window: Task 2. Monitoring: movement history for the last 24 hours."""
    await feed(client, "c-win-in", [(0, 1.0, 1.0, 31), (12 * H, 2.0, 2.0, 32), (23 * H, 3.0, 3.0, 33)])
    r = await detail(client, "c-win-in")
    rates = {float(h["breathing_rate"]) for h in r.json()["history"]}
    assert {31.0, 32.0, 33.0} <= rates


@pytest.mark.asyncio
async def test_history_window_is_relative_to_cat_newest_reading_not_other_cats(client):
    """mon_history_window: Interface contract: from the last 24 hours relative to the cat's newest reading (never the wall clock)."""
    await feed(client, "c-win-cat-a", [(0, 1.0, 1.0, 35)])
    await feed(client, "c-win-cat-b", [(50 * H, 2.0, 2.0, 45)])
    r = await detail(client, "c-win-cat-a")
    rates = {float(h["breathing_rate"]) for h in r.json()["history"]}
    assert 35.0 in rates


@pytest.mark.asyncio
async def test_telemetry_post_returns_2xx_and_begins_tracking(client):
    """telemetry_ingest: Interface contract: POST /telemetry {cat_id, x, y, breathing_rate, timestamp} -> 2xx; a reading for a new cat_id begins tracking that cat."""
    r = await post_reading(client, "c-ingest-new", 4.0, 4.0, 38)
    assert 200 <= r.status_code < 300
    assert (await cat(client, "c-ingest-new")) is not None


@pytest.mark.asyncio
async def test_telemetry_posted_reading_visible_in_detail_view(client):
    """telemetry_ingest: Interface contract: the reading is processed exactly as if a collar emitted it."""
    await post_reading(client, "c-ingest-det", 5.0, 6.0, 49)
    r = await detail(client, "c-ingest-det")
    assert r.status_code == 200
    rates = [float(h["breathing_rate"]) for h in r.json()["history"]]
    assert 49.0 in rates


@pytest.mark.asyncio
async def test_import_no_autostart_leaves_untracked_cats_static(client):
    """import_no_autostart: Interface contract: Importing app:app must not auto-start the random telemetry generator."""
    initial_rows = await cats(client)
    subsequent_rows = await cats(client)
    assert initial_rows == subsequent_rows
