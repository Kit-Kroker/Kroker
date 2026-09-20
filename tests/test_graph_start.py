# tests/test_graph_start.py
"""E-75 spec §6.1: client start helper -- store first, never blocks the start."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.start import start_graph_run
from sdlc.graph.store import GraphStore

FIXTURE = Path(__file__).parent / "graph" / "fixtures" / "pre_code.graph.yaml"


class _Input:
    def __init__(self) -> None:
        self.graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))


class _Client:
    def __init__(self) -> None:
        self.started: list[tuple] = []

    async def start_workflow(self, run, arg, *, id, task_queue):
        self.started.append((run, arg, id, task_queue))
        return f"handle:{id}"


async def _run_fn(inp):  # stands in for GraphWorkflow.run
    return ""


@pytest.mark.asyncio
async def test_stores_the_graph_then_starts(tmp_path):
    client, inp = _Client(), _Input()
    store = GraphStore(tmp_path)
    handle = await start_graph_run(
        client, _run_fn, inp, id="feature-x", task_queue="q", store=store
    )
    assert handle == "handle:feature-x"
    assert client.started == [(_run_fn, inp, "feature-x", "q")]
    assert store.get(inp.graph.content_sha()) == inp.graph


@pytest.mark.asyncio
async def test_a_store_failure_never_blocks_the_start(tmp_path, caplog):
    class _Broken(GraphStore):
        def put(self, graph):
            raise OSError("disk full")

    client = _Client()
    # Absolute root: the ruled contract (bug root-store-write) refuses a
    # relative root= at construction, which would test the refusal, not
    # the never-blocks-the-start contract this test exists for.
    await start_graph_run(
        client, _run_fn, _Input(), id="feature-y", task_queue="q", store=_Broken(tmp_path / "g")
    )
    assert len(client.started) == 1
    assert "graph store write failed" in caplog.text
