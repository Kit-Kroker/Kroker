# tests/graph/test_graph_store_e77.py
"""E-77 store contract (RED): layout files, registry snapshots, run pointers.

Spec: .specify/specs/001-canonical-stage-graph-sha/data-model.md (Store files,
Store API) and contracts/records-and-store.md. Everything here targets API
that does not exist yet; imports of new names (RunGraphPointer) stay
function-local so each section fails on its own missing name.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdlc.core.models import RoleConfig
from sdlc.graph import from_yaml
from sdlc.graph.io import to_yaml
from sdlc.graph.model import NodePort, PipelineGraph
from sdlc.graph.node_types import NodeTypeSpec
from sdlc.graph.store import GraphStore
from sdlc.graph.validate import ValidationReport, validate

GRAPH = {
    "schema_version": 1,
    "nodes": [
        {
            "id": "architect",
            "type": "architect",
            "role": {"kind": "proposer", "model": "m1"},
            "position": {"x": 1, "y": 2},
            "label": "Architect",
        },
        {"id": "planner", "type": "plan", "role": {"kind": "proposer", "model": "m2"}},
    ],
    "edges": [
        {
            "source": "architect",
            "source_port": "spec",
            "target": "planner",
            "target_port": "spec",
            "label": "hand over",
        }
    ],
}


def _graph(mutate=None) -> PipelineGraph:
    data = copy.deepcopy(GRAPH)
    if mutate is not None:
        mutate(data)
    return PipelineGraph.model_validate(data)


def _moved(d):
    d["nodes"][0]["position"] = {"x": 99, "y": -1}


def _re_semantics(d):
    d["nodes"][1]["role"]["model"] = "m9"


def _layouts(root: Path, sha: str) -> list[Path]:
    return sorted((root / sha / "layouts").glob("*.yaml"))


# --- (a) put: identity file unchanged, layout file added -------------------


def test_put_writes_identity_and_one_layout_file(tmp_path):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    assert (tmp_path / f"{sha}.yaml").is_file()  # identity write, as today
    files = _layouts(tmp_path, sha)
    assert len(files) == 1
    stored = from_yaml(files[0].read_text(encoding="utf-8"))
    assert stored.content_sha() == sha
    by_id = {n.id: n for n in stored.nodes}
    assert by_id["architect"].position is not None  # cosmetics kept in the layout
    assert by_id["architect"].label == "Architect"


def test_second_put_with_a_new_layout_never_rewrites_the_identity_file(tmp_path):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    identity = tmp_path / f"{sha}.yaml"
    first_bytes = identity.read_bytes()
    moved = _graph(_moved)
    assert moved.content_sha() == sha  # cosmetics never change content identity
    assert store.put(moved) == sha
    assert identity.read_bytes() == first_bytes  # first write wins, always
    assert len(_layouts(tmp_path, sha)) == 2  # one layout file per layout


# --- (b) layouts are trusted only after full verification ------------------


def test_layout_that_verifies_is_served(tmp_path):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    doc = g.document_sha()
    assert store.get(sha, layout=doc) == g


def test_unparseable_layout_is_not_served(tmp_path):
    store = GraphStore(tmp_path)
    sha = _graph().content_sha()
    layout = tmp_path / sha / "layouts" / f"{'d' * 64}.yaml"
    layout.parent.mkdir(parents=True)
    layout.write_text("]: not a graph at all", encoding="utf-8")
    assert store.get(sha, layout="d" * 64) is None


def test_layout_whose_name_is_not_its_document_sha_is_not_served(tmp_path):
    """Parses, content even matches the directory -- but the file name lies."""
    store = GraphStore(tmp_path)
    sha = _graph().content_sha()
    layout = tmp_path / sha / "layouts" / f"{'e' * 64}.yaml"
    layout.parent.mkdir(parents=True)
    layout.write_text(to_yaml(_graph(_moved)), encoding="utf-8")
    assert store.get(sha, layout="e" * 64) is None


def test_layout_of_a_foreign_graph_is_not_served(tmp_path):
    """Self-consistent file (name == its own document_sha) whose content_sha
    is not the directory's sha: verification condition 3."""
    store = GraphStore(tmp_path)
    sha = _graph().content_sha()
    foreign = _graph(_re_semantics)
    name = foreign.document_sha()
    layout = tmp_path / sha / "layouts" / f"{name}.yaml"
    layout.parent.mkdir(parents=True)
    layout.write_text(to_yaml(foreign), encoding="utf-8")
    assert store.get(sha, layout=name) is None


# --- (c) registry snapshots -------------------------------------------------


