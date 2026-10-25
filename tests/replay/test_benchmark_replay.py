"""017 T002: BenchmarkWorkflow replays the single-cell graded execution (D-6)."""

from __future__ import annotations

import pytest

from sdlc.benchmarks.workflow import BenchmarkWorkflow
from tests.replay.harness import load_history
from tests.replay.test_feature_replay import replayer

pytestmark = pytest.mark.temporal


@pytest.mark.asyncio
async def test_benchmark_workflow_replays_one_cell_history():
    result = await replayer(BenchmarkWorkflow).replay_workflow(
        load_history("benchmark_one_cell"), raise_on_replay_failure=True
    )
    assert result.replay_failure is None
