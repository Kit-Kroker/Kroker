# Baseline: 005-native-zai-provider

Recorded on the base sha before any source edit (Phase 1). All runs in
`kroker-dev`; one pytest per command; RC captured per command.

## T001 setup

| Item | Value |
|---|---|
| Base sha (branch point) | `2196438` (current main HEAD: the 005 spec commit, docs-only, on code base `0f4ac11`) |
| Branch | `005-native-zai-provider` |
| Worktree | `D:\own\Kroker-005` |
| `uv sync --frozen --extra dev` in `kroker-dev` | RC=0 (venv volume `kroker-005-venv`) |

Environment notes (this executor's container, not a source change):

- `kroker-dev` = image `kroker-dev`, the feature worktree bind-mounted at
  `/app`, dedicated venv volume at `/app/.venv` (the shared
  `kroker-verify-venv` is deliberately NOT reused: syncing without
  `--extra logfire` would prune that volume under the running
  `kroker-baseline` container).
- Git inside the container: the worktree's `.git` pointer is relative
  (`../Kroker/.git/worktrees/Kroker-005`) and the primary checkout's `.git`
  is mounted at `/Kroker/.git`, so the same pointer resolves on host and in
  the container; container git sets `core.autocrlf true` to match the host
  checkout. Without this, three fast-tier tests that read git
  (`test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`,
  `test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`,
  `test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`)
  fail on the worktree mount (003 "worktree pointer trap"). With it they are
  green (verified per file, RC=0 each).
