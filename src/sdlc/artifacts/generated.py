"""Shared definitions of generated artifacts and cache directories (017 T004, US5, FR-050)."""

from __future__ import annotations

GENERATED_DIRS: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".tox",
    }
)


def is_generated(path: str) -> bool:
    """Return True if path points to a generated artifact or is within a generated/cache directory.

    Matching is on normalized forward-slash path segments: a path is generated if
    any segment is in GENERATED_DIRS, or matches *.egg-info, or the file ends .pyc.
    """
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return False
    if normalized.endswith(".pyc"):
        return True
    parts = normalized.split("/")
    for part in parts:
        if part in GENERATED_DIRS or part.endswith(".egg-info"):
            return True
    return False
