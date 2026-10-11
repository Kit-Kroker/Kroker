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


@pytest.mark.asyncio
async def test_risk_is_independent_per_cat(client):
    """risk_flag: Task 2. Monitoring: and a risk analysis for each cat's life or health based on collar data."""
    x, y = await zone(client, "rest_area")
    await feed(client, "c-tachy-pair", stationary(x, y, bpm=180))
    await feed(client, "c-calm-pair", stationary(x, y, bpm=25))
    assert (await cat(client, "c-tachy-pair"))["at_risk"] is True
    assert (await cat(client, "c-calm-pair"))["at_risk"] is False


@pytest.mark.asyncio
async def test_single_reading_cat_has_boolean_at_risk(client):
    """risk_flag: Task 2. Monitoring: Cats with a detected life or health risk must be marked in red."""
    await feed(client, "c-single-risk", [(0, 1.0, 1.0, 40)])
    row = await cat(client, "c-single-risk")
    assert isinstance(row["at_risk"], bool)
