"""FleetPoller: lazy start, grace-period stop, and a REST read whose
correctness never depends on the poller being up (spec D6)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from sdlc.dashboard.fleet import FleetPoller, FleetSnapshot

AT = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)


class _Clock:
    def __init__(self):
        self.t = AT

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += timedelta(seconds=seconds)


def _poller(clock=None, **kw):
    clock = clock or _Clock()
    calls = []

    async def fake_fetch(client, *, now, closed_limit=20):
        calls.append(now)
        return FleetSnapshot(at=now, total_open_runs=len(calls))

    p = FleetPoller(lambda: None, clock=clock, fetch=fake_fetch,
                    interval=kw.pop("interval", 0.01),
                    grace_s=kw.pop("grace_s", 0.05))
    p.calls = calls
    return p


@pytest.mark.asyncio
async def test_snapshot_fans_out_inline_when_there_is_no_cached_snapshot():
    p = _poller()
    snap = await p.snapshot()
    assert snap.total_open_runs == 1
    assert len(p.calls) == 1


@pytest.mark.asyncio
async def test_snapshot_reuses_a_fresh_cached_snapshot():
    clock = _Clock()
    p = _poller(clock)
    await p.snapshot()
    await p.snapshot()
    assert len(p.calls) == 1


@pytest.mark.asyncio
async def test_snapshot_refetches_a_stale_snapshot():
    """Older than 2 x interval is stale, so REST correctness never depends
    on the poller running."""
    clock = _Clock()
    p = _poller(clock, interval=1.0)
    await p.snapshot()
    clock.advance(3.0)
    await p.snapshot()
    assert len(p.calls) == 2


@pytest.mark.asyncio
async def test_poller_is_not_running_before_anyone_subscribes():
    p = _poller()
    assert p.running is False


@pytest.mark.asyncio
async def test_subscribing_starts_the_poller_and_delivers_snapshots():
    p = _poller()
    async with p.subscribe() as q:
        assert p.running is True
        snap = await asyncio.wait_for(q.get(), timeout=2)
        assert isinstance(snap, FleetSnapshot)


@pytest.mark.asyncio
async def test_poller_stops_after_the_grace_period_once_all_unsubscribe():
    p = _poller(grace_s=0.02)
    async with p.subscribe() as q:
        await asyncio.wait_for(q.get(), timeout=2)
    for _ in range(100):
        if not p.running:
            break
        await asyncio.sleep(0.01)
    assert p.running is False


@pytest.mark.asyncio
async def test_a_second_subscriber_keeps_the_poller_alive():
    p = _poller(grace_s=0.02)
    async with p.subscribe() as q1:
        await asyncio.wait_for(q1.get(), timeout=2)
        async with p.subscribe() as q2:
            await asyncio.wait_for(q2.get(), timeout=2)
        await asyncio.sleep(0.05)
        assert p.running is True
    await p.aclose()


@pytest.mark.asyncio
async def test_aclose_stops_the_poller_immediately():
    p = _poller(grace_s=10.0)
    async with p.subscribe() as q:
        await asyncio.wait_for(q.get(), timeout=2)
    await p.aclose()
    assert p.running is False
