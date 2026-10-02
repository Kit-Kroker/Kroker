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

## T002 pass counts

| Tier | Result | Notes |
|---|---|---|
| `pytest` (fast) | **5436 passed, 11 skipped, 245 deselected**, RC=0, 347.58s | no failures; identical counts to 004 close-out |
| `pytest -m temporal` (chunked per file, 44 files, `timeout 300` each) | **179 passed, 20 skipped, 1 xfailed, 1 failed**, every other file RC=0, 0 timeout-kills | one pre-existing failure, see below |

Pre-existing failure (not caused by 005; reproduced 3/3 — twice in this
container, once in `kroker-baseline` on the same sha `2196438`):
`tests/replay/test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[budget_arch_reject-sandboxed]`
— "SG-3: command projection differs" (at index 11 the run projects
`activity:publish_artifact_version` where the golden expects `timer`, and
the golden contains one more item, `activity:apply_session_retention`).
004's close-out recorded 180/20/1/0 on base `730f085`; main has moved since
(004 merge + docs commits). Recorded per T002, not investigated, not fixed
here.

## T003 first-workflow-task timing

`tests/durability/test_first_workflow_task_time.py` green on base (temporal
tier, RC=0, 2 passed; the measured value only travels in the assert message).
One-off replica of the measurement (same greenfield_happy scenario, sandboxed
runner via `SdlcPydanticAIPlugin`, `auto_time_skipping_disabled`, script kept
outside the repo): **first WorkflowTaskCompleted at 0.128s** from
`start_workflow`; no TMPRL1101 in the history. 004's baseline on `730f085`
was 0.130s — consistent. Budget: < 1.5s.
