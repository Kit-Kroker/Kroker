"""Content-addressed graph store: graphs/<sha>.yaml (E-75, FR-1204).

Spec: docs/superpowers/specs/2026-09-17-graph-queries-design.md §6.

Files only -- there is no graph database and no index. A file is trusted only
after it verifies (parses, and its content_sha equals its name), so a
truncated or corrupt file is replaced rather than kept by existence. Written
by the client start helper (start.py) and backfilled by the dashboard from a
run's start input; never imported by workflow code (sandbox I/O).

Module-level imports stay within stdlib and sdlc.graph (pinned by
tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import PipelineGraph

_log = logging.getLogger(__name__)
_SHA = re.compile(r"[0-9a-f]{64}")


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

    def put(self, graph: PipelineGraph) -> str:
        sha = graph.content_sha()
        text = to_yaml(graph)
        if from_yaml(text).content_sha() != sha:
            raise GraphStoreCorrupt(f"to_yaml does not round-trip graph {sha}")
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

    def get(self, sha: str) -> PipelineGraph | None:
        path = self._path(sha)
        if not path.exists():
            return None
        try:
            graph = from_yaml(path.read_text(encoding="utf-8"))
        except GraphSchemaError as e:
            raise GraphStoreCorrupt(f"{path} does not parse") from e
        if graph.content_sha() != sha:
            raise GraphStoreCorrupt(f"{path} hashes to {graph.content_sha()}")
        return graph
