# Reviewer brief: round 020, integration consistency pass (2026-11-08)

The user made three decisions, which the spec lead applied to `plan.md` and
`tasks.md` only:
1. Integration is by fast-forward merges to `main`, with no pull requests.
   "PR-1" and "PR-2" stay as stage names. T015 and T035 are now
   "the orchestrator verifies, then fast-forwards `main`; the crew does not
   push". Both stages and both blocking gates are kept.
2. T016 (gate run 1), T036 (gate run 2) and T037 (worker restart) are
   orchestrator-only. The executor STOPs after T014 (resuming at T017 after
   a T016 PASS) and after T034 (before T035).
3. T001 was done by the orchestrator and is marked `[x]`; it is not an
   executor task.

Check only that `plan.md` and `tasks.md` are consistent with these three
decisions and with each other. Specifically:
- no remaining wording implies a GitHub pull request, opening a PR, or
  merging after review;
- every orchestrator-only task is marked as such;
- the executor STOP points are explicit and match the Dependencies section;
- no executor task runs a `temporal` command;
- task ids and plan-id citations are unchanged.

Write the result to `checklists/integration.md`, with the verdict on line 1
exactly `VERDICT: approve` or `VERDICT: fixes-needed` and numbered gaps
below it. Edit nothing else. No git commands that write. Do not run any
`temporal` command. Reply in the pane with only the verdict word.

## Pass 2

Gap 1 is fixed: `(T049)` is now `(T029)` at tasks.md:62. Re-check that
gap only. Put the verdict on line 1 of `checklists/integration.md` and
append a "## Pass 2" section. Reply with the verdict word only.
