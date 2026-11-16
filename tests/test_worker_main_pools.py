"""``worker.main()`` pool wiring, fast tier (024 T008; contracts/worker-boot.md G-1..G-5, R5).

No Temporal server: ``Client``, ``Worker`` and ``worktree_janitor`` are replaced by
recorders, and the slow boot checks (registry, crew CLIs, graph, harness versions)
are stubbed so only the pool wiring is under test. ``Worker.run()`` and the janitor
hang on an Event nobody sets, so ``main()`` sits in steady state until the test
cancels it.

Case 1 is the G-1 today-pin and largely passes before T009; cases 2-5 are RED.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

ENV_POOL = "KROKER_WORKER_POOL"
ENV_QUEUE = "KROKER_HARNESS_QUEUE"
ENV_CAP = "KROKER_HARNESS_CAP"
Q = "pools-q"

WORKFLOW_NAMES = {
    "GraphWorkflow",
    "BenchmarkWorkflow",
    "ReflectWorkflow",
    "DeploymentWorkflow",
    "TriageWorkflow",
    "TidyUpWorkflow",
    "AssessmentWorkflow",
    "CrewTaskWorkflow",
    "MaintenanceWorkflow",
    "MaintenanceKickWorkflow",
}


@dataclass
class Recorder:
    connects: list[Any] = field(default_factory=list)
    built: list[dict[str, Any]] = field(default_factory=list)  # build order
    running: list[Any] = field(default_factory=list)  # entered run()
    janitors: list[Any] = field(default_factory=list)


@pytest.fixture
def rec(monkeypatch: pytest.MonkeyPatch) -> Iterator[Recorder]:
    from sdlc import worker

    for var in (ENV_POOL, ENV_QUEUE, ENV_CAP):
        monkeypatch.delenv(var, raising=False)

    r = Recorder()
    sentinel = object()

    class FakeClient:
        @classmethod
        async def connect(cls, *args: Any, **kwargs: Any) -> object:
            r.connects.append((args, kwargs))
            return sentinel

    class FakeWorker:
        def __init__(self, client: Any, **kwargs: Any) -> None:
            assert client is sentinel
            r.built.append(dict(kwargs))

        async def run(self) -> None:
            r.running.append(self)
            await asyncio.Event().wait()

    async def fake_janitor(client: Any, **kwargs: Any) -> None:
        r.janitors.append(client)
        await asyncio.Event().wait()

    monkeypatch.setattr(worker, "Client", FakeClient)
    monkeypatch.setattr(worker, "Worker", FakeWorker)
    monkeypatch.setattr(worker, "worktree_janitor", fake_janitor)
    # Boot checks are not what is under test (and need a real registry / CLIs).
    monkeypatch.setattr(worker, "validate_registry", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "load_registry", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "validate_crew_clis", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "graph_boot_problems", lambda *_a, **_k: [])
    monkeypatch.setattr(worker, "check_harness_versions", lambda *_a, **_k: None)
    monkeypatch.setattr("sdlc.observability.logfire_setup.configure", lambda *_a, **_k: False)
    yield r


def _names(activities: Any) -> list[str]:
    return sorted(a.__temporal_activity_definition.name for a in activities)


def _wf_names(workflows: Any) -> set[str]:
    return {w.__name__ for w in workflows}


def _run_to_steady_state(rec: Recorder, expect_workers: int) -> tuple[list[dict[str, Any]], int]:
    """Run ``worker.main()`` until ``expect_workers`` workers are running, then cancel it.

    Returns ``(built kwargs in build order, janitor start count)`` as of steady state.
    A ``main()`` that stops early re-raises its error; one that never reaches the
    expected worker count fails with what it did build.
    """
    from sdlc import worker

    async def scenario() -> tuple[list[dict[str, Any]], int]:
        task = asyncio.create_task(worker.main())
        try:
            for _ in range(100):
                if task.done() or len(rec.running) >= expect_workers:
                    break
                await asyncio.sleep(0.01)
            if task.done():
                task.result()  # surface SystemExit / crash
            await asyncio.sleep(0.05)  # let the janitor task (if any) start
            assert len(rec.running) == expect_workers, (
                f"expected {expect_workers} running worker(s), got {len(rec.running)} "
                f"(built {len(rec.built)})"
            )
            return list(rec.built), len(rec.janitors)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return asyncio.run(scenario())


def _identity(kw: dict[str, Any]) -> str:
    return str(kw.get("identity", ""))


# ------------------------------------------------- 1. no vars: today, exactly (G-1, G-5)


def test_no_vars_builds_one_worker_exactly_as_today(
    rec: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    from sdlc import worker
    from sdlc.task_queue import TASK_QUEUE

    built, janitors = _run_to_steady_state(rec, expect_workers=1)

    assert len(built) == 1
    kw = built[0]
    assert kw["task_queue"] == TASK_QUEUE == "ai-sdlc"
    assert len(kw["workflows"]) == 10
    assert _wf_names(kw["workflows"]) == WORKFLOW_NAMES
    assert _names(kw["activities"]) == _names(worker.get_worker_activities())
    # Today's exact Worker call keeps its arguments: no cap, no identity.
    # (025 Part B repair: activity_executor joins every Worker call — the
    # sync paths_exist activity, FR-205, cannot construct without it.)
    assert set(kw) == {"task_queue", "workflows", "activities", "activity_executor"}
    assert janitors == 1
    assert "worker running on task queue 'ai-sdlc'" in capsys.readouterr().out.splitlines()


# --------------------------------------------- 2. all + queue + cap 2 (G-3, G-4)


def test_all_with_queue_builds_harness_worker_first_then_core(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc import worker
    from sdlc.task_queue import TASK_QUEUE

    monkeypatch.setenv(ENV_QUEUE, Q)
    monkeypatch.setenv(ENV_CAP, "2")

    built, janitors = _run_to_steady_state(rec, expect_workers=2)

    assert len(built) == 2
    harness, core = built  # G-4: harness is built first
    # harness worker
    assert harness["task_queue"] == Q
    assert harness["max_concurrent_activities"] == 2
    assert not harness.get("workflows")
    assert _names(harness["activities"]) == _names(worker.harness_activities())
    assert _identity(harness).startswith("harness@")
    # core worker keeps everything
    assert core["task_queue"] == TASK_QUEUE
    assert _wf_names(core["workflows"]) == WORKFLOW_NAMES
    assert len(core["workflows"]) == 10
    assert _names(core["activities"]) == _names(worker.get_worker_activities())
    assert _identity(core).startswith("core@")
    assert janitors == 1  # `all` still runs the janitor


# ----------------------------------------------------------------- 3. core + queue


def test_core_with_queue_builds_one_core_worker_and_no_janitor(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc import worker
    from sdlc.task_queue import TASK_QUEUE

    monkeypatch.setenv(ENV_POOL, "core")
    monkeypatch.setenv(ENV_QUEUE, Q)

    built, janitors = _run_to_steady_state(rec, expect_workers=1)

    assert len(built) == 1
    kw = built[0]
    assert kw["task_queue"] == TASK_QUEUE
    assert _wf_names(kw["workflows"]) == WORKFLOW_NAMES
    assert _names(kw["activities"]) == _names(worker.core_activities())
    assert _identity(kw).startswith("core@")
    assert janitors == 0


# --------------------------------------------------------------- 4. harness + queue


def test_harness_with_queue_builds_one_harness_worker_and_starts_janitor(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc import worker

    monkeypatch.setenv(ENV_POOL, "harness")
    monkeypatch.setenv(ENV_QUEUE, Q)

    built, janitors = _run_to_steady_state(rec, expect_workers=1)

    assert len(built) == 1
    kw = built[0]
    assert kw["task_queue"] == Q
    assert not kw.get("workflows")
    assert _names(kw["activities"]) == _names(worker.harness_activities())
    assert _identity(kw).startswith("harness@")
    assert janitors == 1


# ------------------------------------------------------- 5. refusals (G-2): pre-connect

REFUSALS = [
    pytest.param("all", None, "2", ENV_CAP, id="all-cap-without-queue"),
    pytest.param("core", None, None, ENV_QUEUE, id="core-queueless"),
    pytest.param("harness", None, None, ENV_QUEUE, id="harness-queueless"),
    pytest.param("bogus", None, None, ENV_POOL, id="bogus-pool"),
    *[
        pytest.param(pool, Q, cap, ENV_CAP, id=f"{pool}-cap{cap}")
        for pool in ("all", "core", "harness")
        for cap in ("0", "-1")
    ],
]


@pytest.mark.parametrize(("pool", "queue", "cap", "var"), REFUSALS)
def test_refusals_exit_before_connecting(
    rec: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    pool: str,
    queue: str | None,
    cap: str | None,
    var: str,
) -> None:
    from sdlc import worker

    monkeypatch.setenv(ENV_POOL, pool)
    if queue is not None:
        monkeypatch.setenv(ENV_QUEUE, queue)
    if cap is not None:
        monkeypatch.setenv(ENV_CAP, cap)

    async def attempt() -> None:
        try:
            await asyncio.wait_for(worker.main(), timeout=0.5)
        except TimeoutError:
            pytest.fail("main() did not refuse: it booted and kept running")

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(attempt())

    assert var in str(excinfo.value)
    assert rec.connects == [], "a refusal must happen before Client.connect"
    assert rec.built == []


# ------------------------------------------------- chaos pass (024 T008, edge cases)

NOTHING_SIDE_EFFECTING = [
    pytest.param("bogus", None, None, id="bogus-pool"),
    pytest.param("all", None, "2", id="all-cap-without-queue"),
    pytest.param("harness", None, None, id="harness-queueless"),
    pytest.param("core", Q, "0", id="core-cap0"),
]


@pytest.mark.parametrize(("pool", "queue", "cap"), NOTHING_SIDE_EFFECTING)
def test_refusal_has_no_side_effects_before_it(
    rec: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pool: str,
    queue: str | None,
    cap: str | None,
) -> None:
    from sdlc import worker

    monkeypatch.setenv(ENV_POOL, pool)
    if queue is not None:
        monkeypatch.setenv(ENV_QUEUE, queue)
    if cap is not None:
        monkeypatch.setenv(ENV_CAP, cap)

    async def attempt() -> None:
        try:
            await asyncio.wait_for(worker.main(), timeout=0.5)
        except TimeoutError:
            pytest.fail("main() did not refuse: it booted and kept running")

    with pytest.raises(SystemExit):
        asyncio.run(attempt())

    assert "worker running" not in capsys.readouterr().out
    assert rec.built == [], "no Worker may be built before a refusal"
    assert rec.running == []
    assert rec.janitors == [], "the janitor must not start before a refusal"


def test_all_with_queue_and_cap_routes_each_worker_to_its_own_queue(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.task_queue import TASK_QUEUE

    monkeypatch.setenv(ENV_QUEUE, Q)
    monkeypatch.setenv(ENV_CAP, "2")

    built, _ = _run_to_steady_state(rec, expect_workers=2)

    queues = sorted(kw["task_queue"] for kw in built)
    assert queues == sorted([Q, "ai-sdlc"]) and TASK_QUEUE == "ai-sdlc"
    harness = next(kw for kw in built if kw["task_queue"] == Q)
    core = next(kw for kw in built if kw["task_queue"] == TASK_QUEUE)
    assert harness["max_concurrent_activities"] == 2
    # The cap belongs to the harness pool only; the core worker stays uncapped.
    assert "max_concurrent_activities" not in core


def test_default_sentinel_in_harness_mode_resolves_to_the_default_queue(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.pools import HARNESS_QUEUE_DEFAULT

    monkeypatch.setenv(ENV_POOL, "harness")
    monkeypatch.setenv(ENV_QUEUE, "default")

    built, _ = _run_to_steady_state(rec, expect_workers=1)

    assert [kw["task_queue"] for kw in built] == [HARNESS_QUEUE_DEFAULT]
    assert built[0]["task_queue"] != "default"


@pytest.mark.parametrize("pool", [None, "all"], ids=["unset", "explicit-all"])
def test_single_pool_worker_kwargs_have_no_identity_key(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch, pool: str | None
) -> None:
    # G-1: today's Worker(...) call shape is preserved; identity is for pool workers only.
    if pool is not None:
        monkeypatch.setenv(ENV_POOL, pool)

    built, _ = _run_to_steady_state(rec, expect_workers=1)

    assert len(built) == 1
    assert "identity" not in built[0]
    assert "max_concurrent_activities" not in built[0]


@pytest.mark.parametrize(
    ("pool", "queue"),
    [(None, None), ("harness", Q)],
    ids=["single-pool", "harness"],
)
def test_janitor_receives_the_connected_client(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch, pool: str | None, queue: str | None
) -> None:
    from sdlc import worker

    returned: list[object] = []
    fake_connect = worker.Client.connect

    async def recording_connect(*args: Any, **kwargs: Any) -> object:
        client = await fake_connect(*args, **kwargs)
        returned.append(client)
        return client

    monkeypatch.setattr(worker.Client, "connect", staticmethod(recording_connect))
    if pool is not None:
        monkeypatch.setenv(ENV_POOL, pool)
    if queue is not None:
        monkeypatch.setenv(ENV_QUEUE, queue)

    _, janitors = _run_to_steady_state(rec, expect_workers=1)

    assert janitors == 1
    assert len(returned) == 1
    assert rec.janitors[0] is returned[0]


@pytest.mark.parametrize(
    ("pool", "queue"),
    [(None, None), ("all", Q), ("core", Q), ("harness", Q)],
    ids=["single-pool", "all", "core", "harness"],
)
def test_boot_checks_still_run_in_every_mode(
    rec: Recorder, monkeypatch: pytest.MonkeyPatch, pool: str | None, queue: str | None
) -> None:
    from sdlc import worker

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("registry invariant violated")

    monkeypatch.setattr(worker, "validate_registry", boom)
    if pool is not None:
        monkeypatch.setenv(ENV_POOL, pool)
    if queue is not None:
        monkeypatch.setenv(ENV_QUEUE, queue)

    async def attempt() -> None:
        try:
            await asyncio.wait_for(worker.main(), timeout=0.5)
        except TimeoutError:
            pytest.fail("main() skipped the boot check and kept running")

    with pytest.raises(RuntimeError, match="registry invariant violated"):
        asyncio.run(attempt())

    assert rec.built == [], "a failed boot check must not leave a Worker built"
    assert rec.janitors == []
