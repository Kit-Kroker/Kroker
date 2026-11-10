# Reviewer brief: round 020 plan, pass 1

You are the SPEC & PLAN REVIEWER. Judge the plan **only** by spec-kit's
checklist method. The questions are whether every requirement is traceable,
the steps are concrete, nothing is left as a placeholder, file paths are
exact, and test commands are explicit.

Artifacts, all in this repo, under `.specify/specs/020-delete-featureworkflow/`:
- `spec.md` (GATE 1 approved; see Rulings and corrections C1-C5)
- `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `test-inventory.md`
- `contracts/fleet-legacy-row.md`, `contracts/gate-runbook.md`
- background only: `advisor-answer-1.md`, `skeptic-answer-1.md`

Do:
1. Run `/speckit-checklist` for the **plan** domain against these
   artifacts. Write the checklist to `checklists/plan.md` in that directory.
2. Check spec-to-plan consistency, `/speckit-analyze` style:
   - FR-001..FR-016 and SC-001..SC-007 each map to a plan task (T0xx) and to
     a validation in quickstart or a contract;
   - the two gate re-runs (FR-001, FR-002) are BLOCKING tasks, and the gate
     queries are NOT executed as part of planning;
   - the replay-safety analysis (FR-008) covers every execution class, and
     the FR-009 choice is consistent with research R-1;
   - the 76-file test classification (FR-012) is a concrete task with a
     closed set of classes and a counterpart rule;
   - the PR-1 tasks change no command sequence that FeatureWorkflow executes
     (the grace-edit rule in `src/sdlc/workflows/AGENTS.md` still holds then);
   - every cited `file:line` exists in this tree (spot-check at least 10).
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly
   `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as
   a numbered item with the file and section.

Rules:
- Do not edit any artifact other than `checklists/plan.md`.
- No git commands that write. Do NOT run any `temporal` CLI command.
- Reply in the pane with only the verdict word.

## Pass 2 (2026-11-08)

All five pass-1 gaps were folded in:
1. Counts: 18 scenarios; 19 Feature histories (18 plus `research_retain_grounded`)
   and 18 Feature goldens re-captured, 37 files in all; the
   `assessment_discover_risk` golden is listed as unchanged. Fixed in spec C1,
   the card table and US4, plan Summary/Scale/T041/replay table, research R-4,
   data-model §4 and the test-inventory header.
2. The `DEFAULT_LINT_CMD` target is now `sdlc.stages.merge.step` (test-inventory
   and plan T012).
3. Task refs: T020 → T041, T031 → T046, T061 → T050.
4. `fleet.py:105`.
5. The R-7 path is qualified with its directory; T012 states the
   `validate_task_graph` rename.

Re-check only those five, plus a fresh placeholder and stale-ref sweep.
Overwrite `checklists/plan.md` with the pass-2 verdict on line 1, and keep
the pass-1 gaps below it marked resolved or open.

## Pass 3 (2026-11-08)

Gap 6 is folded in:
- spec US4 scenarios 2 and 3 now say three non-Feature histories, with the
  Feature ones "replaced in place by GraphWorkflow captures";
- the card-table row at spec.md:43 now says three, and marks
  `research_retain_grounded` as FeatureWorkflow (see C1).

Re-check gap 6 only, plus a quick sweep of spec.md for any remaining
"removed" or "deleted" wording about histories. Overwrite line 1 of
`checklists/plan.md` with the pass-3 verdict and append a "## Pass 3"
section.
