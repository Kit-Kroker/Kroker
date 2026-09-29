"""verify.py must run everything CI runs.

A local "all gates pass" that CI then contradicts is worse than no script,
because it turns a check into false confidence. This test fails the moment
the two drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.verify import GATES

CI = Path(".github/workflows/ci.yml")


def _ci_commands() -> list[str]:
    """Every `run:` value in the workflow."""
    return [
        line.split("run:", 1)[1].strip()
        for line in CI.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s+run:\s+\S", line)
    ]


def _gate_key(command: str) -> str:
    """What a command *does*, ignoring how it is launched.

    The first two non-flag tokens: enough to tell `ruff check` from
    `ruff format`, and insensitive to `python -m pytest -q` versus a bare
    `pytest` or `uv run --no-sync pytest`.
    """
    tokens = command.replace(sys.executable, "python").split()
    if tokens[:2] == ["uv", "run"]:
        tokens = tokens[2:]
    parts = [
        token
        for token in tokens
        if not token.startswith("-") and token not in ("python", "python3")
    ]
    return " ".join(parts[:2])


def test_every_ci_gate_is_in_verify():
    # `pip install` and `uv sync --frozen` are setup, not gates: verify.py
    # runs in an already-installed tree.
    ci = {
        _gate_key(c)
        for c in _ci_commands()
        if not (c.startswith("pip install") or c.startswith("uv sync"))
    }
    covered = {_gate_key(" ".join(cmd)) for _, cmd in GATES}
    missing = ci - covered
    assert not missing, f"CI runs {sorted(missing)} but scripts/verify.py does not"


def test_gates_are_ordered_cheapest_first():
    names = [name for name, _ in GATES]
    assert names.index("ruff") < names.index("mypy") < names.index("pytest")
