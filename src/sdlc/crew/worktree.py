"""Where the round protocol lives on disk, and how it stays out of the diff
(E-88 §2).

Inside the worktree, because containment checks _abs_under(path, worktree):
moving the protocol outside would weaken the strongest invariant in the
system. Out of the diff because checkpoint_round's `git add` is
pathspec-scoped to exclude the orchestration tree: the exclusion is local
to that one command, so no state is written into the user's repository.
(An exclude file cannot be worktree-private: info/exclude lives in the git
COMMON dir, which a linked worktree shares with the main repo.)
"""

from __future__ import annotations

from pathlib import Path

ORCH_ROOT = ".workspace/orchestration"


def orchestration_dir(worktree: str | Path, layout: str) -> Path:
    return Path(worktree) / ORCH_ROOT / layout


def round_dir(worktree: str | Path, layout: str, rnd: int) -> Path:
    return orchestration_dir(worktree, layout) / f"round-{rnd}"


def prepare_orchestration(worktree: str | Path, layout: str) -> Path:
    """Create the layout's orchestration tree.

    Idempotent: a retried activity re-enters here.
    """
    d = orchestration_dir(worktree, layout)
    # No status/ or cost/ subdirectories: E-87 needed them as a second signal
    # against a screen heuristic and as a place for CostProbe records. A turn
    # is an activity now -- its return IS the signal, and it carries its own
    # cost (spec §2, §4).
    d.mkdir(parents=True, exist_ok=True)
    return d
