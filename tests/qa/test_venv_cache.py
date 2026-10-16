"""The shared venv cache (B-fix): one provisioned venv per unique manifest
fingerprint under the RUN's directory, instead of one 290 MB venv per
task worktree (kroker_worker-worktrees reached 52 GB of near-identical
venvs). Pure-function tier here; the real provisioning is exercised by the
slow tier in test_qa_task_venv_provisioning.py."""

import os
import time

import pytest

from sdlc.stages.qa.venv_cache import (
    LOCK_STALE_S,
    build_env,
    dir_lock,
    fingerprint,
    is_workspace,
    marker_ok,
    shared_venv_dir,
    touch_marker,
)

PYPROJECT = "[project]\nname = 'x'\nversion = '0.0.0'\n"
WORKSPACE_PYPROJECT = "[tool.uv.workspace]\nmembers = ['pkgs/a']\n\n" + PYPROJECT


def _layout(tmp_path):
    """A <root>/<run>/<task> worktree layout, the shape integration.py
    creates under /tmp/sdlc/worktrees."""
    task = tmp_path / "run-1" / "T01"
    task.mkdir(parents=True)
    return task


def test_fingerprint_is_content_addressed(tmp_path):
    task = _layout(tmp_path)
    (task / "requirements.txt").write_text("a\n", encoding="utf-8")
    first = fingerprint(str(task))
    assert first is not None

    (task / "requirements.txt").write_text("a\nb\n", encoding="utf-8")
    assert fingerprint(str(task)) != first

    # an unrelated file must not move the fingerprint
    (task / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert fingerprint(str(task)) == fingerprint(str(task))


def test_fingerprint_is_none_without_manifests(tmp_path):
    task = _layout(tmp_path)
    assert fingerprint(str(task)) is None


def test_fingerprint_covers_every_manifest(tmp_path):
    task = _layout(tmp_path)
    (task / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    base = fingerprint(str(task))
    (task / "uv.lock").write_text("lock\n", encoding="utf-8")
    assert fingerprint(str(task)) != base


def test_shared_venv_dir_is_scoped_to_the_run_dir(tmp_path):
    task = _layout(tmp_path)
    fp = "abc123"
    # INSIDE the run dir: produced manifests are untrusted input, so the
    # venv they build must never be reachable from another run (the
    # security shape in venv_cache's module docstring).
    assert shared_venv_dir(str(task), fp) == str(tmp_path / "run-1" / ".sdlc-venv-cache" / fp)


def test_shared_venv_dir_is_none_off_the_run_layout(tmp_path):
    task = _layout(tmp_path)
    assert shared_venv_dir(str(task), "abc123") is not None
    # every child of the run dir shares the run's cache
    sub = tmp_path / "run-1" / "integration"
    sub.mkdir()
    assert shared_venv_dir(str(sub), "abc123") == str(
        tmp_path / "run-1" / ".sdlc-venv-cache" / "abc123"
    )
    # pathologically shallow inputs (worktree at a filesystem top) refuse
    assert shared_venv_dir("/", "abc123") is None


def test_is_workspace_detection(tmp_path):
    task = _layout(tmp_path)
    assert is_workspace(str(task)) is False

    (task / "pyproject.toml").write_text(WORKSPACE_PYPROJECT, encoding="utf-8")
    assert is_workspace(str(task)) is True


def test_build_env_points_the_project_at_the_worktree(tmp_path):
    venv = tmp_path / "cache" / "fp1"
    env = build_env(str(venv), str(tmp_path / "T01"), {"PATH": "/usr/bin"})

    bin_dir = "Scripts" if os.name == "nt" else "bin"
    assert env["VIRTUAL_ENV"] == str(venv)
    assert env["PATH"].startswith(str(venv / bin_dir) + os.pathsep)
    assert str(tmp_path / "T01") in env["PYTHONPATH"].split(os.pathsep)
    assert str(tmp_path / "T01" / "src") in env["PYTHONPATH"].split(os.pathsep)


def test_build_env_prepends_to_existing_pythonpath(tmp_path):
    env = build_env(
        str(tmp_path / "v"), str(tmp_path / "T01"), {"PATH": "", "PYTHONPATH": "/keep/me"}
    )
    assert env["PYTHONPATH"].endswith(os.pathsep + "/keep/me")


def test_marker_checks_the_fingerprint_not_just_existence(tmp_path):
    venv = tmp_path / "v"
    venv.mkdir()
    assert marker_ok(str(venv), "fp1") is False

    touch_marker(str(venv))  # no marker yet: a no-op, not a crash
    assert marker_ok(str(venv), "fp1") is False

    (venv / ".provisioned").write_text("fp1", encoding="utf-8")
    assert marker_ok(str(venv), "fp1") is True
    assert marker_ok(str(venv), "fp2") is False
    # a marker written for another fingerprint must not pass as current
    old = time.time() - 3600
    os.utime((venv / ".provisioned"), (old, old))
    touch_marker(str(venv))
    assert os.path.getmtime(venv / ".provisioned") > old


@pytest.mark.asyncio
async def test_dir_lock_is_exclusive_and_owned(tmp_path):
    lock = str(tmp_path / "v.lock")

    async with dir_lock(lock, timeout_s=1):
        # a second holder cannot take it
        with pytest.raises(TimeoutError):
            async with dir_lock(lock, timeout_s=0.5):
                pass

    # released on exit
    async with dir_lock(lock, timeout_s=1):
        pass
    assert not os.path.exists(lock)


@pytest.mark.asyncio
async def test_dir_lock_steals_a_crashed_holder(tmp_path):
    lock = str(tmp_path / "v.lock")
    os.makedirs(lock)
    crasher = os.path.join(lock, "deadbeef")
    (open(crasher, "w")).close()
    old = time.time() - LOCK_STALE_S - 60
    os.utime(crasher, (old, old))

    async with dir_lock(lock, timeout_s=5):
        # the crashed holder's file is gone and ours is in place
        entries = os.listdir(lock)
        assert len(entries) == 1 and entries[0] != "deadbeef"

    assert not os.path.exists(lock)
