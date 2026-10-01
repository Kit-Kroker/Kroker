"""Wire neutrality for no-override runs (004 T003, FR-010 / stop-guard SG-2).

A run with no proposer override must schedule the same activities, in the
same order, carrying the same model_request model ids as the Phase A
baseline. The fixture tests/durability/fixtures/wire_no_override.json is
FROZEN: this test loads it and never regenerates it. If it goes red, the
change under test altered the no-override wire — SG-2, stop and escalate;
do not refresh the fixture to get green.

Regeneration (baseline re-capture only, by the executor on an unmodified
base): SDLSC_WIRE_REGEN=1 pytest -m temporal tests/durability/test_wire_neutrality.py
"""

from __future__ import annotations

import os

import pytest

from . import wire_dump

pytestmark = [pytest.mark.temporal]


@pytest.mark.asyncio
async def test_no_override_wire_equals_the_frozen_baseline(monkeypatch, tmp_path):
    live = await wire_dump.capture_no_override_wire(monkeypatch, tmp_path)
    if os.environ.get(wire_dump.REGEN_ENV) == "1":
        wire_dump.write_fixture(live)

    frozen = wire_dump.load_fixture()

    assert live["activities"] == frozen["activities"], (
        "no-override run schedules different activities (or a different "
        "order) than the frozen baseline — SG-2: stop, escalate, do not "
        "regenerate the fixture"
    )
    assert live["model_requests"] == frozen["model_requests"], (
        "no-override run carries different model_request model ids than the "
        "frozen baseline — SG-2: stop, escalate, do not regenerate the fixture"
    )
    assert frozen["model_requests"], "the frozen baseline itself has no model requests"
    assert all(
        isinstance(entry["model_id"], str) and entry["model_id"]
        for entry in frozen["model_requests"]
    ), (
        "the frozen baseline carries a null/empty model_id — the model-id "
        "comparison is vacuous; re-capture from an unmodified base "
        "(SDLSC_WIRE_REGEN=1), never to silence a live-vs-frozen red"
    )
