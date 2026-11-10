# Reviewer brief: round 020 tasks, pass 1

You are the SPEC & PLAN REVIEWER. Judge `tasks.md` **only** by spec-kit's
tasks checklist method. The questions are whether every task is in the
strict format (`- [ ] Txxx [P?] [USn?] description with exact path`),
whether it is executable without extra context, and whether it is
dependency-ordered, traceable and free of placeholders.

Artifacts are in `.specify/specs/020-delete-featureworkflow/`. `tasks.md` is
the subject. `plan.md` (approved, pass 3), `spec.md`, `research.md`,
`data-model.md`, `contracts/*`, `quickstart.md` and `test-inventory.md` are
the reference.

Do:
1. Run `/speckit-checklist` for the **tasks** domain. Write the result to
   `checklists/tasks.md`.
2. Check consistency, `/speckit-analyze` style:
   - every plan task id (T010 to T092) is implemented by a tasks.md task
     that cites `(plan Txxx)`, and nothing in the plan is dropped;
   - every FR-001..FR-016 and SC-001..SC-007 is covered;
   - the gate re-runs (T016, T036) are BLOCKING tasks with a STOP, and no
     other task runs a `temporal` command;
   - the replay-safety work (FR-008, FR-009) and the 76-file classification
     (T003, then T026) are concrete;
   - order: the re-capture (T018) happens before any PR-2 `src/` edit, and
     the inbox removal (T024) happens after gate run 1;
   - every `[P]` claim is true (disjoint files, no unmet dependency);
   - every task story label matches the spec's user stories;
   - every cited path and `file:line` exists in the tree (spot-check at
     least 10), or is explicitly marked new.
3. Verdict on the **first line**, exactly `VERDICT: approve` or
   `VERDICT: fixes-needed`. Number each gap below it with its task id.

Rules: edit nothing but `checklists/tasks.md`. No git commands that write.
Do NOT run any `temporal` CLI command. Reply only with the verdict word.

## Pass 2 (2026-11-08)

All three gaps are fixed:
1. T012 and T013 now cite `(plan T018)`.
2. T029 now cites `(plan T053)`.
3. The conventions rule now reads "except in T016 and T036".

Re-check those three only. Put the pass-2 verdict on line 1 of
`checklists/tasks.md` and append a "## Pass 2" section.