def _spec(type_: str, kind: str, stage: str) -> NodeTypeSpec:
    return NodeTypeSpec(
        type=type_,
        kind=kind,
        role=None,
        canonical_stage=stage,
        ports=(
            NodePort(name="spec", direction="out", payload=None),
            NodePort(name="artifact", direction="in", payload=None),
        ),
    )


REG = {
    "architect": _spec("architect", "stage", "architecture"),
    "plan": _spec("plan", "stage", "plan"),
}


def test_put_registry_is_stable_one_file(tmp_path):
    store = GraphStore(tmp_path)
    sha1 = store.put_registry(REG)
    sha2 = store.put_registry(REG)
    assert sha1 == sha2
    assert re.fullmatch(r"[0-9a-f]{64}", sha1)
    assert [p.name for p in sorted((tmp_path / "registry").glob("*.json"))] == [f"{sha1}.json"]


def test_get_registry_round_trips_into_a_mapping_validate_accepts(tmp_path):
    store = GraphStore(tmp_path)
    sha = store.put_registry(REG)
    got = store.get_registry(sha)
    assert got == REG
    empty = PipelineGraph.model_validate({"schema_version": 1, "nodes": [], "edges": []})
    report = validate(empty, got, roles={})
    assert isinstance(report, ValidationReport)


def _snapshot_text(schema: int, extra: dict | None = None) -> str:
    snap = {"schema": schema, "node_types": [s.model_dump(mode="json") for s in REG.values()]}
    if extra:
        snap.update(extra)
    return json.dumps(snap)


@pytest.mark.parametrize(
    "name,text",
    [
        ("truncated", _snapshot_text(1)[:40]),
        ("wrong_hash_name", _snapshot_text(1)),
        ("schema_2", _snapshot_text(2)),
        ("unknown_extra_field", _snapshot_text(1, extra={"oops": True})),
    ],
    ids=["truncated", "wrong-hash-name", "schema-2", "extra-field"],
)
def test_bad_registry_snapshots_read_as_none(tmp_path, name, text):
    store = GraphStore(tmp_path)
    file = tmp_path / "registry" / f"{'f' * 64}.json"
    file.parent.mkdir(parents=True)
    file.write_text(text, encoding="utf-8")
    assert store.get_registry("f" * 64) is None


# --- (d) per-run pointers ---------------------------------------------------


def _pointer(**kw):
    from sdlc.graph.store import RunGraphPointer  # E-77: does not exist yet

    base = dict(
        schema=1,
        run_id="feature-add-sso",
        graph_sha="a" * 64,
        layout_sha="b" * 64,
        registry_sha="c" * 64,
        roles={"architect": RoleConfig(kind="proposer", model="m1")},
        started_at=datetime(2026, 9, 19, 9, 0, tzinfo=UTC),
    )
    base.update(kw)
    return RunGraphPointer(**base)


def test_pointer_round_trips_with_roles(tmp_path):
    store = GraphStore(tmp_path)
    p = _pointer()
    store.put_pointer(p)
    got = store.get_pointer("feature-add-sso")
    assert got == p
    assert got.roles["architect"].model == "m1"


@pytest.mark.parametrize(
    "run_id",
    ["..", "a/b", ".x", "a" * 201, "run id!"],
    ids=["dotdot", "slash", "leading-dot", "too-long", "alphabet"],
)
def test_unsafe_run_ids_write_nothing_and_read_none(tmp_path, run_id):
    store = GraphStore(tmp_path)
    store.put_pointer(_pointer(run_id=run_id))
    assert list((tmp_path / "runs").rglob("*")) == []
    assert store.get_pointer(run_id) is None


def test_reused_run_id_replaces_the_pointer(tmp_path):
    store = GraphStore(tmp_path)
    store.put_pointer(_pointer(graph_sha="a" * 64))
    second = _pointer(graph_sha="2" * 64)
    store.put_pointer(second)
    assert store.get_pointer("feature-add-sso") == second
    assert len(list((tmp_path / "runs").rglob("*.json"))) == 1


def test_pointer_naming_a_missing_layout_still_returns_its_other_fields(tmp_path):
    """No layout or graph file exists for these shas; the pointer itself is
    still readable (FR-012: the pointer is never fatal)."""
    store = GraphStore(tmp_path)
    p = _pointer(layout_sha="9" * 64, registry_sha=None)
    store.put_pointer(p)
    got = store.get_pointer("feature-add-sso")
    assert got is not None
    assert got.run_id == "feature-add-sso"
    assert got.graph_sha == "a" * 64
    assert got.registry_sha is None
    assert got.roles == p.roles
    assert got.started_at == p.started_at


