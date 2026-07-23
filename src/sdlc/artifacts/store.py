"""Claim-check artifact store (E-38, first FR-702 consumer).

One seam, one backend: LocalFileStore writes beside the E-32 export root.
S3 becomes a second backend behind the same Protocol when it earns its
keep. Layout: <root>/<run_id>/<subdir>/<name>; sessions and their digests
share a subdir so a human can `ls` one run's transcripts.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

from ..models import ArtifactRef

_SUBDIRS = {
    "harness_session": "sessions",
    "harness_session_digest": "sessions",
}


def ref_to_path(ref: ArtifactRef) -> Path:
    """file:// URI -> local Path (Windows-safe: file:///D:/x -> D:\\x)."""
    return Path(url2pathname(urlparse(ref.uri).path))


class ArtifactStore(Protocol):
    def put(self, kind: str, run_id: str, name: str,
            data: bytes) -> ArtifactRef: ...
    def delete(self, ref: ArtifactRef) -> None: ...


class LocalFileStore:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = Path(
            root
            or os.environ.get("SDLC_ARTIFACT_ROOT")
            or os.environ.get("SDLC_EXPORT_ROOT", "./runs"))

    def put(self, kind: str, run_id: str, name: str,
            data: bytes) -> ArtifactRef:
        path = self.root / run_id / _SUBDIRS.get(kind, kind) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ArtifactRef(
            kind=kind, uri=path.resolve().as_uri(),
            sha256=hashlib.sha256(data).hexdigest())

    def delete(self, ref: ArtifactRef) -> None:
        ref_to_path(ref).unlink(missing_ok=True)
