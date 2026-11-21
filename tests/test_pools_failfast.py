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

import argparse
import asyncio
import contextlib
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

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


# ------------------------------------------------------------------ start paths
# 024 T031 (SC-005; US2-AS4): with routing on and no harness poller, every start
# path refuses within 10 s and leaves nothing behind. With routing off the same
# calls proceed. Where a path hardcodes its real workflow class (TriageWorkflow.run
# etc.) no stub can complete it, so "proceeds" is observed as the workflow being
# CREATED (then terminated), not as it finishing.

FAILFAST_Q = "failfast-q"
REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_CASE = REPO_ROOT / "benchmarks" / "cases" / "deveval-hone" / "case.yaml"
BENCH_ARM = "zai-coding-plan-glm-5.3"


class _Cfg(BaseModel):
    harness_queue: str | None = None


class _Graph(BaseModel):
    def content_sha(self) -> str:
        return "c" * 8

    def document_sha(self) -> str:
        return "d" * 8


class _RunInput(BaseModel):
    cfg: _Cfg = _Cfg()
    graph: _Graph = _Graph()
    roles: dict[str, str] = {}


@workflow.defn
class _StubGraphRun:
    @workflow.run
    async def run(self, inp: _RunInput) -> str:
        return "done"


class _NoopStore:
    """Duck for GraphStore: swallows every write so no file is created."""

    def put(self, *a: Any, **k: Any) -> None:
        return None

    def put_registry(self, *a: Any, **k: Any) -> str:
        return "r" * 8

    def put_pointer(self, *a: Any, **k: Any) -> None:
        return None


async def _workflow_ids(client: Any) -> set[str]:
    return {w.id async for w in client.list_workflows()}


async def _schedule_ids(client: Any) -> set[str]:
    return {e.id async for e in await client.list_schedules()}


async def _new_ids(client: Any, before: set[str], *, prefix: str = "") -> set[str]:
    """Wait (visibility is eventual) for ids not in ``before`` to appear."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        new = {i for i in await _workflow_ids(client) - before if i.startswith(prefix)}
        if new:
            return new
        await asyncio.sleep(0.25)
    return set()


async def _terminate(client: Any, ids: set[str]) -> None:
    for i in ids:
        with contextlib.suppress(Exception):
            await client.get_workflow_handle(i).terminate("T031 cleanup")


def _namespace(*argv: str) -> argparse.Namespace:
    from sdlc.cli import build_parser

    return build_parser().parse_args(list(argv))


async def test_start_paths_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from temporalio.contrib.pydantic import sdlc_data_converter

    from sdlc import cli
    from sdlc.benchmarks.cli import _run_matrix
    from sdlc.graph.start import start_graph_run
    from sdlc.maintenance.cli import _enable
    from sdlc.schedules.apply import apply_changes

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    async def run_cli(cmd: str) -> None:
        monkeypatch.setattr(sys, "argv", ["sdlc", cmd, "--repo", str(repo)])
        await asyncio.wait_for(cli.main(), timeout=10)

    async def graph_start(client: Any, wf_id: str) -> Any:
        return await start_graph_run(
            client, _StubGraphRun.run, _RunInput(), id=wf_id, task_queue="t", store=_NoopStore()
        )

    async def bench() -> str:
        return await _run_matrix(str(BENCH_CASE), arm=BENCH_ARM, skip_smoke=True, allow_parked=True)

    # start_local, not time-skipping: DescribeTaskQueue is unimplemented there.
    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        client = env.client
        monkeypatch.setenv("TEMPORAL_HOST", client.service_client.config.target_host)
        enable_args = _namespace(
            "maintain", "enable", "proj", "--repo", str(repo), "--no-build-probe"
        )

        # ---- routing ON, no worker polls failfast-q: every path refuses ----
        monkeypatch.setenv("KROKER_HARNESS_QUEUE", FAILFAST_Q)

        with pytest.raises(HarnessQueueUnpolled):
            await asyncio.wait_for(graph_start(client, "g-refused"), timeout=10)
        for cmd in ("triage", "tidyup", "assess"):
            with pytest.raises(HarnessQueueUnpolled):
                await run_cli(cmd)
        with pytest.raises(HarnessQueueUnpolled):
            await asyncio.wait_for(bench(), timeout=10)
        capsys.readouterr()
        rc = await asyncio.wait_for(_enable(enable_args, client), timeout=10)
        err = capsys.readouterr().err
        # Reviewer-approved T030 deviation: _enable prints and returns 2, it does not raise.
        assert rc == 2
        assert FAILFAST_Q in err and "KROKER_WORKER_POOL=harness" in err
        with pytest.raises(HarnessQueueUnpolled):
            await asyncio.wait_for(apply_changes(client, [], []), timeout=10)

        assert [w.id async for w in client.list_workflows()] == []
        assert await _schedule_ids(client) == set()

        # ---- routing OFF: the same calls proceed ----
        monkeypatch.delenv("KROKER_HARNESS_QUEUE", raising=False)

        async with Worker(
            client,
            task_queue="t",
            workflows=[_StubGraphRun],
            workflow_runner=UnsandboxedWorkflowRunner(),
        ):
            handle = await asyncio.wait_for(graph_start(client, "g-ok"), timeout=10)
            assert await handle.result() == "done"

        for cmd in ("triage", "tidyup", "assess"):
            before = await _workflow_ids(client)
            await run_cli(cmd)
            created = await _new_ids(client, before)
            assert created, f"{cmd} created no workflow with routing off"
            await _terminate(client, created)

        before = await _workflow_ids(client)
        bench_task = asyncio.create_task(bench())
        created = await _new_ids(client, before, prefix="bench-")
        assert created, "benchmark start created no workflow with routing off"
        await _terminate(client, created)
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(bench_task, timeout=10)

        before = await _workflow_ids(client)
        assert await asyncio.wait_for(_enable(enable_args, client), timeout=10) == 0
        created = await _new_ids(client, before, prefix="maint-")
        assert created, "maintenance enable created no workflow with routing off"
        await _terminate(client, created)

        assert await asyncio.wait_for(apply_changes(client, [], []), timeout=10) == []


# ------------------------------------------------------------- chaos edge cases
# Representative paths (one per case, to bound runtime): case 1 uses start_graph_run
# (the only path that writes to a store before starting); cases 2 and 3 use
# apply_changes with an empty plan (the cheapest path, no workflow needed).


class _RecordingStore(_NoopStore):
    """A _NoopStore that records every write, to prove none happened before refusal."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def put(self, *a: Any, **k: Any) -> None:
        self.calls.append("put")

    def put_registry(self, *a: Any, **k: Any) -> str:
        self.calls.append("put_registry")
        return "r" * 8

    def put_pointer(self, *a: Any, **k: Any) -> None:
        self.calls.append("put_pointer")


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


