"""003 T007: capture the AssessmentWorkflow history from unchanged main.

Mirrors test_capture_feature.py for the assessment starter: the proposers
(discover, risk) run through their durable agent activities, so the frozen
history is the only captured evidence for those names (spec FR-005.5c).
Runs only with SDLC_CAPTURE_HISTORIES=1; SG-1 double-capture applies.
"""

from __future__ import annotations

import os

import pytest

from tests.replay.harness import ASSESSMENT_STARTER, capture, write_fixtures
from tests.replay.scenarios import ASSESSMENT_SCENARIOS

pytestmark = [
    pytest.mark.temporal,
    pytest.mark.skipif(
        os.environ.get("SDLC_CAPTURE_HISTORIES") != "1",
        reason="capture runs only on demand (003 T007)",
    ),
]


_ASSESSMENT_IDS = [s.name for s in ASSESSMENT_SCENARIOS]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ASSESSMENT_SCENARIOS, ids=_ASSESSMENT_IDS)
async def test_capture_assessment_scenario(scenario, monkeypatch, tmp_path):
    first = await capture(scenario, ASSESSMENT_STARTER, monkeypatch, tmp_path / "a")
    second = await capture(scenario, ASSESSMENT_STARTER, monkeypatch, tmp_path / "b")
    assert first.golden["commands"] == second.golden["commands"], "SG-1: unstable commands"
    assert first.golden["trace"] == second.golden["trace"], "SG-1: unstable trace"
    assert first.golden["close"] == second.golden["close"], "SG-1: unstable close"
    write_fixtures(scenario.name, first, ASSESSMENT_STARTER.name)
