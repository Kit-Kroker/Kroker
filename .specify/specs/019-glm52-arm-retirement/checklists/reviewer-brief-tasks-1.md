# Reviewer brief: round 019 tasks, pass 1

You are the SPEC & PLAN REVIEWER. Judge `tasks.md` **only** by spec-kit's
checklist method. The tasks must be bite-sized and in dependency order,
with exact file paths, explicit test commands and no placeholders, and
every requirement must be traceable.

Artifacts, all in this repo, under `.specify/specs/019-glm52-arm-retirement/`:
- `tasks.md`, under review;
- `spec.md`, `plan.md` (approved), `research.md`, `data-model.md`,
  `contracts/corpus-status.md`, `quickstart.md`.

Do:
1. Run `/speckit-checklist` for the **tasks** domain. Write the checklist to
   `.specify/specs/019-glm52-arm-retirement/checklists/tasks.md`.
2. Run a `/speckit-analyze`-style cross-artifact check:
   - every FR-001..FR-011 and SC-001..SC-006 has at least one task;
   - every plan step (0–7) and stop-guard (SG-1..SG-8) is reached by a
     task;
   - RED-first ordering holds for FR-009 (T007 before T008), FR-004 (T016
     before T017) and the real-case tests (T018 before T019–T025);
   - the checklist format holds (`- [ ] T### [P?] [US?] … path`);
   - the [P] markers do not collide on a file;
   - the commit tasks list every file their phase changes;
   - cited `file:line` targets exist (spot-check at least 10).
3. Put the verdict on the **first line** of `checklists/tasks.md`, exactly
   `VERDICT: approve` or `VERDICT: fixes-needed`, with numbered gaps below
   it (file and task id).

Rules:
- Edit nothing except `checklists/tasks.md`.
- No git write commands.
- Reply in the pane with only the verdict word.
