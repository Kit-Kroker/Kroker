"""The shared venv cache (B-fix): one provisioned venv per unique manifest
fingerprint under the run's worktree root, instead of one 290 MB venv per
task worktree (kroker_worker-worktrees reached 52 GB of near-identical
venvs). Pure-function tier here; the real provisioning is exercised by the
slow tier in test_qa_task_venv_provisioning.py."""

import os

from sdlc.stages.qa.venv_cache import (
    build_env,
    fingerprint,
    is_workspace,
    shared_venv_dir,
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


def test_shared_venv_dir_sits_under_the_run_root(tmp_path):
    task = _layout(tmp_path)
    fp = "abc123"
    assert shared_venv_dir(str(task), fp) == str(tmp_path / ".sdlc-venv-cache" / fp)


def test_shared_venv_dir_is_none_off_the_run_layout(tmp_path):
    task = _layout(tmp_path)
    assert shared_venv_dir(str(task), "abc123") is not None
    # deeper trees (e.g. a merge base worktree) cache beside their own
    # grandparent — siblings share, neighbours do not
    sub = tmp_path / "run-1" / "integration" / "wt"
    sub.mkdir(parents=True)
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
