"""Where the round protocol lives on disk, and how it stays out of the diff
(E-88 §2).

Inside the worktree, because containment checks _abs_under(path, worktree):
moving the protocol outside would weaken the strongest invariant in the
system. Out of git, because checkpoint_round runs `git add -A`, and
adapters.py's ENV_ALLOWLIST comment already records what happens when a
stray directory gets swept into a checkpoint.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ORCH_ROOT = ".workspace/orchestration"
# Exactly what we create, and no more. Excluding all of /.workspace/ would
# also hide anything a future feature -- or the task's own repo -- puts
# there, and an exclusion nobody asked for is found the hard way.
_EXCLUDE_LINE = f"/{ORCH_ROOT}/"


def orchestration_dir(worktree: str | Path, layout: str) -> Path:
    return Path(worktree) / ORCH_ROOT / layout


def round_dir(worktree: str | Path, layout: str, rnd: int) -> Path:
    return orchestration_dir(worktree, layout) / f"round-{rnd}"


def exclude_file(worktree: str | Path) -> Path:
    """The exclude file for THIS worktree, resolved by git itself."""
    out = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "--git-path",
         "info/exclude"],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(
            f"git rev-parse failed in {worktree}: "
            f"{out.stderr.strip() or out.stdout.strip()}")
    p = Path(out.stdout.strip())
    return p if p.is_absolute() else Path(worktree) / p


def prepare_orchestration(worktree: str | Path, layout: str) -> Path:
    """Create the layout's orchestration tree and make sure git ignores it.

    Idempotent: a retried activity re-enters here.
    """
    d = orchestration_dir(worktree, layout)
    # No status/ or cost/ subdirectories: E-87 needed them as a second signal
    # against a screen heuristic and as a place for CostProbe records. A turn
    # is an activity now -- its return IS the signal, and it carries its own
    # cost (spec §2, §4).
    d.mkdir(parents=True, exist_ok=True)

    ex = exclude_file(worktree)
    ex.parent.mkdir(parents=True, exist_ok=True)
    body = ex.read_text(encoding="utf-8") if ex.is_file() else ""
    if _EXCLUDE_LINE not in body.splitlines():
        if body and not body.endswith("\n"):
            body += "\n"
        body += (
            "# E-88: crew round protocol. Inside the worktree so containment\n"
            "# still applies; excluded so `git add -A` cannot sweep it into a\n"
            "# checkpoint commit and thence into the task's diff.\n"
            f"{_EXCLUDE_LINE}\n")
        ex.write_text(body, encoding="utf-8")
    return d
