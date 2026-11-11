# Reviewer brief: round 021 plan, pass 1

You are the SPEC & PLAN REVIEWER. Judge the plan **only** by spec-kit's checklist method. The questions are whether every requirement is traceable, the steps are concrete, nothing is left as a placeholder, file paths are exact, and test commands are explicit.

Artifacts, all under `.specify/specs/021-recall-snapshot-artifact/`:
- `spec.md` (GATE 1 approved; see Rulings Q1-Q3 and Errata E-1, E-2)
- `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/recall-snapshot-artifact.md`
- background only: `advisor-answer-1.md`, `skeptic-answer-1.md`

Do:
1. Run `/speckit-checklist` for the **plan** domain against these artifacts. Write the checklist to `checklists/plan.md` in that directory.
2. Check spec-to-plan consistency, `/speckit-analyze` style:
   - FR-001..FR-011 and SC-001..SC-005 each map to a plan task (T0xx) and to a validation in quickstart or a test task (see plan §Traceability);
   - the three GATE 1 rulings (Q1 alongside, Q2 artifact store only, Q3 continue as degraded) are honoured exactly;
   - the replay-safety analysis (FR-009) is consistent with research R-1 (no new activity, no `workflow.patched`), and T050 is a blocking check;
   - FR-007 (memory-off byte identity) holds by construction in T021/T022 and is tested;
   - every skeptic finding in `skeptic-answer-1.md` is either adopted in research R-1..R-8 or explicitly deferred as a GATE 2 item (R-9);
   - every cited `file:line` exists in this tree (spot-check at least 10).
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as a numbered item with the file and section.

Rules:
- Do not edit any artifact other than `checklists/plan.md`.
- No git commands that write. Do NOT run any `temporal` CLI command and do not run the test suite.
- Reply in the pane with only the verdict word.

## Pass 2 (2026-11-11)

All four pass-1 gaps were folded in:
1. The spec Testing Scope last bullet now says the pre-021 memory-on history "replays unpatched, without editing the history (no new activity; E-1)".
2. In plan Traceability, the FR-009 and SC-005 rows now name T011, T013 and T021.
3. Scale/Scope: src has 12 `.py` files (9 + 3 stage `step.py`); tests have 9 edited (7 distinct in T040, plus T041 and T042) and 3 new (T043-T045).
4. `RecallInput` is cited at `activities.py:51` in plan T013 and data-model.

Re-check only those four, plus a fresh placeholder and stale-ref sweep. Overwrite line 1 of `checklists/plan.md` with the pass-2 verdict and append a "## Pass 2" section that marks each pass-1 gap resolved or open.
