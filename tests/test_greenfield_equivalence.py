"""DS8: on an empty base the scoped verdict equals the whole-tree verdict."""

import os
import subprocess
import sys

import pytest

from sdlc.stages.qa.activities import _SCAN_SKIP_DIRS, scan_paths
from tests.test_diff_scoped_fixture_tier import EVAL, commit, gate, git, write

pytestmark = [pytest.mark.slow, pytest.mark.asyncio]

TREES = {
    "clean": {
        "app.py": "def f():\n    return 1\n",
        "tests/test_app.py": "def test_f():\n    pass\n",
    },
    "lint": {"app.py": "import os\n", "tests/test_app.py": "def test_f():\n    pass\n"},
    "critical": {
        "app.py": f"x = {EVAL}'1')\n",
        "tests/test_app.py": "def test_f():\n    pass\n",
    },
    "failing": {"app.py": "x = 1\n", "tests/test_app.py": "def test_f():\n    assert False\n"},
    "no_tests": {"app.py": "x = 1\n"},
}


def whole_tree_verdict(root) -> dict[str, bool]:
    """The pre-change semantics, recomputed as an oracle: tree-wide lint,
    tree-wide scan (walk minus skip dirs), whole-suite pytest exit 0."""

    def run(*args: str) -> int:
        return subprocess.run(
            [sys.executable, "-m", *args], cwd=root, capture_output=True, timeout=60
        ).returncode

    paths: list[str] = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in _SCAN_SKIP_DIRS]
        paths.extend(os.path.relpath(os.path.join(d, f), root) for f in files)
    scan = scan_paths(str(root), paths)
    return {
        "build_integration_green": run("pytest", "-q", "-p", "no:cacheprovider") == 0,
        "lint_clean": run("ruff", "check", "--no-cache", ".") == 0,
        "security_scan_collected": True,
        "security_no_critical": scan.critical == 0,
    }


@pytest.mark.parametrize("name", sorted(TREES))
async def test_empty_base_scoped_verdict_equals_whole_tree(name, tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_WORKTREES_ROOT", str(tmp_path / "wts"))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, ".gitignore", ".sdlc-venv/\n.sdlc-junit*.xml\ncoverage.xml\n")
    base = commit(r, "empty base")  # no source: the greenfield case
    write(r, "pyproject.toml", "[project]\nname = 'g'\nversion = '0.0.0'\n")
    write(r, "ruff.toml", '[lint]\nselect = ["F401"]\n')
    for rel, body in TREES[name].items():
        write(r, rel, body)
    commit(r, "the run's output")
    scoped, *_ = await gate(r, base)
    assert scoped == whole_tree_verdict(r), name
