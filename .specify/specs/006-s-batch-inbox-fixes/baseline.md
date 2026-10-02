# Baseline: 006-s-batch-inbox-fixes

Recorded on the base sha before any source edit (Phase 1). All runs in
`kroker-dev`; one pytest per command; RC captured per command.

## T001 setup

| Item | Value |
|---|---|
| Base sha (branch point) | `6de8489` (current main HEAD: the 006 spec commit, docs-only, on code base `817f819`) |
| Branch | `006-s-batch-inbox-fixes` |
| Worktree | `D:\own\Kroker-006` |
| `uv sync --frozen --extra dev` in `kroker-dev` | RC=0 (venv volume `kroker-006-venv`, dedicated; the shared `kroker-verify-venv` is deliberately not reused) |

Environment notes (this executor's container, not a source change):

- `kroker-dev` re-bound from the deleted 005 worktree to `D:\own\Kroker-006`
  at `/app` per quickstart.md, following the 005 pattern: the worktree's
  `.git` pointer is relative
  (`../Kroker/.git/worktrees/Kroker-006`) and the primary checkout's `.git`
  is mounted at `/Kroker/.git`, so the same pointer resolves on host and in
  the container. Container git sees `core.autocrlf true` from the shared
  repo config, matching the host checkout (003 "worktree pointer trap"
  avoided by construction).
- venv volume `kroker-006-venv` mounted at `/app/.venv`; sync is clean.

## Baseline counts

| Check | Result | Notes |
|---|---|---|
| `pytest` (fast) | **1 failed, 5469 passed, 11 skipped, 247 deselected**, RC=1, 1201.49s | one failure, see below |
| `mypy` | **0 errors in 378 source files**, RC=0 | matches the 005 close-out (0/378) |

Pre-existing failure (recorded on the unmodified base before any edit):

`tests/replay/test_feature_replay.py::test_feature_workflow_replays_captured_history[clarify_fanout]`
— failed once inside the full fast run, which took 20:01 under heavy load.
Re-run of the whole module in isolation on the same sha: **18 passed, RC=0**
(65.98s), including the `clarify_fanout` param. Same class as 005's
recorded `test_graph_golden` flake: **load-dependent replay flakiness**,
not a deterministic base red. Recorded per T001, not investigated, not
fixed here.

Comparison point for T014: fast tier should be 5469 + this batch's new
passing tests, with no new failure; mypy stays 0/378.
