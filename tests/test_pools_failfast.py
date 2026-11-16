"""The R6 poller-freshness proof (024 T010; plan C3, risk 1).

PROOF task: this tests the platform's DescribeTaskQueue poller signal
(``last_access_time``) on the ephemeral dev-server, not just our code.
Per tasks.md: if leg (b) or (c) cannot be made to hold, STOP and report —
R6 is re-planned; do not work around it.

Observed on the start_local dev-server, 2026-11-16 (worker with one
activity, no workflows running; three consecutive runs identical):

- lag (start of worker -> require_harness_poller passes): 0.26 s — well
  inside the 5 s budget (leg b).
- linger (worker shutdown -> first HarnessQueueUnpolled with
  freshness_s=3): 2.79 s — the last poll lands ~0.2 s before shutdown
  completes and then ages out at the freshness boundary; the entry does
  not vanish early or linger indefinitely (leg c).

Refresh this record if the environment changes materially.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.pools import HarnessQueueUnpolled, require_harness_poller

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

QUEUE = "poller-proof-q"
FRESHNESS_S = 3


@activity.defn
async def _noop() -> str:
    return "ok"


async def _eventually_passes(client, *, budget_s: float) -> float:
    """Poll require_harness_poller until it passes; return the elapsed lag."""
    start = time.monotonic()
    while time.monotonic() - start < budget_s:
        try:
            await require_harness_poller(client, QUEUE, freshness_s=FRESHNESS_S, timeout_s=5)
            return time.monotonic() - start
        except HarnessQueueUnpolled:
            await asyncio.sleep(0.25)
    raise AssertionError(f"poller not observed fresh within {budget_s}s")


async def test_poller_freshness() -> None:
    # start_local, not start_time_skipping: DescribeTaskQueue is
    # unimplemented on the test server; the dev-server implements it and
    # this proof is about that exact signal.
    async with await WorkflowEnvironment.start_local() as env:
        client = env.client

        # (a) No worker on the queue: it raises within 10 s, naming the
        # queue and the KROKER_WORKER_POOL=harness remedy.
        start = time.monotonic()
        with pytest.raises(HarnessQueueUnpolled) as excinfo:
            await asyncio.wait_for(
                require_harness_poller(client, QUEUE, freshness_s=FRESHNESS_S, timeout_s=5),
                timeout=10,
            )
        assert time.monotonic() - start < 10
        assert QUEUE in str(excinfo.value)
        assert "KROKER_WORKER_POOL=harness" in str(excinfo.value)

        # (b) A harness-only worker on the queue: passes within 5 s.
        worker = Worker(client, task_queue=QUEUE, activities=[_noop])
        async with worker:
            lag = await _eventually_passes(client, budget_s=5)
        assert lag < 5.0, f"observed lag {lag:.2f}s exceeds the 5s budget"

        # (c) After that worker shuts down: it raises once freshness_s has
        # elapsed (the entry may read fresh until the last poll ages out).
        start = time.monotonic()
        linger: float | None = None
        while time.monotonic() - start < 15:
            try:
                await require_harness_poller(client, QUEUE, freshness_s=FRESHNESS_S, timeout_s=5)
                await asyncio.sleep(0.25)
            except HarnessQueueUnpolled:
                linger = time.monotonic() - start
                break
        assert linger is not None, "no HarnessQueueUnpolled within 15s of shutdown"
        assert linger is not None and linger >= 1.0, (
            f"raised after only {linger:.2f}s — the signal vanished suspiciously fast"
        )
