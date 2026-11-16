"""025 Part B infra repair (T020 STOP finding): the worker must BOOT with
the FR-205 activity set.

The compose core worker crash-looped at boot (preflight.md SS4):
temporalio rejects a sync ``@activity.defn`` — ``paths_exist``, arrived
with 023 FR-205 (cbbf6f02) — unless the Worker carries an
``activity_executor``. The pool tests intercept ``worker.Worker`` with a
FakeWorker that skips temporalio's __init__ validation, so no test ever
constructed a real Worker with the production activity sets — the
regression rode from 023 into the fleet image untouched (H7's blind spot:
no real worker boot since the pools landed).

These tests construct REAL Workers via ``worker._build_workers`` — the
exact production path ``worker.main`` uses — against a local environment.
Construction itself is the assertion: the failure was at Worker.__init__.
"""

from __future__ import annotations

import pytest
from temporalio.testing import WorkflowEnvironment

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

from sdlc.pools import pool_boot_plan  # noqa: E402
from sdlc.worker import _build_workers, get_worker_activities  # noqa: E402


async def test_single_pool_boots_with_the_fr205_activity_set() -> None:
    """Today, exactly (G-1): one Worker, all activities, no identity —
    including the sync paths_exist. Against the unfixed code this raised
    'Activity paths_exist is not async so an activity_executor must be
    present' at construction."""
    assert any(getattr(a, "__name__", "") == "paths_exist" for a in get_worker_activities()), (
        "the FR-205 activity left the default registration — test needs updating"
    )
    async with await WorkflowEnvironment.start_local() as env:
        workers = _build_workers(env.client, pool_boot_plan("all", None, None))
        assert len(workers) == 1


async def test_both_pools_boot_with_the_fr205_activity_set() -> None:
    """The 024 split (core + harness, cap 2) constructs too; the harness
    set excludes paths_exist, the core set does not."""
    async with await WorkflowEnvironment.start_local() as env:
        workers = _build_workers(env.client, pool_boot_plan("all", "fleet-boot-q", 2))
        assert len(workers) == 2
