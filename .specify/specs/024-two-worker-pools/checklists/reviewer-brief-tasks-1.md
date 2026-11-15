# Reviewer brief — round 024 tasks, pass 1

RESET: round **024** (two worker pools, E-91), spec dir `.specify/specs/024-two-worker-pools/`. You approved `plan.md` on pass 2 (`checklists/plan.md`).

Role: SPEC & PLAN REVIEWER.
- Edit no artifact except `checklists/tasks.md`.
- No git writes, no test runs, and no temporal CLI.

Judge `tasks.md` by spec-kit's tasks checklist method:
- the format is `- [ ] Tnnn [P?] [USn?] description (size)`, with exact file paths;
- RED-before-implementation ordering holds, and PROOF tasks carry STOP clauses;
- every P-FR-001..013 and SC-001..007 is covered by at least one task;
- every plan step A1..J2 is covered (plan §Traceability);
- dependencies and [P] markers are correct: no [P] task shares a file with a task it is parallel to;
- the 024-i/024-ii split is honoured: T001–T020 contain no routing wiring, and 024-ii needs only 024-i;
- the sizes are honest: no hidden L;
- every task is executable without extra context.

Spot-check, against the tree:
- at least 10 of the `file:line` references in T023/T026/T027/T028/T030;
- that T005's named test file exists;
- that the T021 constants exist in `src/sdlc/stages/code/step.py`;
- that the T012 doctor row list exists.

Flag any reviewer-plan gap that was not carried into tasks.

Write `checklists/tasks.md`. Line 1 is exactly `VERDICT: approve` or `VERDICT: fixes-needed`, followed by numbered gaps (file and section), each marked blocking or non-blocking, then the checklist. Reply in the pane with only the verdict word.