async def test_refusal_precedes_every_side_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from temporalio.contrib.pydantic import sdlc_data_converter

    from sdlc.graph.start import start_graph_run

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", FAILFAST_Q)
    store = _RecordingStore()
    before = _tree(tmp_path)

    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        with pytest.raises(HarnessQueueUnpolled):
            await asyncio.wait_for(
                start_graph_run(
                    env.client,
                    _StubGraphRun.run,
                    _RunInput(),
                    id="g-refused-clean",
                    task_queue="t",
                    store=store,
                ),
                timeout=10,
            )

        assert store.calls == [], f"store written before the poller check: {store.calls}"
        assert _tree(tmp_path) == before, "refusal left files or directories behind"
        assert [w.id async for w in env.client.list_workflows()] == []


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
async def test_blank_harness_queue_is_routing_off(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    from temporalio.contrib.pydantic import sdlc_data_converter

    from sdlc.schedules.apply import apply_changes

    monkeypatch.setenv("KROKER_HARNESS_QUEUE", blank)

    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        # No worker polls anything; blank means routing off, so this must not refuse.
        assert await asyncio.wait_for(apply_changes(env.client, [], []), timeout=10) == []


async def test_a_routing_off_success_does_not_satisfy_a_later_routing_on_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from temporalio.contrib.pydantic import sdlc_data_converter

    from sdlc.schedules.apply import apply_changes

    async with await WorkflowEnvironment.start_local(data_converter=sdlc_data_converter) as env:
        client = env.client

        async def refuses() -> None:
            monkeypatch.setenv("KROKER_HARNESS_QUEUE", FAILFAST_Q)
            with pytest.raises(HarnessQueueUnpolled):
                await asyncio.wait_for(apply_changes(client, [], []), timeout=10)

        async def proceeds() -> None:
            monkeypatch.delenv("KROKER_HARNESS_QUEUE", raising=False)
            assert await asyncio.wait_for(apply_changes(client, [], []), timeout=10) == []

        await refuses()
        await proceeds()
        await refuses()  # the success above must not be memoized as "queue is fine"
        await proceeds()
        await refuses()
