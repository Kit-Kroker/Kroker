"""Shared, fingerprint-keyed venv cache for produced-project provisioning.

One ~290 MB ``.sdlc-venv`` per task worktree was the single largest
contributor to worktree-volume growth (``kroker_worker-worktrees`` reached
52 GB, almost entirely near-identical venv copies). Tasks of one run
provision the SAME dependency set over and over, so the venv now lives
once per unique manifest fingerprint under the RUN's directory and every
task's environment points at it.

Security shape (why the cache is run-scoped, not global):

- Produced manifests are UNTRUSTED input (the produced repo is coding-
  agent output — the same trust level that puts harnesses behind
  sandboxes). An install can execute arbitrary code, so a poisoned venv
  is a real outcome; scoping the cache to the run whose manifests built
  it bounds that blast radius to the run itself. The cache dies with the
  run (the A-terminal teardown removes the run dir wholesale) and the
  TTL below bounds what a killed run leaves behind.
- The produced project itself is NEVER installed into the shared venv.
  An editable install would leave that task's source dir on the shared
  venv's sys.path for every later task; importability comes from
  PYTHONPATH instead, which covers flat and src layouts without any
  per-task mutation of the venv.
- Install shells run with an allowlisted environment (see
  activities._provision_env) — the worker's secrets never reach
  install-time code. (Pre-existing behaviour ran those installs with the
  full worker env; the shared cache keeps the new discipline.)

A uv workspace (``[tool.uv.workspace]`` in pyproject.toml) keeps the
legacy per-worktree venv: uv installs workspace members into the venv
(as editables pointing at that one task's tree), so there is no
deps-only expression of a workspace to share.

Provisioning under contention goes through a mkdir-based directory lock
(atomic on every filesystem the worker and the host tests run on, no
third-party dependency). The holder heartbeats a uuid file; a lock whose
heartbeat is stale is stolen, and release removes the lock only when it
is still ours. A caller that cannot take the lock in time falls back to
the legacy private venv rather than failing the task.

Pure module: nothing here spawns a subprocess; the shell steps live in
stages/qa/activities.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
import uuid
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
# Cache entries untouched for this long are removed on the next
# provisioning (best-effort, under the entry's own lock). The A-terminal
# teardown normally removes the whole run dir; this bounds what a killed
# run leaves behind.
CACHE_TTL_S: Final = 14 * 24 * 3600
# A lock whose heartbeat is older than this belongs to a crashed holder
# and is stolen. Must comfortably exceed the longest legitimate gap
# between heartbeats (LOCK_HEARTBEAT_S), not the hold duration — the
# heartbeat is what decouples staleness from hold time.
LOCK_STALE_S: Final = 15 * 60
LOCK_HEARTBEAT_S: Final = 30.0
# A lock dir with no holder file at all is live only while this fresh
# (mkdir -> write-holder is a same-thread pair; the window exists for a
# holder that crashed in between).
LOCK_EMPTY_FRESH_S: Final = 60.0

MARKER_NAME: Final = ".provisioned"


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
            with open(path, "rb") as f:
                content = f.read()
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
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    return "[tool.uv.workspace]" in text


def shared_venv_dir(worktree: str, fp: str) -> str | None:
    """The cache directory for this fingerprint, or None when the worktree
    has no parent to scope under.

    The cache sits INSIDE the run dir (``<root>/<run>/.sdlc-venv-cache``),
    not beside the run dir: the manifests that build the venv are
    untrusted input, so the venv must never outlive — or be reachable
    from — a different run (see the security shape in the module
    docstring). Cross-task sharing within the run is the win; the
    A-terminal teardown removes the cache with the run."""
    parent = os.path.dirname(os.path.abspath(worktree))
    if not parent or parent == os.path.abspath(worktree):
        return None
    return os.path.join(parent, CACHE_DIR_NAME, fp)


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


def marker_ok(venv_dir: str, fp: str) -> bool:
    """Whether the venv carries a provisioned marker FOR THIS
    fingerprint. The marker's content is part of the check, not just its
    existence: a venv provisioned from a different manifest set must
    never pass as current."""
    try:
        with open(os.path.join(venv_dir, MARKER_NAME), encoding="utf-8") as f:
            return f.read(32).strip() == fp
    except OSError:
        return False


def touch_marker(venv_dir: str) -> None:
    """Refresh the marker's mtime — the liveness signal gc_cache reads.
    Best-effort: a vanished venv is handled by the caller's existence
    check, not here."""
    try:
        os.utime(os.path.join(venv_dir, MARKER_NAME))
    except OSError:
        pass


@contextlib.asynccontextmanager
async def dir_lock(
    lock_dir: str, *, poll_s: float = 0.2, timeout_s: float = 600.0
) -> AsyncIterator[None]:
    """Cross-process mutual exclusion around cache provisioning. mkdir is
    the lock: atomic everywhere, no third-party dependency. The holder
    writes a uuid file and heartbeats it, so staleness is decoupled from
    hold duration: a lock whose heartbeat is older than LOCK_STALE_S (or
    an empty one older than LOCK_EMPTY_FRESH_S) is a crashed holder and
    is stolen. Release removes the lock only when our uuid is still the
    one in it — a stolen holder must not delete its thief's lock. Raises
    TimeoutError so the caller can fall back to a private venv."""
    deadline = time.monotonic() + timeout_s
    os.makedirs(os.path.dirname(lock_dir) or ".", exist_ok=True)
    holder = uuid.uuid4().hex
    while True:
        try:
            os.mkdir(lock_dir)
            _write_holder(lock_dir, holder)
            break
        except FileExistsError as err:
            if not _lock_is_live(lock_dir):
                shutil.rmtree(lock_dir, ignore_errors=True)
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"lock not acquired in {timeout_s}s: {lock_dir}") from err
            await asyncio.sleep(poll_s)
    heartbeat_file = os.path.join(lock_dir, holder)
    stop = asyncio.Event()

    async def heartbeat() -> None:
        while not stop.is_set():
            try:
                with open(heartbeat_file, "w", encoding="utf-8") as f:
                    f.write(holder)
            except OSError:
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=LOCK_HEARTBEAT_S)
            except TimeoutError:
                pass

    task = asyncio.create_task(heartbeat())
    try:
        yield
    finally:
        stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if _read_holder(lock_dir) == holder:
            shutil.rmtree(lock_dir, ignore_errors=True)


def _write_holder(lock_dir: str, holder: str) -> None:
    try:
        with open(os.path.join(lock_dir, holder), "w", encoding="utf-8") as f:
            f.write(holder)
    except OSError:
        pass  # the emptiness rule below covers a holder that never wrote


def _read_holder(lock_dir: str) -> str | None:
    try:
        entries = [e for e in os.listdir(lock_dir) if not e.startswith(".")]
    except OSError:
        return None
    return entries[0] if entries else None


def _lock_is_live(lock_dir: str) -> bool:
    entries = []
    try:
        entries = os.listdir(lock_dir)
        mtime = os.path.getmtime(lock_dir)
    except OSError:
        return True  # released between the calls; the retry will mkdir
    if not entries:
        return time.time() - mtime <= LOCK_EMPTY_FRESH_S
    newest = max((os.path.getmtime(os.path.join(lock_dir, e)) for e in entries), default=0.0)
    return time.time() - newest <= LOCK_STALE_S


def gc_cache(cache_root: str, keep: str, *, now: float | None = None) -> None:
    """Remove cache entries (and their lock dirs) untouched for longer
    than CACHE_TTL_S, except ``keep``. Each removal takes the entry's own
    lock first, so a concurrent provisioning is never raced mid-install.
    Best-effort by contract: any error leaves the entry for the next
    call."""
    if now is None:
        now = time.time()
    try:
        entries = list(os.scandir(cache_root))
    except OSError:
        return
    for entry in entries:
        if entry.path == keep or not entry.is_dir():
            continue
        try:
            if now - entry.stat().st_mtime <= CACHE_TTL_S:
                continue
        except OSError:
            continue
        if entry.path.endswith(".lock"):
            target = None  # a stale lock dir: remove it, no lock to take
        else:
            target = entry.path + ".lock"
            try:
                os.mkdir(target)
            except FileExistsError:
                continue  # someone is provisioning it; leave it be
        try:
            shutil.rmtree(entry.path, ignore_errors=True)
        finally:
            if target is not None:
                shutil.rmtree(target, ignore_errors=True)
