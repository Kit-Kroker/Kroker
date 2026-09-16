"""A SANDBOXED GraphWorkflow run ships end to end (E-74 §4.2 F1 residue: the
production sandbox, not the unsandboxed capture runner)."""

from __future__ import annotations

import pytest

from tests.replay.harness import GRAPH_STARTER, capture
from tests.replay.scenarios import SCENARIOS

pytestmark = pytest.mark.temporal
GREENFIELD = next(s for s in SCENARIOS if s.name == "greenfield_happy")


@pytest.mark.asyncio
async def test_sandboxed_graph_workflow_greenfield_deploys(monkeypatch, tmp_path):
    captured = await capture(GREENFIELD, GRAPH_STARTER, monkeypatch, tmp_path, sandboxed=True)
    assert captured.golden["close"].startswith("deployed:"), captured.golden["close"]
