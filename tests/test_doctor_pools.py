"""Doctor row for the worker pools (024 T011; P-FR-008, contracts/worker-boot.md §Doctor).

RED until T012 adds ``sdlc.doctor.checks.check_worker_pools(connect=None)``. Imports are
inside each test so each case fails on the missing attribute, not at collection.

The check reads ``KROKER_HARNESS_QUEUE`` from the environment and never raises (SG-3):
every stub misbehaviour in the contract table becomes a FAIL row.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest

QUEUE = "pools-q"
HOST = "doctor-test-host:7233"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KROKER_HARNESS_QUEUE", raising=False)
    monkeypatch.setenv("TEMPORAL_HOST", HOST)


def _poller(age_s: float) -> SimpleNamespace:
    t = time.time() - age_s
    return SimpleNamespace(
        last_access_time=SimpleNamespace(seconds=int(t), nanos=int((t % 1) * 1e9))
    )


class _Service:
    def __init__(self, pollers: list[Any] | None = None, exc: BaseException | None = None) -> None:
        self._pollers = pollers or []
        self._exc = exc
        self.requests: list[Any] = []

    async def describe_task_queue(self, request: Any) -> Any:
        self.requests.append(request)
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(pollers=self._pollers)


def _connect_to(service: _Service) -> Any:
    client = SimpleNamespace(namespace="default", workflow_service=service)

    async def connect(*_args: Any, **_kwargs: Any) -> Any:
        return client

    return connect


def _connect_raising(exc: BaseException) -> Any:
    async def connect(*_args: Any, **_kwargs: Any) -> Any:
        raise exc

    return connect


def _run(connect: Any) -> Any:
    from sdlc.doctor.checks import check_worker_pools

    return asyncio.run(check_worker_pools(connect))


def _status(result: Any) -> str:
    return str(result.status.value)


# ------------------------------------------------------------------ 1. unset


def test_unset_is_a_pass_naming_the_single_pool_and_never_connects() -> None:
    calls: list[Any] = []

    async def must_not_connect(*args: Any, **kwargs: Any) -> Any:
        calls.append((args, kwargs))
        raise AssertionError("connect must not be called when routing is off")

    result = _run(must_not_connect)

    assert _status(result) == "PASS"
    assert "single pool" in result.detail
    assert "ai-sdlc" in result.detail
    assert calls == []


def test_blank_queue_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", "  ")
    result = _run(_connect_raising(AssertionError("must not connect")))
    assert _status(result) == "PASS"
    assert "single pool" in result.detail


# ------------------------------------------------- 2. set, fresh poller(s): PASS


@pytest.mark.parametrize("count", [1, 2])
def test_fresh_pollers_pass_with_queue_and_count(
    monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)
    service = _Service([_poller(0) for _ in range(count)])

    result = _run(_connect_to(service))

    assert _status(result) == "PASS"
    assert QUEUE in result.detail
    assert f"{count} worker" in result.detail
    # It asked about the harness queue, not the core one.
    assert [r.task_queue.name for r in service.requests] == [QUEUE]


def test_default_sentinel_checks_the_default_harness_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sdlc.pools import HARNESS_QUEUE_DEFAULT

    monkeypatch.setenv("KROKER_HARNESS_QUEUE", "default")
    service = _Service([_poller(0)])

    result = _run(_connect_to(service))

    assert _status(result) == "PASS"
    assert HARNESS_QUEUE_DEFAULT in result.detail
    assert [r.task_queue.name for r in service.requests] == [HARNESS_QUEUE_DEFAULT]


# ----------------------------------------- 3. set, no fresh poller: FAIL + remedy


@pytest.mark.parametrize(
    "pollers",
    [
        pytest.param([], id="no-pollers"),
        pytest.param([_poller(3600)], id="one-stale"),
        pytest.param([_poller(3600), _poller(7200)], id="all-stale"),
    ],
)
def test_no_fresh_poller_fails_with_the_remedy(
    monkeypatch: pytest.MonkeyPatch, pollers: list[Any]
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service(pollers)))

    assert _status(result) == "FAIL"
    assert QUEUE in result.detail
    assert "has no harness worker" in result.detail
    assert "KROKER_WORKER_POOL=harness" in result.detail


# ------------------------------------------- 4. set, Temporal unreachable: FAIL


@pytest.mark.parametrize(
    "exc",
    [TimeoutError(), ConnectionRefusedError("boom"), RuntimeError("no route")],
    ids=["timeout", "connection-refused", "generic"],
)
def test_unreachable_temporal_fails_naming_host_and_queue(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_raising(exc))

    assert _status(result) == "FAIL"
    assert "routing on: cannot reach" in result.detail
    assert HOST in result.detail
    assert QUEUE in result.detail


# --------------------------------------------- SG-3: the check never raises


def test_describe_task_queue_raising_is_a_fail_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service(exc=RuntimeError("describe blew up"))))

    assert _status(result) == "FAIL"
    assert QUEUE in result.detail


def test_describe_task_queue_timeout_is_a_fail_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service(exc=TimeoutError())))

    assert _status(result) == "FAIL"
    assert QUEUE in result.detail


# ------------------------------------------------- chaos pass (024 T011, edge cases)


@pytest.mark.parametrize(
    ("ages", "fresh"),
    [
        pytest.param([0, 3600], 1, id="fresh-then-stale"),
        pytest.param([3600, 0], 1, id="stale-then-fresh"),
        pytest.param([0, 3600, 5], 2, id="two-fresh-around-one-stale"),
    ],
)
def test_mixed_pollers_pass_and_count_only_the_fresh_ones(
    monkeypatch: pytest.MonkeyPatch, ages: list[int], fresh: int
) -> None:
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service([_poller(a) for a in ages])))

    assert _status(result) == "PASS"
    assert f"polled by {fresh} worker" in result.detail, result.detail
    assert f"polled by {len(ages)} worker" not in result.detail or fresh == len(ages)


def test_poller_just_past_the_freshness_edge_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default freshness is 90 s (R6): a poller last seen 91 s ago is stale.
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service([_poller(91)])))

    assert _status(result) == "FAIL"
    assert "has no harness worker" in result.detail
    assert "KROKER_WORKER_POOL=harness" in result.detail


def test_poller_well_inside_the_freshness_window_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    # Guard against an over-strict check that only accepts "just now".
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", QUEUE)

    result = _run(_connect_to(_Service([_poller(60)])))

    assert _status(result) == "PASS"
    assert "polled by 1 worker" in result.detail
