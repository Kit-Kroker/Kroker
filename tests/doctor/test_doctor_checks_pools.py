"""The worker-pools row's non-PASS outcomes, inside the checks corpus.

The full T011 contract lives in tests/test_doctor_pools.py (the name
tasks.md pins). This file exists because the registry invariant
(test_doctor_registry_invariants) requires every check function to be
named -- and driven to a non-PASS outcome -- inside the
``test_doctor_checks_*.py`` corpus. Rows here: the stale/no-poller
remedy FAIL and the cannot-reach FAIL.
"""

from __future__ import annotations

import asyncio

from sdlc.doctor.checks import check_worker_pools
from sdlc.doctor.models import Status


class _FakeWorkflowService:
    def __init__(self, pollers: list[object]) -> None:
        self._pollers = pollers

    async def describe_task_queue(self, request: object) -> object:
        class _Resp:
            pass

        resp = _Resp()
        resp.pollers = self._pollers
        return resp


class _FakeClient:
    def __init__(self, pollers: list[object]) -> None:
        self.namespace = "default"
        self.workflow_service = _FakeWorkflowService(pollers)


class _Stamp:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self.nanos = 0


class _Poller:
    def __init__(self, seconds: int) -> None:
        self.last_access_time = _Stamp(seconds)


def test_no_fresh_pollers_fails_with_the_remedy(monkeypatch) -> None:
    import time

    monkeypatch.setenv("KROKER_HARNESS_QUEUE", "pools-doctor-q")
    stale = _Poller(int(time.time()) - 3600)

    async def connect(host: str) -> _FakeClient:
        return _FakeClient([stale])

    result = asyncio.run(check_worker_pools(connect=connect))
    assert result.status is Status.FAIL
    assert "KROKER_WORKER_POOL=harness" in result.detail


def test_connect_timeout_fails_as_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", "pools-doctor-q")

    async def _hang(host: str) -> object:
        await asyncio.sleep(60)
        return None

    result = asyncio.run(check_worker_pools(connect=_hang))
    assert result.status is Status.FAIL
    assert "routing on: cannot reach" in result.detail
