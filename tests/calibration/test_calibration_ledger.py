"""C7: the durable ledger. Append-only, windowed, and fail-safe on read."""

import pytest

from sdlc.calibration.models import CalibrationSample, LabelSource
from sdlc.calibration.store import CalibrationLedger
from sdlc.calibration.verdict import MIN_SAMPLES, WINDOW, bucket_key

BK = bucket_key("some/model", LabelSource.PRODUCTION_PROXY)
OTHER = bucket_key("other/model", LabelSource.PRODUCTION_PROXY)


@pytest.fixture
def ledger(tmp_path):
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    yield led
    led.close()


def _sample(conf: float, label: float, bk: str = BK, gate: str = "architecture"):
    return CalibrationSample(
        gate=gate, bucket_key=bk, confidence=conf, outcome_label=label, run_id="r1"
    )


def test_append_then_read_round_trips_as_pairs(ledger):
    ledger.append([_sample(0.9, 0.8), _sample(0.7, 0.6)])
    assert sorted(ledger.recent("architecture", BK)) == [(0.7, 0.6), (0.9, 0.8)]


def test_an_empty_bucket_reads_empty(ledger):
    assert ledger.recent("architecture", BK) == []


def test_buckets_do_not_bleed_into_each_other(ledger):
    ledger.append([_sample(0.9, 0.9, bk=BK), _sample(0.1, 0.1, bk=OTHER)])
    assert ledger.recent("architecture", BK) == [(0.9, 0.9)]


def test_gates_do_not_bleed_into_each_other(ledger):
    ledger.append([_sample(0.9, 0.9, gate="architecture"), _sample(0.1, 0.1, gate="plan")])
    assert ledger.recent("plan", BK) == [(0.1, 0.1)]


def test_the_window_keeps_the_most_recent(ledger):
    """Ruling OQ5. The stale samples are retained in the table -- the WINDOW
    bounds what the verdict READS, so history stays auditable."""
    ledger.append([_sample(0.1, 0.1) for _ in range(WINDOW)])
    ledger.append([_sample(0.9, 0.9) for _ in range(5)])
    pairs = ledger.recent("architecture", BK, limit=WINDOW)
    assert len(pairs) == WINDOW
    assert pairs.count((0.9, 0.9)) == 5
    assert pairs.count((0.1, 0.1)) == WINDOW - 5


def test_appending_nothing_is_a_no_op(ledger):
    ledger.append([])
    assert ledger.recent("architecture", BK) == []


@pytest.mark.asyncio
async def test_verdict_activity_reads_the_ledger(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    led.append([_sample(0.9, 0.9) for _ in range(MIN_SAMPLES)])
    led.close()

    v = await activities.calibration_verdict(
        activities.VerdictInput(gate="architecture", bucket_key=BK)
    )
    assert v.verdict == "calibrated"
    assert v.n == MIN_SAMPLES


@pytest.mark.asyncio
async def test_verdict_activity_on_an_empty_ledger_is_insufficient(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    v = await activities.calibration_verdict(
        activities.VerdictInput(gate="architecture", bucket_key=BK)
    )
    assert v.verdict == "insufficient_data"


@pytest.mark.asyncio
async def test_record_activity_appends(tmp_path, monkeypatch):
    from sdlc.calibration import activities

    monkeypatch.setattr(activities, "_db_path", lambda: tmp_path / "board.sqlite3")
    await activities.record_calibration_samples(
        activities.RecordSamplesInput(samples=[_sample(0.9, 0.8)])
    )
    led = CalibrationLedger(db=tmp_path / "board.sqlite3")
    try:
        assert led.recent("architecture", BK) == [(0.9, 0.8)]
    finally:
        led.close()


def test_both_activities_are_registered_on_the_worker():
    """A workflow that awaits an unregistered activity hangs until timeout
    rather than failing loudly, so registration gets its own pin."""
    src = __import__("pathlib").Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "calibration_verdict" in src
    assert "record_calibration_samples" in src
