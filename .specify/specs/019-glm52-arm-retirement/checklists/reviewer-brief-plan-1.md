# Reviewer brief: round 019 plan, pass 1 (pass 2 notes at the end)

You are the SPEC & PLAN REVIEWER. Judge the plan **only** by spec-kit's
checklist method. The questions are whether every requirement is traceable,
the steps are concrete, nothing is left as a placeholder, file paths are
exact, and test commands are explicit.

Artifacts, all in this repo:
- `.specify/specs/019-glm52-arm-retirement/spec.md` (GATE 1 approved; see
  Rulings)
- `.specify/specs/019-glm52-arm-retirement/plan.md`
- `.specify/specs/019-glm52-arm-retirement/research.md`
- `.specify/specs/019-glm52-arm-retirement/data-model.md`
- `.specify/specs/019-glm52-arm-retirement/contracts/corpus-status.md`
- `.specify/specs/019-glm52-arm-retirement/quickstart.md`

Do:
1. Run `/speckit-checklist` for the **plan** domain against these
   artifacts. Write the checklist to
   `.specify/specs/019-glm52-arm-retirement/checklists/plan.md`.
2. Check spec-to-plan consistency, `/speckit-analyze` style:
   - FR-001..FR-011 and SC-001..SC-006 each map to a plan step and to a
     validation in quickstart or the contract;
   - stop-guards SG-1..SG-8 are each checkable;
   - every cited `file:line` exists in this tree (spot-check at least 10);
   - the expected verdicts (research D-3, contract §2) follow from
     `src/sdlc/benchmarks/acceptance.py` `decide()`.
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly
   `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as
   a numbered item with the file and section.

Rules:
- Do not edit any artifact other than `checklists/plan.md`.
- No git commands that write.
- Files outside this repo are not needed.
- Reply in the pane with only the verdict word.