# --- (e) the atomic-replace helper ------------------------------------------
# Expected shape: store._atomic_replace(final: Path, data: str) -> None --
# sibling tmp file + os.replace, bounded retry (<=5 attempts) on Windows
# sharing violations, give-up logs and returns without raising.


def test_atomic_replace_retries_then_succeeds(tmp_path, monkeypatch):
    store = GraphStore(tmp_path)
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError("held by a concurrent reader")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    final = tmp_path / "latest"
    store._atomic_replace(final, "layout-sha\n")
    assert calls["n"] == 4
    assert final.read_text(encoding="utf-8") == "layout-sha\n"
    assert [p.name for p in tmp_path.iterdir()] == ["latest"]  # no .tmp left


def test_atomic_replace_gives_up_after_five_failures_logged_not_raised(
    tmp_path, monkeypatch, caplog
):
    store = GraphStore(tmp_path)
    calls = {"n": 0}

    def always_locked(src, dst):
        calls["n"] += 1
        raise PermissionError("held by a concurrent reader")

    monkeypatch.setattr(os, "replace", always_locked)
    final = tmp_path / "latest"
    store._atomic_replace(final, "layout-sha\n")  # must not raise
    assert calls["n"] == 5
    assert not final.exists()
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert list(tmp_path.iterdir()) == []  # no .tmp left behind


# --- E-77 T034 (RED): save() moves `latest`; get() prefers it (FR-019/020) ---
# save(graph) -> (sha, layout_sha) = put + move `latest`. `latest` is the
# ONLY mutable file besides the pointer: written by save() alone, never by
# put, backfill or start; a value that is absent, torn or unverifiable is
# ignored and the identity file is served instead.


def test_save_returns_pair_and_moves_latest_but_put_never_does(tmp_path):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    latest = tmp_path / sha / "latest"
    assert not latest.exists()  # put never writes `latest`
    saved_sha, layout_sha = store.save(g)
    assert (saved_sha, layout_sha) == (sha, g.document_sha())
    assert latest.read_text(encoding="utf-8").strip() == layout_sha
    moved = _graph(_moved)
    assert store.save(moved) == (sha, moved.document_sha())  # a later save moves it
    assert latest.read_text(encoding="utf-8").strip() == moved.document_sha()
    store.put(g)  # backfill of an older layout after a save...
    assert latest.read_text(encoding="utf-8").strip() == moved.document_sha()  # ...never moves it


def test_get_without_layout_serves_latest_and_with_layout_exact(tmp_path):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    moved = _graph(_moved)
    _, latest_layout = store.save(moved)
    served = store.get(sha)  # no layout: the latest layout wins
    by_id = {n.id: n for n in served.nodes}
    assert by_id["architect"].position is not None and by_id["architect"].position.x == 99
    assert store.get(sha, layout=latest_layout) == moved  # exact layout, or...
    assert store.get(sha, layout=g.document_sha()) == g  # ...any verifying one
    assert store.get(sha, layout="e" * 64) is None  # ...or None, never a fallback


_MISSING = object()


@pytest.mark.parametrize(
    "latest_text",
    [_MISSING, "", "zz-torn-not-a-sha\n", "f" * 64, "d" * 64],
    ids=["missing", "empty", "torn", "dangling-absent", "dangling-unverified"],
)
def test_a_broken_latest_falls_back_to_the_identity_file(tmp_path, latest_text):
    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    store.save(g)  # a good latest first
    latest = tmp_path / sha / "latest"
    if latest_text is _MISSING:
        latest.unlink()
    else:
        if latest_text == "d" * 64:  # names a layout that exists but cannot verify
            torn = tmp_path / sha / "layouts" / f"{latest_text}.yaml"
            torn.parent.mkdir(parents=True, exist_ok=True)
            torn.write_text("]: not a graph", encoding="utf-8")
        latest.write_text(latest_text, encoding="utf-8")
    assert store.get(sha) == g  # the identity file's graph, cosmetics included


def test_concurrent_saves_leave_both_layouts_and_one_valid_latest(tmp_path):
    import threading

    store = GraphStore(tmp_path)
    g = _graph()
    sha = store.put(g)
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(graph):
        try:
            barrier.wait()
            store.save(graph)
        except Exception as e:  # noqa: BLE001 -- reported through `errors`
            errors.append(e)

    threads = [threading.Thread(target=worker, args=graph) for graph in (g, _graph(_moved))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    layouts = {f.stem for f in _layouts(tmp_path, sha)}
    assert len(layouts) == 2  # both layout documents survived
    latest = (tmp_path / sha / "latest").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"[0-9a-f]{64}", latest)  # never torn
    assert latest in layouts  # names exactly one real, verifying layout
    assert store.get(sha) is not None  # and the store still serves the graph
