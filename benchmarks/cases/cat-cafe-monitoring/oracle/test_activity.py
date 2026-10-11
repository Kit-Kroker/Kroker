"""Task 1 oracle: activity detection at the app's own zone coordinates.
Extremes only — any reasonable ruleset passes (fairness rule, spec §4)."""
import pytest

from conftest import cat, cats, far_from_zones, feed, stationary, zone


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


@pytest.mark.asyncio
async def test_two_cats_different_zones_one_eating(client):
    """act_eating: Task 1. Activity Detection: Detect the current activity of each cat from collar telemetry and distance to café zones: eating."""
    fx, fy = await zone(client, "food_bowl")
    wx, wy = await zone(client, "water_bowl")
    await feed(client, "c-eat-2", stationary(fx, fy, bpm=40))
    await feed(client, "c-drink-comp", stationary(wx, wy, bpm=40))
    assert (await cat(client, "c-eat-2"))["activity"] == "eating"


@pytest.mark.asyncio
async def test_two_cats_different_zones_one_drinking(client):
    """act_drinking: Task 1. Activity Detection: Detect the current activity of each cat from collar telemetry and distance to café zones: drinking."""
    fx, fy = await zone(client, "food_bowl")
    wx, wy = await zone(client, "water_bowl")
    await feed(client, "c-eat-comp", stationary(fx, fy, bpm=40))
    await feed(client, "c-drink-2", stationary(wx, wy, bpm=40))
    assert (await cat(client, "c-drink-2"))["activity"] == "drinking"


@pytest.mark.asyncio
async def test_two_cats_different_zones_one_sleeping(client):
    """act_sleeping: Task 1. Activity Detection: Detect the current activity of each cat from collar telemetry and distance to café zones: sleeping."""
    rx, ry = await zone(client, "rest_area")
    lx, ly = await zone(client, "litter_box")
    await feed(client, "c-sleep-2", stationary(rx, ry, bpm=20))
    await feed(client, "c-litter-comp", stationary(lx, ly, bpm=40))
    assert (await cat(client, "c-sleep-2"))["activity"] == "sleeping"


@pytest.mark.asyncio
async def test_two_cats_different_zones_one_litter_box(client):
    """act_litter_box: Task 1. Activity Detection: Detect the current activity of each cat from collar telemetry and distance to café zones: using the litter box."""
    rx, ry = await zone(client, "rest_area")
    lx, ly = await zone(client, "litter_box")
    await feed(client, "c-sleep-comp", stationary(rx, ry, bpm=20))
    await feed(client, "c-litter-2", stationary(lx, ly, bpm=40))
    assert (await cat(client, "c-litter-2"))["activity"] == "litter_box"


@pytest.mark.asyncio
async def test_second_cat_in_colocated_pair_is_playing_or_fighting(client):
    """act_playing_fighting: Task 1. Activity Detection: The detectable activities are: sleeping, eating, drinking, using the litter box, playing, and fighting."""
    fx, fy = await far_from_zones(client)
    a = [(i * 5, fx + (1.5 if i % 2 else -1.5), fy, 90) for i in range(6)]
    b = [(i * 5, fx + (-1.5 if i % 2 else 1.5), fy + 0.5, 90) for i in range(6)]
    await feed(client, "c-pair-a", a)
    await feed(client, "c-pair-b", b)
    assert (await cat(client, "c-pair-b"))["activity"] in ("playing", "fighting")


@pytest.mark.asyncio
async def test_colocated_fast_high_bpm_pair_at_offset_is_playing_or_fighting(client):
    """act_playing_fighting: Task 1. Activity Detection: Detect the current activity of each cat from collar telemetry and distance to café zones: playing and fighting."""
    fx, fy = await far_from_zones(client)
    a = [(i * 5 + 100, fx + 10.0 + (1.5 if i % 2 else -1.5), fy + 10.0, 95) for i in range(6)]
    b = [(i * 5 + 100, fx + 10.0 + (-1.5 if i % 2 else 1.5), fy + 10.5, 95) for i in range(6)]
    await feed(client, "c-pair-c", a)
    await feed(client, "c-pair-d", b)
    assert (await cat(client, "c-pair-c"))["activity"] in ("playing", "fighting")


@pytest.mark.asyncio
async def test_lone_cat_away_from_zones_has_vocabulary_activity(client):
    """act_vocabulary: Interface contract: activity is one of sleeping | eating | drinking | litter_box | playing | fighting, or null when undetermined."""
    fx, fy = await far_from_zones(client)
    await feed(client, "c-lone-vocab", [(0, fx, fy, 40)])
    allowed = {"sleeping", "eating", "drinking", "litter_box", "playing", "fighting", None}
    assert (await cat(client, "c-lone-vocab"))["activity"] in allowed


@pytest.mark.asyncio
async def test_all_tracked_cats_have_vocabulary_activity(client):
    """act_vocabulary: Interface contract: activity is one of sleeping | eating | drinking | litter_box | playing | fighting, or null when undetermined."""
    all_rows = await cats(client)
    allowed = {"sleeping", "eating", "drinking", "litter_box", "playing", "fighting", None}
    for row in all_rows:
        assert row["activity"] in allowed
