"""A NON-editable install must find the registry.

The local install is editable (__editable__.ai_sdlc_temporal-0.1.0.pth), so
sdlc resolves to src/sdlc and any __file__-relative walk lands on the repo
root by accident. `pip install .` puts the package in site-packages, where
that accident does not happen — which is why the image could not boot. Slow
(builds a venv); marked so it can be deselected.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_dockerfile_ships_the_registry_explicitly():
    """The two Dockerfile lines are load-bearing and have no other guard.
    Deleting ENV SDLC_AGENTS_DIR breaks zero tests today because repo-root
    discovery silently rescues it in the image (WORKDIR /app + pyproject.toml
    + agents/), so this source-inspection test is the only thing that catches
    a future PR removing the explicit, deterministic prod path."""
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY agents ./agents" in text
    assert "ENV SDLC_AGENTS_DIR=" in text


@pytest.mark.slow
def test_non_editable_install_resolves_registry_via_env(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if sys.platform == "win32"
                 else "bin/python")
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(REPO)],
                   check=True)

    probe = "from sdlc.agents.loader import load_registry; load_registry()"
    # cwd=tmp_path: OUTSIDE the repo, so discovery cannot rescue us and only
    # SDLC_AGENTS_DIR can work.
    done = subprocess.run(
        [str(py), "-c", probe], cwd=tmp_path, capture_output=True, text=True,
        env={"SDLC_AGENTS_DIR": str(REPO / "agents"), "PATH": ""},
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.slow
def test_non_editable_install_without_env_fails_closed(tmp_path):
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if sys.platform == "win32"
                 else "bin/python")
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(REPO)],
                   check=True)

    probe = "from sdlc.agents.loader import load_registry; load_registry()"
    done = subprocess.run([str(py), "-c", probe], cwd=tmp_path,
                          capture_output=True, text=True, env={"PATH": ""})
    assert done.returncode != 0
    assert "SDLC_AGENTS_DIR" in done.stderr        # names the mechanism
    assert "FileNotFoundError" not in done.stderr  # fails closed, deliberately
