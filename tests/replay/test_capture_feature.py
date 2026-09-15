"""E-74 Task 1: capture FeatureWorkflow histories + golden traces from unchanged main.

Runs only with SDLC_CAPTURE_HISTORIES=1. Capture-twice rule (spec §4.1): each
scenario runs twice and the fixtures are written only when both projections
agree. A disagreement is stop-guard SG-1 -- fix the scenario's fixture, never
the projection.
"""

from __future__ import annotations

import os

import pytest

from tests.replay.harness import FEATURE_STARTER, capture, write_fixtures
from tests.replay.scenarios import SCENARIOS

pytestmark = [
    pytest.mark.temporal,
    pytest.mark.skipif(
        os.environ.get("SDLC_CAPTURE_HISTORIES") != "1",
        reason="capture runs only on demand (E-74 Task 1)",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
async def test_capture_feature_scenario(scenario, monkeypatch, tmp_path):
    first = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path / "a")
    second = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path / "b")
    assert first.golden["commands"] == second.golden["commands"], "SG-1: unstable commands"
    assert first.golden["trace"] == second.golden["trace"], "SG-1: unstable trace"
    assert first.golden["close"] == second.golden["close"], "SG-1: unstable close"
    write_fixtures(scenario.name, first, FEATURE_STARTER.name)
