"""024 T025 (R7a): every stored history still replays with routing forced on.

Research R7 found sdk-core does not compare activity queues on replay, so no
``workflow.patched()`` marker is needed. This is the permanent guard: replace
``sdlc.pools.on_harness`` with a wrapper that forces every harness queue to
``"forced-q"`` and replay every history under ``tests/replay/histories/``.
Call sites use the module-qualified ``**pools.on_harness(...)`` form
(T026-T028), so one ``setattr`` on the module reaches them all.

RED today: no call site uses ``on_harness`` yet, so the patch is vacuous and
the "a forced queue was applied" assertion fails. T028 removes the xfail.

Stop-guard SG-2: a replay failure means the command sequence changed. Never
re-record a history to turn it green (tests/replay/AGENTS.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

import sdlc  # noqa: F401  (the package the workflow sandbox passes through)
from sdlc import pools
from tests.replay.harness import HISTORIES, load_history, replayer

FORCED_QUEUE = "forced-q"


class NoForcedQueueApplied(AssertionError):
    """The patched ``on_harness`` was never reached: the patch was vacuous."""


def _replay_workflows() -> tuple[type, ...]:
    from sdlc.benchmarks.workflow import BenchmarkWorkflow
    from sdlc.workflows.assessment import AssessmentWorkflow
    from sdlc.workflows.crew import CrewTaskWorkflow
    from sdlc.workflows.deployment import DeploymentWorkflow
    from sdlc.workflows.graph import GraphWorkflow
    from sdlc.workflows.triage import TriageWorkflow

    return (
        GraphWorkflow,
        DeploymentWorkflow,
        CrewTaskWorkflow,
        AssessmentWorkflow,
        TriageWorkflow,
        BenchmarkWorkflow,
    )


def _history_names() -> list[str]:
    return sorted(p.stem for p in HISTORIES.glob("*.json"))


def test_history_corpus_is_not_empty() -> None:
    assert _history_names(), f"no histories under {HISTORIES}"


@pytest.mark.xfail(strict=True, raises=NoForcedQueueApplied, reason="vacuous until T028")
@pytest.mark.asyncio
async def test_forced_queue_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    real = pools.on_harness
    forced: list[tuple[dict[str, Any], str | None]] = []

    def forcing(opts: Mapping[str, Any], queue: str | None) -> dict[str, Any]:
        forced.append((dict(opts), queue))
        return real(opts, FORCED_QUEUE)

    monkeypatch.setattr(pools, "on_harness", forcing)

    names = _history_names()
    assert names, f"no histories under {HISTORIES}"
    failures: dict[str, object] = {}
    workflows = _replay_workflows()
    for name in names:
        result = await replayer(*workflows).replay_workflow(
            load_history(name), raise_on_replay_failure=False
        )
        if result.replay_failure is not None:
            failures[name] = result.replay_failure
    assert not failures, f"histories failed to replay with forced queue: {failures}"

    if not forced:
        raise NoForcedQueueApplied("no on_harness call reached: the forced-queue patch is vacuous")
