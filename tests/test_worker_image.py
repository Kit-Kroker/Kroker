"""The worker image carries the binaries the activities shell out to.

`open_pull_request` execs `gh`, and it is the last step of a feature run: a
worker image without it fails *after* build, lint, security, review and every
gate have already passed. Nothing else catches that — the activity's unit
coverage stubs `gh` on PATH by design, and no e2e reaches the real binary — so
the check has to be against the built image itself.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE_TAG = "sdlc-worker:imagetest"

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(shutil.which("docker") is None,
                       reason="docker not on PATH"),
]


@pytest.fixture(scope="module")
def worker_image() -> str:
    build = subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, "."],
        cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if build.returncode != 0:
        pytest.fail(f"docker build failed:\n{build.stderr[-4000:]}")
    return IMAGE_TAG


def test_gh_is_installed_and_runnable(worker_image):
    run = subprocess.run(
        ["docker", "run", "--rm", worker_image, "gh", "--version"],
        capture_output=True, encoding="utf-8", errors="replace")
    assert run.returncode == 0, run.stderr
    assert "gh version" in run.stdout


def test_git_is_configured_to_get_credentials_from_gh(worker_image):
    """`open_pull_request` runs a plain `git push` before it calls `gh`, so
    the token in GH_TOKEN has to reach git as well. The credential helper is
    baked into the image; without it the push prompts (and, with stdin closed,
    fails) on any https remote."""
    run = subprocess.run(
        ["docker", "run", "--rm", worker_image,
         "git", "config", "--global", "--get",
         "credential.https://github.com.helper"],
        capture_output=True, encoding="utf-8", errors="replace")
    assert run.returncode == 0, run.stderr
    assert "gh auth git-credential" in run.stdout
