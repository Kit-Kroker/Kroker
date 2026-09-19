# tests/graph/test_graph_start.py
"""E-77 T020 (RED): start_graph_run pins the run before client.start_workflow.

Spec: tasks.md T020 / FR-011, FR-013, FR-022. The fake client snapshots the
store tree INSIDE start_workflow, so "written before the start" is observed
at the call, not assumed after it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sdlc.core.models import RoleConfig
from sdlc.graph import from_yaml
from sdlc.graph.node_types import NODE_TYPES
from sdlc.graph.start import start_graph_run
from sdlc.graph.store import GraphStore, registry_sha

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


class _Input:
    def __init__(self) -> None:
        self.graph = from_yaml(FIXTURE.read_text(encoding="utf-8"))
        self.roles = {"architect": RoleConfig(kind="proposer", model="m1")}


class _Client:
    """Records the start call and the store tree as seen at that moment."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.started: list[tuple] = []
        self.tree_at_start: list[str] = []

    async def start_workflow(self, run, arg, *, id, task_queue):
        self.tree_at_start = sorted(
            str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()
        )
        self.started.append((run, arg, id, task_queue))
        return f"handle:{id}"


async def _run_fn(inp):  # stands in for GraphWorkflow.run
    return ""


@pytest.mark.asyncio
async def test_identity_layout_registry_and_pointer_exist_before_start_workflow(tmp_path):
    store = GraphStore(tmp_path)
    client = _Client(tmp_path)
    inp = _Input()
    sha = inp.graph.content_sha()
    await start_graph_run(client, _run_fn, inp, id="feature-add-sso", task_queue="q", store=store)
    assert client.started  # the run did start
    # normalized to forward slashes: Windows rglob yields backslash separators
    tree = [p.replace("\\", "/") for p in client.tree_at_start]
    assert f"{sha}.yaml" in tree  # graph identity
    assert any(p.startswith(f"{sha}/layouts/") for p in tree)  # layout document
    assert any(p.startswith("registry/") for p in tree)  # registry snapshot
    assert "runs/feature-add-sso.json" in tree  # per-run pointer


@pytest.mark.asyncio
async def test_pointer_names_graph_layout_registry_and_roles(tmp_path):
    store = GraphStore(tmp_path)
    client = _Client(tmp_path)
    inp = _Input()
    await start_graph_run(client, _run_fn, inp, id="feature-add-sso", task_queue="q", store=store)
    got = store.get_pointer("feature-add-sso")
    assert got is not None
    assert got.run_id == "feature-add-sso"
    assert got.graph_sha == inp.graph.content_sha()
    assert got.layout_sha == inp.graph.document_sha()
    assert got.registry_sha == registry_sha(NODE_TYPES)
    assert got.roles == inp.roles
    assert store.get_registry(got.registry_sha) is not None  # names a loadable snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,run_id",
    [
        ("put", "feature-ok"),
        ("put_registry", "feature-ok"),
        ("put_pointer", "feature-ok"),
        (None, "bad id!"),
    ],
    ids=["store-put", "registry-write", "pointer-write", "unsafe-run-id"],
)
async def test_write_failures_warn_and_never_block_the_start(tmp_path, caplog, method, run_id):
    class _Broken(GraphStore):
        pass

    if method is not None:

        def raiser(self, *args, **kwargs):
            raise OSError("disk full")

        setattr(_Broken, method, raiser)

    client = _Client(tmp_path)
    with caplog.at_level(logging.WARNING):
        await start_graph_run(
            client, _run_fn, _Input(), id=run_id, task_queue="q", store=_Broken(tmp_path)
        )
    assert len(client.started) == 1  # the run started anyway (FR-011)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


@pytest.mark.asyncio
async def test_start_never_writes_latest(tmp_path):
    store = GraphStore(tmp_path)
    client = _Client(tmp_path)
    await start_graph_run(
        client, _run_fn, _Input(), id="feature-add-sso", task_queue="q", store=store
    )
    assert list(tmp_path.rglob("latest")) == []  # `latest` is save()'s, never start's
