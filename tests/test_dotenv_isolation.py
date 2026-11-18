"""026 T025 (FR-030, research R7): a repo-root .env must not leak into tests.

The rider: `load_dotenv()` with no path walks up from the CALLING file, not the
CWD (python-dotenv 1.2.2), and uses override=False. So an operator's .env at
the repo root refills any variable a test has unset, and a test that spawns the
`sdlc` CLI inherits it. That is how a developer's KROKER_HARNESS_QUEUE leaked
into CLI-spawning tests (research R7).

Future contract (T026): tests/conftest.py sets PYTHON_DOTENV_DISABLED=1 at
import, so every child spawned from os.environ is immune. python-dotenv honors
that flag in load_dotenv.

Each test below spawns a child whose CWD holds a .env with two variables, after
removing both from the child's environment, so the .env is the only source. The
first test fails today: the child prints the polluted value. The complement
passes today and must keep passing: with the flag set explicitly, the .env is
ignored.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

POLLUTED = {
    "KROKER_HARNESS_QUEUE": "polluted",
    "SDLC_RUNS_ROOT": "/polluted/by/env",
}

CHILD = (
    "import os, dotenv\n"
    "dotenv.load_dotenv(dotenv.find_dotenv(usecwd=True))\n"
    "print(os.environ.get('KROKER_HARNESS_QUEUE'))\n"
    "print(os.environ.get('SDLC_RUNS_ROOT'))\n"
)


def _write_polluted_dotenv(root) -> None:
    (root / ".env").write_text(
        "".join(f"{k}={v}\n" for k, v in POLLUTED.items()),
        encoding="utf-8",
    )


def _child_env(**overrides: str) -> dict[str, str]:
    """A copy of this process's environment, with the polluted variables
    unset (the R7 scenario: unsetting lets .env refill them) and any overrides
    applied."""
    env = dict(os.environ)
    for key in POLLUTED:
        env.pop(key, None)
    env.update(overrides)
    return env


def _run_child(cwd, env) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.splitlines()


def test_a_repo_root_dotenv_does_not_leak_into_a_spawned_child(tmp_path):
    """Both polluted variables must read None in a child spawned from this
    process's environment. RED today: the child prints 'polluted'."""
    _write_polluted_dotenv(tmp_path)

    lines = _run_child(tmp_path, _child_env())

    assert lines == ["None", "None"], (
        "a repo-root .env leaked into the child: "
        f"KROKER_HARNESS_QUEUE={lines[0]!r}, SDLC_RUNS_ROOT={lines[1]!r}"
    )


def test_the_dotenv_is_ignored_when_python_dotenv_disabled_is_set(tmp_path):
    """Complement, passes today and must keep passing after T026: with the flag
    set in the child's environment, load_dotenv is a no-op and both read None."""
    _write_polluted_dotenv(tmp_path)

    lines = _run_child(tmp_path, _child_env(PYTHON_DOTENV_DISABLED="1"))

    assert lines == ["None", "None"]


@pytest.mark.parametrize("flag", ["1", "true"])
def test_the_flag_is_honored_by_the_child_for_any_truthy_value(tmp_path, flag):
    """python-dotenv reads the flag as a truthy string, so the immunity does not
    depend on the exact value a conftest writes."""
    _write_polluted_dotenv(tmp_path)

    lines = _run_child(tmp_path, _child_env(PYTHON_DOTENV_DISABLED=flag))

    assert lines == ["None", "None"]


# --- chaos / edge cases (026 T025, chaos QA) --------------------------------
#
# The child's find_dotenv(usecwd=True) walks UP from its cwd, so a .env at the
# repo root or in any ancestor would load into a child whose cwd is the repo
# root. This checkout HAS a repo-root .env (an operator's file, never read
# here), so the repo-root case skips on such machines, and never creates one.

REPO_ROOT = Path(__file__).resolve().parents[1]


def _dotenv_on_walk_up(start: Path) -> Path | None:
    """The first .env at `start` or any ancestor (what find_dotenv would find)."""
    for d in (start, *start.parents):
        if (d / ".env").is_file():
            return d / ".env"
    return None


@pytest.mark.skipif(
    _dotenv_on_walk_up(REPO_ROOT) is not None,
    reason="a .env exists at or above the repo root (an operator's file); "
    "this case needs a clean walk-up and must not create one",
)
def test_edge_child_with_repo_root_cwd_sees_no_dotenv_when_none_is_above(tmp_path):
    """A child whose cwd is the repo root, with no .env at or above it, reads
    both polluted variables as None (the walk-up finds nothing to load)."""
    lines = _run_child(REPO_ROOT, _child_env())
    assert lines == ["None", "None"]


def test_edge_already_set_variable_is_not_overwritten_by_the_dotenv(tmp_path):
    """override=False: a variable the child already has keeps its value even
    when the .env names it. Passes today; it pins the semantics the fix uses."""
    _write_polluted_dotenv(tmp_path)

    lines = _run_child(tmp_path, _child_env(KROKER_HARNESS_QUEUE="already-set"))

    assert lines[0] == "already-set"


def test_edge_single_quoted_polluted_value_is_still_isolated(tmp_path):
    """python-dotenv strips the quotes, so a quoted value would print without
    them. RED today for the same reason as the main case."""
    (tmp_path / ".env").write_text(
        "KROKER_HARNESS_QUEUE='polluted'\nSDLC_RUNS_ROOT='/polluted/by/env'\n",
        encoding="utf-8",
    )

    lines = _run_child(tmp_path, _child_env())

    assert lines == ["None", "None"], f"quoted .env leaked: {lines!r}"
