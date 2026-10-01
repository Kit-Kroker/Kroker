"""Priced-usage parity: live migrated run vs the frozen recording (T046).

FR-014 / SC-006a: the migration must not change any per-run spend figure.
Record checked: tests/replay/histories/greenfield_happy.json — the
greenfield_happy Feature scenario, captured live on pre-migration main and
replay-protected since (SG-2 family). This test runs the SAME scenario LIVE
under the migrated code (harness.capture: FeatureWorkflow +
DeploymentWorkflow on a real worker with the scenario's activities and
SdlcPydanticAIPlugin) and asserts the price_usage activity inputs decode to
identical (model, tokens) tuples in order — plus the same comparison for
every record_benchmark input's spend fields (role, model, cost bag).
"""

from __future__ import annotations

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter

from sdlc.benchmarks.models import BenchmarkRecord
from sdlc.pricing import PriceUsageInput
from tests.replay.harness import FEATURE_STARTER, capture, load_history
from tests.replay.scenarios import SCENARIOS

pytestmark = [pytest.mark.temporal]


def _scheduled_inputs(events, activity_name: str, model_type: type) -> list:
    """Decode the input payload of every ActivityTaskScheduled with the given
    activity type, in schedule order."""
    converter = pydantic_data_converter.payload_converter
    decoded: list = []
    for ev in events:
        if not ev.HasField("activity_task_scheduled_event_attributes"):
            continue
        attrs = ev.activity_task_scheduled_event_attributes
        if attrs.activity_type.name != activity_name:
            continue
        (value,) = converter.from_payloads(list(attrs.input.payloads), [model_type])
        decoded.append(value)
    return decoded


def _price_tuple(inp: PriceUsageInput) -> tuple:
    return (
        inp.model,
        inp.input_tokens,
        inp.output_tokens,
        inp.cache_read_tokens,
        inp.cache_write_tokens,
    )


def _spend(rec: BenchmarkRecord) -> tuple:
    """Record identity + spend fields only. Volatile fields (run ids,
    timestamps, durations, confidence floats) are deliberately excluded."""
    return (rec.role, rec.model, rec.cost.usd, rec.cost.input_tokens, rec.cost.output_tokens)


@pytest.mark.asyncio
async def test_live_priced_usage_matches_the_frozen_recording(monkeypatch, tmp_path):
    recorded = load_history("greenfield_happy")
    recorded_prices = [
        _price_tuple(p) for p in _scheduled_inputs(recorded.events, "price_usage", PriceUsageInput)
    ]
    assert recorded_prices, "frozen history carries no price_usage activities"

    scenario = next(s for s in SCENARIOS if s.name == "greenfield_happy")
    live = await capture(scenario, FEATURE_STARTER, monkeypatch, tmp_path)

    live_prices = [
        _price_tuple(p)
        for p in _scheduled_inputs(live.history.events, "price_usage", PriceUsageInput)
    ]
    assert live_prices == recorded_prices, "priced usage drifted from the recording"

    recorded_bench = [
        _spend(r) for r in _scheduled_inputs(recorded.events, "record_benchmark", BenchmarkRecord)
    ]
    live_bench = [
        _spend(r)
        for r in _scheduled_inputs(live.history.events, "record_benchmark", BenchmarkRecord)
    ]
    # greenfield_happy schedules no record_benchmark today (verified against
    # the frozen history — the comparison is vacuous until one appears, and
    # bites the moment the scenario starts recording benchmarks).
    assert live_bench == recorded_bench, "benchmark spend drifted from the recording"
