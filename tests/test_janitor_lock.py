"""The janitor sweep takes a non-blocking advisory lock (024 T015; research R10).

Two processes sharing one worktree volume (a ``core``/``all`` worker and a ``harness``
replica) must not sweep at once. ``sweep_once`` holds ``flock(LOCK_EX | LOCK_NB)`` on
``<worktrees_root>/.janitor.lock`` for its body: lock held elsewhere -> skip with an
INFO log and return ``[]``; lock free -> sweep as before; lock released afterwards.

RED until T016. A stale run dir is planted in every case so a sweep that ignores the
lock is observable (``cleanup_run_dir`` is called), not vacuously empty.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

STALE = "run-stale"
LOCK_NAME = ".janitor.lock"


class _Env:
    def __init__(self, root: Path, cleaned: list[str]) -> None:
        self.root = root
        self.cleaned = cleaned

    @property
    def lock_path(self) -> Path:
        return self.root / LOCK_NAME


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Env:
    from sdlc.vcs import janitor

    root = tmp_path / "worktrees"
    (root / STALE).mkdir(parents=True)
    old = time.time() - 3600
    os.utime(root / STALE, (old, old))
    cleaned: list[str] = []

    def fake_cleanup(run_id: str) -> Any:
        cleaned.append(run_id)
        return SimpleNamespace(errors=[])

    async def no_running(_client: Any) -> set[str]:
        return set()

    monkeypatch.setattr(janitor, "_worktrees_root", lambda: str(root))
    monkeypatch.setattr(janitor, "cleanup_run_dir", fake_cleanup)
    monkeypatch.setattr(janitor, "open_workflow_ids", no_running)
    return _Env(root, cleaned)


@contextmanager
def _holding(path: Path) -> Iterator[None]:
    """Hold LOCK_EX on ``path`` through a separate open file description (a second
    ``open`` of the same file conflicts with the sweeper's even inside one process)."""
    with open(path, "a+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(held.fileno(), fcntl.LOCK_UN)


def _sweep() -> list[str]:
    from sdlc.vcs.janitor import sweep_once

    return asyncio.run(sweep_once(object(), grace_s=60))


def test_held_lock_skips_the_sweep_and_logs_at_info(
    env: _Env, caplog: pytest.LogCaptureFixture
) -> None:
    env.lock_path.touch()
    with _holding(env.lock_path), caplog.at_level(logging.INFO, logger="sdlc.vcs.janitor"):
        swept = _sweep()

    assert swept == []
    assert env.cleaned == [], "sweep ran although another process held the janitor lock"
    skips = [
        r
        for r in caplog.records
        if r.name == "sdlc.vcs.janitor"
        and r.levelno >= logging.INFO
        and "janitor" in r.getMessage().lower()
        and "skip" in r.getMessage().lower()
    ]
    assert skips, [r.getMessage() for r in caplog.records]


def test_free_lock_sweeps_the_stale_dir_and_creates_the_lock_file(env: _Env) -> None:
    assert not env.lock_path.exists()

    swept = _sweep()

    assert swept == [STALE]
    assert env.cleaned == [STALE]
    assert env.lock_path.exists(), "the sweep should create <root>/.janitor.lock"


def test_lock_file_is_not_mistaken_for_a_run_dir(env: _Env) -> None:
    env.lock_path.touch()

    swept = _sweep()

    assert LOCK_NAME not in swept
    assert LOCK_NAME not in env.cleaned


def test_lock_is_released_after_a_sweep(env: _Env) -> None:
    _sweep()
    assert env.lock_path.exists(), "sweep should have created the lock file"

    with open(env.lock_path, "a+") as probe:
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # BlockingIOError if leaked
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)


def test_lock_is_released_when_the_sweep_body_raises(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.vcs import janitor

    def boom(_run_id: str) -> Any:
        raise RuntimeError("cleanup exploded")

    monkeypatch.setattr(janitor, "cleanup_run_dir", boom)

    with pytest.raises(RuntimeError, match="cleanup exploded"):
        _sweep()

    assert env.lock_path.exists(), "sweep should have created the lock file"
    with open(env.lock_path, "a+") as probe:
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)


# ------------------------------------------------- chaos pass (024 T015, edge cases)


def _assert_lock_is_free(path: Path) -> None:
    with open(path, "a+") as probe:
        fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # BlockingIOError if leaked
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)


def test_lock_is_released_when_listing_running_workflows_raises(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The first IO inside the locked body fails (Temporal unreachable): no orphaned lock.
    from sdlc.vcs import janitor

    async def temporal_down(_client: Any) -> set[str]:
        raise RuntimeError("temporal unreachable")

    monkeypatch.setattr(janitor, "open_workflow_ids", temporal_down)

    with pytest.raises(RuntimeError, match="temporal unreachable"):
        _sweep()

    assert env.cleaned == []
    assert env.lock_path.exists()
    _assert_lock_is_free(env.lock_path)


@pytest.mark.parametrize("held", [False, True], ids=["free", "held"])
def test_lock_file_lives_exactly_in_the_resolved_root(
    env: _Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, held: bool
) -> None:
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    if held:
        env.lock_path.touch()

    if held:
        with _holding(env.lock_path):
            _sweep()
    else:
        _sweep()

    assert env.lock_path == env.root / ".janitor.lock"
    assert env.lock_path.is_file()
    assert sorted(os.listdir(env.root)) == sorted([STALE, LOCK_NAME])
    assert os.listdir(elsewhere) == [], "the lock file must not be created in the cwd"


def test_held_lock_fails_fast_before_listing_running_workflows(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.vcs import janitor

    listed: list[Any] = []

    async def recording(client: Any) -> set[str]:
        listed.append(client)
        return set()

    monkeypatch.setattr(janitor, "open_workflow_ids", recording)
    env.lock_path.touch()

    with _holding(env.lock_path):
        swept = _sweep()

    assert swept == []
    assert listed == [], "a skipped sweep must not do any Temporal IO"
    assert env.cleaned == []


def test_sequential_sweeps_both_run_the_lock_is_not_kept_by_the_first(env: _Env) -> None:
    first = _sweep()
    assert first == [STALE]

    second_dir = env.root / "run-stale-2"
    second_dir.mkdir()
    old = time.time() - 3600
    os.utime(second_dir, (old, old))

    second = _sweep()

    assert sorted(second) == sorted([STALE, "run-stale-2"]), (
        "second sweep was skipped by a leaked lock"
    )
    assert env.cleaned.count("run-stale-2") == 1
    _assert_lock_is_free(env.lock_path)


def test_sequential_sweeps_in_one_event_loop_both_run(env: _Env) -> None:
    from sdlc.vcs.janitor import sweep_once

    async def twice() -> tuple[list[str], list[str]]:
        return (
            await sweep_once(object(), grace_s=60),
            await sweep_once(object(), grace_s=60),
        )

    first, second = asyncio.run(twice())

    assert first == [STALE]
    assert second == [STALE], "the second sweep in the same process was skipped by a leaked lock"
