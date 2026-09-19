"""Content-addressed graph store: graphs/<sha>.yaml (E-75, FR-1204).

Spec: docs/superpowers/specs/2026-09-17-graph-queries-design.md §6.

Files only -- there is no graph database and no index. A file is trusted only
after it verifies (parses, and its content_sha equals its name), so a
truncated or corrupt file is replaced rather than kept by existence. Written
by the client start helper (start.py) and backfilled by the dashboard from a
run's start input; never imported by workflow code (sandbox I/O).

E-77 adds the immutable siblings of the identity file (contracts/
records-and-store.md): per-graph layout documents under `<sha>/layouts/`,
registry snapshots under `registry/`, and per-run pointers under `runs/`.
`latest` (E-77 US5) and the pointer are the only mutable files, both via
tmp + os.replace with a bounded Windows retry.

Module-level imports stay within stdlib, sdlc.graph and sdlc.core.models
(RoleConfig, for pointer roles) -- pinned by tests/graph/test_graph_purity.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypeAlias

from ..core.models import RoleConfig
from .io import GraphSchemaError, from_yaml, to_yaml
from .model import PipelineGraph
from .node_types import NODE_TYPES, NodeTypeSpec

_log = logging.getLogger(__name__)
_SHA = re.compile(r"[0-9a-f]{64}")
_SAFE_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,200}")


def _dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class GraphStoreCorrupt(RuntimeError):
    """A stored file does not hash to its name, or to_yaml is not faithful."""


def default_root() -> Path:
    """SDLC_GRAPH_STORE, else a `graphs` sibling of the run artifact root --
    outside per-run directories, so pruning a run never deletes a graph."""
    explicit = os.environ.get("SDLC_GRAPH_STORE")
    if explicit:
        return Path(explicit).resolve()
    runs = os.environ.get("SDLC_ARTIFACT_ROOT") or os.environ.get("SDLC_EXPORT_ROOT") or "./runs"
    return (Path(runs).resolve().parent / "graphs").resolve()


# The parsed registry-snapshot document: {"schema": 1, "node_types": [...]}.
RegistrySnapshot: TypeAlias = Mapping[str, Any]


def snapshot_registry(registry: Mapping[str, NodeTypeSpec]) -> str:
    """The canonical snapshot document (E-77 FR-022): schema 1, one
    NodeTypeSpec per entry, sorted by type, defaults and port order kept."""
    specs = [registry[key].model_dump(mode="json") for key in sorted(registry)]
    return _dumps({"schema": 1, "node_types": specs})


def registry_sha(registry: Mapping[str, NodeTypeSpec]) -> str:
    return hashlib.sha256(snapshot_registry(registry).encode("utf-8")).hexdigest()


def load_registry(document: str) -> dict[str, NodeTypeSpec] | None:
    """Parse a snapshot document; None on ANY failure (FR-023: a load failure
    is 'no snapshot', never an error path)."""
    try:
        doc = json.loads(document)
    except ValueError:
        return None
    if not isinstance(doc, dict) or set(doc) != {"schema", "node_types"}:
        return None
    schema = doc["schema"]
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
        return None
    if not isinstance(doc["node_types"], list):
        return None
    specs: dict[str, NodeTypeSpec] = {}
    for entry in doc["node_types"]:
        try:
            spec = NodeTypeSpec.model_validate(entry)
        except Exception:  # noqa: BLE001 -- any bad entry is "no snapshot"
            return None
        if spec.type in specs:
            return None
        specs[spec.type] = spec
    return specs


def _safe_run_id(run_id: str) -> bool:
    """The pointer file name rule (contracts/records-and-store.md): the run id
    only when it fully matches [A-Za-z0-9._-]{1,200}, is not '.'/'..' and has
    no leading '.'."""
    if not _SAFE_RUN_ID.fullmatch(run_id):
        return False
    return run_id not in {".", ".."} and not run_id.startswith(".")


@dataclass(frozen=True)
class RunGraphPointer:
    """The per-run pointer (E-77 FR-013): which graph, layout and registry
    snapshot a client-started run pinned, plus the roles it started with.
    Written once at start, replaced atomically on id reuse, never fatal to
    read (FR-012)."""

    run_id: str
    graph_sha: str
    layout_sha: str
    registry_sha: str | None  # None when the snapshot write failed at start
    roles: dict[str, RoleConfig]
    started_at: datetime  # client clock; informational
    schema: Literal[1] = 1

    def to_json(self) -> str:
        return _dumps(
            {
                "schema": self.schema,
                "run_id": self.run_id,
                "graph_sha": self.graph_sha,
                "layout_sha": self.layout_sha,
                "registry_sha": self.registry_sha,
                "roles": {name: role.model_dump(mode="json") for name, role in self.roles.items()},
                "started_at": self.started_at.isoformat(),
            }
        )

    @classmethod
    def from_json(cls, document: str) -> RunGraphPointer | None:
        try:
            doc = json.loads(document)
        except ValueError:
            return None
        if not isinstance(doc, dict) or set(doc) != {
            "schema",
            "run_id",
            "graph_sha",
            "layout_sha",
            "registry_sha",
            "roles",
            "started_at",
        }:
            return None
        schema = doc["schema"]
        if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
            return None
        graph_sha, layout_sha = doc["graph_sha"], doc["layout_sha"]
        if not (_SHA.fullmatch(graph_sha) and _SHA.fullmatch(layout_sha)):
            return None
        registry_sha = doc["registry_sha"]
        if registry_sha is not None and not _SHA.fullmatch(registry_sha):
            return None
        roles_in = doc["roles"]
        if not isinstance(roles_in, dict):
            return None
        roles: dict[str, RoleConfig] = {}
        for name, value in roles_in.items():
            try:
                roles[str(name)] = RoleConfig.model_validate(value)
            except Exception:  # noqa: BLE001 -- any bad role is "not recorded"
                return None
        try:
            started = datetime.fromisoformat(str(doc["started_at"]))
        except ValueError:
            return None
        return cls(
            run_id=str(doc["run_id"]),
            graph_sha=graph_sha,
            layout_sha=layout_sha,
            registry_sha=registry_sha,
            roles=roles,
            started_at=started,
        )


class GraphStore:
    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self.root = Path(root).resolve() if root is not None else default_root()
        _log.debug("graph store root: %s", self.root)

    def _path(self, sha: str) -> Path:
        if not _SHA.fullmatch(sha):
            raise ValueError(f"not a graph sha: {sha!r}")
        return self.root / f"{sha}.yaml"

    def _verifies(self, path: Path, sha: str) -> bool:
        try:
            return from_yaml(path.read_text(encoding="utf-8")).content_sha() == sha
        except (OSError, GraphSchemaError):
            return False

    def _atomic_replace(self, final: Path, data: str, *, attempts: int = 5) -> None:
        """tmp + os.replace with a bounded Windows retry (contracts/
        records-and-store.md): up to `attempts` tries on sharing violations
        with ~100 ms backoff; a final failure is logged, never raised, and no
        .tmp file survives either way."""
        tmp = final.parent / f".{final.name}.{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_text(data, encoding="utf-8")
            for attempt in range(1, attempts + 1):
                try:
                    os.replace(tmp, final)
                    return
                except (PermissionError, FileExistsError):
                    if attempt == attempts:
                        _log.warning("giving up replacing %s after %d attempts", final, attempts)
                        return
                    time.sleep(min(0.1 * attempt, 0.1))
        finally:
            tmp.unlink(missing_ok=True)

    def _read_layout(self, path: Path, doc_sha: str, sha: str) -> PipelineGraph | None:
        """A layout file is trusted only if it parses, its document_sha equals
        its name and its content_sha equals its directory (E-77)."""
        try:
            graph = from_yaml(path.read_text(encoding="utf-8"))
        except (OSError, GraphSchemaError):
            return None
        if graph.document_sha() != doc_sha or graph.content_sha() != sha:
            return None
        return graph

    def _put_layout(self, graph: PipelineGraph, sha: str, text: str) -> None:
        doc = graph.document_sha()
        path = self.root / sha / "layouts" / f"{doc}.yaml"
        if self._read_layout(path, doc, sha) is not None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_replace(path, text)

    def put(self, graph: PipelineGraph) -> str:
        sha = graph.content_sha()
        text = to_yaml(graph)
        if from_yaml(text).content_sha() != sha:
            raise GraphStoreCorrupt(f"to_yaml does not round-trip graph {sha}")
        self._put_layout(graph, sha, text)  # E-77: immutable; never `latest`
        target = self._path(sha)
        if self._verifies(target, sha):
            return sha
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".{sha}.{uuid.uuid4().hex}.tmp"
        tmp.write_text(text, encoding="utf-8")
        try:
            os.replace(tmp, target)
        except (PermissionError, FileExistsError):
            # Windows: a concurrent writer or reader holds the target.
            tmp.unlink(missing_ok=True)
            if not self._verifies(target, sha):
                raise
        return sha

    def get(self, sha: str, layout: str | None = None) -> PipelineGraph | None:
        identity = self._path(sha)  # validates the sha shape
        if layout is not None:
            if not _SHA.fullmatch(layout):
                return None
            path = self.root / sha / "layouts" / f"{layout}.yaml"
            return self._read_layout(path, layout, sha)
        path = identity
        if not path.exists():
            return None
        try:
            graph = from_yaml(path.read_text(encoding="utf-8"))
        except GraphSchemaError as e:
            raise GraphStoreCorrupt(f"{path} does not parse") from e
        if graph.content_sha() != sha:
            raise GraphStoreCorrupt(f"{path} hashes to {graph.content_sha()}")
        return graph

    def put_registry(self, registry: Mapping[str, NodeTypeSpec] | None = None) -> str:
        """Snapshot `registry` (the shipped NODE_TYPES when None) under its
        content hash. The default keeps start.py free of a node_types import
        (T021's purity pin)."""
        if registry is None:
            registry = NODE_TYPES
        sha = registry_sha(registry)
        path = self.root / "registry" / f"{sha}.json"
        try:
            if hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest() == sha:
                return sha
        except OSError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_replace(path, snapshot_registry(registry))
        return sha

    def get_registry(self, registry_sha: str) -> dict[str, NodeTypeSpec] | None:
        if not _SHA.fullmatch(registry_sha):
            return None
        path = self.root / "registry" / f"{registry_sha}.json"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != registry_sha:
            return None
        return load_registry(text)

    def put_pointer(self, pointer: RunGraphPointer) -> None:
        if not _safe_run_id(pointer.run_id):
            _log.warning("unsafe run id %r: no run pointer written", pointer.run_id)
            return
        path = self.root / "runs" / f"{pointer.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_replace(path, pointer.to_json())

    def get_pointer(self, run_id: str) -> RunGraphPointer | None:
        if not _safe_run_id(run_id):
            return None
        path = self.root / "runs" / f"{run_id}.json"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        return RunGraphPointer.from_json(text)
