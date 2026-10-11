"""Oracle identity computation (round 015, Phase 3, US4, DAG B)."""

from __future__ import annotations

import hashlib
from pathlib import Path

IGNORED_DIRS = ("__pycache__", ".pytest_cache")


def oracle_identity(oracle_dir: Path | str) -> str:
    """Compute sha256:hex over all non-cached files in an oracle directory."""
    path = Path(oracle_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"oracle directory not found: {path}")

    files: list[tuple[str, Path]] = []
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(path)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        if p.suffix == ".pyc":
            continue
        files.append((rel.as_posix(), p))

    files.sort(key=lambda item: item[0])

    hasher = hashlib.sha256()
    for rel_posix, p in files:
        hasher.update(rel_posix.encode("utf-8"))
        norm_bytes = p.read_bytes().replace(b"\r\n", b"\n")
        hasher.update(norm_bytes)

    return f"sha256:{hasher.hexdigest()}"
