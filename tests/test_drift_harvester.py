import asyncio
from datetime import datetime

from sdlc.benchmarks.drift import DriftHarvester


class FakeHistory:
    """Yields a canned list of (run_id, events) tuples."""
    def __init__(self, runs):
        self._runs = runs

    async def list_completed(self, hours):
        return [(rid, evs) for rid, evs in self._runs]

    async def fetch_history(self, run_id):
        return dict(self._runs)[run_id]


def _harness_result_event(cost=0.42, exit_code=0):
    # one activity-completed event whose result is a HarnessRunResult-ish dict
    return {
        "event_type": "ActivityTaskCompleted",
        "activity": "run_coding_task",
        "result": {"harness": "claude_code", "exit_code": exit_code,
                   "cost_usd": cost, "summary": "", "input_tokens": 100,
                   "output_tokens": 20, "context_window": 200000,
                   "compacted": False},
        "timestamp": datetime(2026, 7, 4, 10, 0, 30),
    }


def test_drift_emits_records_from_history(tmp_path):
    runs = [("feature-1", [_harness_result_event(cost=0.42)])]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path),
                       bench_run_id="_drift/2026-07-04")
    n = asyncio.run(h.harvest_since(hours=24))
    assert n == 1
    from sdlc.benchmarks.recorder import RecordStore
    store = RecordStore(root=str(tmp_path),
                        bench_run_id="_drift/2026-07-04", cell_id=None)
    recs = store.read_all()
    assert len(recs) == 1
    assert recs[0].case_id == "_production"
    assert recs[0].cost.usd == 0.42
    # Regression: bench_run_id must round-trip verbatim — do NOT derive it
    # from the store's path parent (which collapses '_drift/2026-07-04' to
    # just '2026-07-04').
    assert recs[0].bench_run_id == "_drift/2026-07-04"


def test_drift_skips_run_with_no_relevant_events(tmp_path):
    runs = [("feature-2", [{"event_type": "WorkflowStarted"}])]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path),
                       bench_run_id="_drift/2026-07-04")
    n = asyncio.run(h.harvest_since(hours=24))
    assert n == 0


def test_drift_skips_malformed_event_without_crashing(tmp_path):
    runs = [("feature-3", [_harness_result_event(),
                           {"event_type": "ActivityTaskCompleted",
                            "activity": "run_coding_task",
                            "result": "not-a-dict"}])]
    h = DriftHarvester(FakeHistory(runs), root=str(tmp_path),
                       bench_run_id="_drift/2026-07-04")
    n = asyncio.run(h.harvest_since(hours=24))
    # the malformed one is skipped, the well-formed one is kept
    assert n == 1


def test_drift_skips_run_whose_history_fetch_raises(tmp_path):
    class BrokenFetch(FakeHistory):
        async def fetch_history(self, run_id):
            raise RuntimeError("temporal unavailable")
    runs = [("feature-4", [_harness_result_event()])]
    h = DriftHarvester(BrokenFetch(runs), root=str(tmp_path),
                       bench_run_id="_drift/2026-07-04")
    # must not raise — the harvest continues past the broken fetch
    n = asyncio.run(h.harvest_since(hours=24))
    assert n == 0
