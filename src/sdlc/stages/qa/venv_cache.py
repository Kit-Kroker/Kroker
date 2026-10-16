"""Shared, fingerprint-keyed venv cache for produced-project provisioning.

One ~290 MB ``.sdlc-venv`` per task worktree was the single largest
contributor to worktree-volume growth (``kroker_worker-worktrees`` reached
52 GB, almost entirely near-identical venv copies). Tasks of one run
provision the SAME dependency set over and over, so the venv now lives
once per unique manifest fingerprint under the run's worktree root and
every task's environment points at it.

Two rules keep the shared venv safe to share:

- The produced project itself is NEVER installed into it. An editable
  install leaves that task's source dir on the shared venv's sys.path for
  every later task; importability comes from PYTHONPATH instead, which
  covers flat and src layouts without any per-task mutation of the venv.
- A uv workspace (``[tool.uv.workspace]`` in pyproject.toml) keeps the
  legacy per-worktree venv: uv installs workspace members into the venv
  (as editables pointing at that one task's tree), so there is no
  deps-only expression of a workspace to share.

Provisioning under contention goes through a mkdir-based directory lock
(atomic on every filesystem the worker and the host tests run on, no
third-party dependency). A lock older than ``LOCK_STALE_S`` is stolen —
its holder crashed mid-install. A caller that cannot take the lock in
time falls back to the legacy private venv rather than failing the task.

Pure module: nothing here spawns a subprocess; the shell steps live in
stages/qa/activities.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from collections.abc import AsyncIterator, Mapping
from typing import Final

# The manifests a shared venv's contents depend on. requirements paths are
# qa/activities.py's _REQUIREMENTS_FILES — duplicated here (not imported)
# because that module imports this one.
MANIFEST_FILES: Final = (
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements/base.txt",
    "requirements/dev.txt",
)

CACHE_DIR_NAME: Final = ".sdlc-venv-cache"
# Sibling cache entries untouched for this long are removed on the next
# provisioning (best-effort) — a run root outlives its run, and without a
# bound the cache would rebuild the same leak one level up.
CACHE_TTL_S: Final = 14 * 24 * 3600
# A lock dir older than this belongs to a crashed holder and is stolen.
LOCK_STALE_S: Final = 15 * 60


def fingerprint(worktree: str) -> str | None:
    """A stable content hash of the worktree's dependency manifests, or
    None when the worktree carries none (nothing to share over — and the
    legacy venv would hold only pytest/ruff, which is cheap to keep
    private)."""
    import hashlib

    digest = hashlib.sha256()
    seen = False
    for name in MANIFEST_FILES:
        path = os.path.join(worktree, name)
        try:
            content = open(path, "rb").read()
        except OSError:
            continue
        seen = True
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(content)
        digest.update(b"\x00")
    return digest.hexdigest()[:16] if seen else None


def is_workspace(worktree: str) -> bool:
    """True when pyproject.toml declares a uv workspace — the one shape
    the shared cache cannot express deps-only (see module docstring)."""
    path = os.path.join(worktree, "pyproject.toml")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return False
    return "[tool.uv.workspace]" in text


def shared_venv_dir(worktree: str, fp: str) -> str | None:
    """The cache directory for this fingerprint, or None when the worktree
    does not sit at ``<root>/<run>/<task>`` (the layout integration.py
    creates under /tmp/sdlc/worktrees). An unexpected layout falls back to
    the legacy per-worktree venv rather than guessing at a shared spot —
    e.g. the merge stage's base worktree and the benchmark scratch trees
    must never share a cache with a run they do not belong to."""
    parent = os.path.dirname(os.path.abspath(worktree))
    root = os.path.dirname(parent)
    if not root or root == parent or root == os.path.abspath(worktree):
        return None
    return os.path.join(root, CACHE_DIR_NAME, fp)


def build_env(venv_dir: str, worktree: str, base: Mapping[str, str]) -> dict[str, str]:
    """The environment for running the produced project against a venv it
    is NOT installed into: the venv owns PATH/VIRTUAL_ENV, the worktree
    owns importability via PYTHONPATH (root first, then src — flat and
    src layouts both resolve)."""
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    env = dict(base)
    env["PATH"] = os.path.join(venv_dir, bin_dir) + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_dir
    project_paths = [worktree, os.path.join(worktree, "src")]
    existing = env.get("PYTHONPATH")
    if existing:
        project_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(project_paths)
    env.pop("PYTHONHOME", None)
    return env


@contextlib.asynccontextmanager
async def dir_lock(
    lock_dir: str, *, poll_s: float = 0.2, timeout_s: float = 600.0
) -> AsyncIterator[None]:
    """Cross-process mutual exclusion around cache provisioning. mkdir is
    the lock: atomic everywhere, no third-party dependency. Raises
    TimeoutError so the caller can fall back to a private venv; a lock
    directory older than LOCK_STALE_S is stolen (crashed holder)."""
    deadline = time.monotonic() + timeout_s
    os.makedirs(os.path.dirname(lock_dir) or ".", exist_ok=True)
    while True:
        try:
            os.mkdir(lock_dir)
            break
        except FileExistsError as err:
            try:
                age = time.time() - os.path.getmtime(lock_dir)
            except OSError:
                age = 0.0  # released between the two calls; just retry
            if age > LOCK_STALE_S:
                shutil.rmtree(lock_dir, ignore_errors=True)
            if time.monotonic() > deadline:
                raise TimeoutError(f"lock not acquired in {timeout_s}s: {lock_dir}") from err
            await asyncio.sleep(poll_s)
    try:
        yield
    finally:
        shutil.rmtree(lock_dir, ignore_errors=True)


def gc_cache(cache_root: str, keep: str, *, now: float | None = None) -> None:
    """Remove cache entries (and their lock dirs) untouched for longer
    than CACHE_TTL_S, except ``keep``. Best-effort by contract: any error
    leaves the entry for the next call."""
    if now is None:
        now = time.time()
    try:
        entries = list(os.scandir(cache_root))
    except OSError:
        return
    for entry in entries:
        if entry.path == keep:
            continue
        try:
            if now - entry.stat().st_mtime <= CACHE_TTL_S:
                continue
        except OSError:
            continue
        shutil.rmtree(entry.path, ignore_errors=True)
