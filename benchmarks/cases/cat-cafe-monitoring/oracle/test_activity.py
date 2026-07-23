"""Task 1 oracle: activity detection at the app's own zone coordinates.
Extremes only — any reasonable ruleset passes (fairness rule, spec §4)."""
import pytest

from conftest import cat, far_from_zones, feed, stationary, zone


@pytest.mark.asyncio
async def test_stationary_at_food_bowl_is_eating(client):
    x, y = await zone(client, "food_bowl")
    await feed(client, "c-eat", stationary(x, y, bpm=40))
    assert (await cat(client, "c-eat"))["activity"] == "eating"


@pytest.mark.asyncio
async def test_stationary_at_water_bowl_is_drinking(client):
    x, y = await zone(client, "water_bowl")
    await feed(client, "c-drink", stationary(x, y, bpm=40))
    assert (await cat(client, "c-drink"))["activity"] == "drinking"


@pytest.mark.asyncio
async def test_resting_low_bpm_is_sleeping(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-sleep", stationary(x, y, bpm=20))
    assert (await cat(client, "c-sleep"))["activity"] == "sleeping"


@pytest.mark.asyncio
async def test_stationary_at_litter_box_is_litter_box(client):
    x, y = await zone(client, "litter_box")
    await feed(client, "c-litter", stationary(x, y, bpm=40))
    assert (await cat(client, "c-litter"))["activity"] == "litter_box"


@pytest.mark.asyncio
async def test_colocated_fast_high_bpm_is_playing_or_fighting(client):
    """Two cats circling each other away from every zone, fast, high bpm.
    playing vs fighting is genuinely ambiguous — either passes."""
    fx, fy = await far_from_zones(client)
    a = [(i * 5, fx + (1.5 if i % 2 else -1.5), fy, 90) for i in range(6)]
    b = [(i * 5, fx + (-1.5 if i % 2 else 1.5), fy + 0.5, 90)
         for i in range(6)]
    await feed(client, "c-rough1", a)
    await feed(client, "c-rough2", b)
    assert (await cat(client, "c-rough1"))["activity"] in (
        "playing", "fighting")
