# Reviewer brief: round 021 tasks, pass 1

You are the SPEC & PLAN REVIEWER. Judge `tasks.md` **only** by spec-kit's tasks checklist method. The questions are whether every task is in the strict format (`- [ ] Txxx [P?] [USn?] description with exact path`), whether it is executable without extra context, and whether it is dependency-ordered, traceable and free of placeholders.

Artifacts are in `.specify/specs/021-recall-snapshot-artifact/`. `tasks.md` is the subject. `plan.md` (approved pass 2; GATE 2 rulings applied), `spec.md` (GATE 1 + GATE 2 rulings, FR-001..FR-012, SC-001..SC-005), `research.md`, `data-model.md`, `contracts/recall-snapshot-artifact.md` and `quickstart.md` are the reference.

Do:
1. Run `/speckit-checklist` for the **tasks** domain. Write the result to `checklists/tasks.md`.
2. Check consistency, `/speckit-analyze` style:
   - every plan task id (T010-T070, plus T050) is implemented by a tasks.md task that cites `(plan Txxx)`, and nothing in the plan is dropped;
   - every FR-001..FR-012 and SC-001..SC-005 is covered (tasks.md §Traceability);
   - the GATE 2 rulings are reflected: FR-001/SC-001 narrowed to `ctx.recall`; ADR-5 correction (T031) and ROADMAP (T032) use plan T061/T062 text; the four cards are only checked (T033), not created; `cache_put` is kept for degraded stages (no task removes it); FR-012 scrub is implemented and tested;
   - no task adds an activity or `workflow.patched`, and only T008, T026, T028, T029 and T036 run `pytest -m temporal`;
   - tests come before implementation for every new behaviour;
   - every `[P]` claim is true (disjoint files, no unmet dependency);
   - every story label matches the spec's user stories (US1-US4);
   - every cited path and `file:line` exists in the tree (spot-check at least 10), or is explicitly marked new.
3. Put the verdict on the **first line** of `checklists/tasks.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. Number each gap below it with its task id.

Rules: edit nothing but `checklists/tasks.md`. No git commands that write. Do NOT run any `temporal` CLI command and do not run the test suite. Reply only with the verdict word.

## Pass 2 (2026-11-11)

Gap 1 is folded in: in tasks.md §Traceability, the FR-001 row now reads `T009, T010, T024, T025`. Re-check gap 1 only, plus a quick placeholder and stale-id sweep. Overwrite line 1 of `checklists/tasks.md` with the pass-2 verdict and append a "## Pass 2" section.
