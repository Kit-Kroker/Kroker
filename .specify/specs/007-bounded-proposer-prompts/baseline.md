# Baseline: 007-bounded-proposer-prompts

Recorded on the base sha before any source edit (T001). All runs in
`kroker-dev`; one pytest per command; RC captured per command.

## Setup

| Item | Value |
|---|---|
| Base sha (branch point) | `721a802` (main HEAD) |
| Branch | `007-bounded-proposer-prompts` |
| Worktree | `D:\own\Kroker-007` |
| `uv sync --frozen --extra dev --extra logfire` in `kroker-dev` | RC=0 (`Installed 1 package`), venv volume `kroker-007-venv` (dedicated; `kroker-verify-venv` not reused) |

Environment notes (this executor's container, not a source change):

- `kroker-dev` was re-bound from the deleted 006 worktree to
  `D:\own\Kroker-007` at `/app` (stop + rm + run, per the executor brief).
- The worktree `.git` pointer was rewritten from the absolute
  `D:/own/Kroker/.git/worktrees/Kroker-007` to the relative
  `../Kroker/.git/worktrees/Kroker-007` so it resolves on the host and in
  the container (the primary `.git` is mounted at `/Kroker/.git`); same
  pattern the 006 baseline records. Without it, three git-reading tests
  fail in the container (`fatal: not a git repository:
  /app/D:/own/Kroker/.git/worktrees/Kroker-007`): verified before the fix
  (`3 failed, 5485 passed`), all three green after it
  (`23 passed, RC=0` for the three modules in isolation).

## Baseline counts

| Check | Result | Notes |
|---|---|---|
| `pytest` (fast tier, RED test file moved aside) | **5488 passed, 11 skipped, 247 deselected**, RC=0, 700.05s | unmodified main, no pre-existing failures |
| `mypy` | **Success: no issues found in 378 source files**, RC=0 | matches the 006 close-out |

The first full-tier attempt (before the `.git` pointer fix) recorded
`3 failed, 5485 passed, 11 skipped, 247 deselected`, RC=1, 920.94s; all
three failures were the container git-path artifact above, re-run green
after the fix. A later attempt with qa-chaos's untracked T002 RED file
still in the tree failed collection with
`ImportError: cannot import name 'payload_guard' from 'sdlc.agents'` —
that is T002's stated RED reason, not a baseline defect; the clean run
above moved the file aside first (log: `.workspace` executor scratch,
not committed).
