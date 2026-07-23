"""Task 2 oracle: life/health risk flag. Extremes only — the research-
grounded floor was >35 bpm at rest, so sustained 180 is unambiguous risk,
~5 bpm is unambiguous risk, and 25 bpm resting is unambiguously normal."""
import pytest

from conftest import cat, feed, stationary, zone


@pytest.mark.asyncio
async def test_sustained_180_bpm_at_rest_is_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-tachy", stationary(x, y, bpm=180))
    assert (await cat(client, "c-tachy"))["at_risk"] is True


@pytest.mark.asyncio
async def test_sustained_5_bpm_is_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-brady", stationary(x, y, bpm=5))
    assert (await cat(client, "c-brady"))["at_risk"] is True


@pytest.mark.asyncio
async def test_calm_resting_cat_is_not_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-calm", stationary(x, y, bpm=25))
    assert (await cat(client, "c-calm"))["at_risk"] is False
