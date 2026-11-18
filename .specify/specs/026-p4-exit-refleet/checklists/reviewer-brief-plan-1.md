# Reviewer brief — round 026 plan, pass 1

RESET: this is round **026**, P4 exit fixes + smaller re-fleet, spec dir `.specify/specs/026-p4-exit-refleet/`. NOT 025; earlier context is background only.

Role: SPEC & PLAN REVIEWER, advice only. Edit no artifact except `checklists/plan.md` in the 026 dir. No git writes. Do not run the test suite or temporal. Never write to ../kroker-fleet-runs-025 or ../scratch-repos.

Judge the plan by spec-kit's checklist method: every requirement traceable, steps concrete, no placeholders, exact file paths, explicit test commands.

Artifacts (026 dir): `spec.md` (GATE 1 record binding; amendments A-1..A-7 at the end), `plan.md`, `research.md` (R1–R9), `data-model.md`, `quickstart.md`, `consults/skeptic.md`, `consults/README.md` (advisor unresponsive — the planner settled D1–D7 in research; judge whether that was done adequately). Requirements FR-001..006, FR-010..012, FR-020..023, FR-030, FR-040, FR-050..054; SC-A1..A4, SC-B1..B4.

Do:
1. Run `/speckit-checklist` for the **plan** domain; write `checklists/plan.md`.
2. Check spec↔plan consistency: traceability of every FR and SC to a step and a validation; scope honesty (trust layer untouched — `lint_clean`, gate policy semantics, auto_decision_for, containment, GraphWorkflow; no new workflow commands; Part B changes no code); GATE 1 rulings honoured (Q1-A PRD SC-1 + HARD; Q2-A per-task autofix + merge's own lint into fix loop; Q3-A 5+smoke, $13.95+$1.00); every skeptic finding dispositioned; corrected 025 baseline consistent across spec/quickstart/plan.
3. Spot-check at least 8 code claims: `benchmarks/evidence.py:48-53`, `observability/activities.py:28`, `benchmarks/recorder.py:17-24`, `workflows/graph.py:205-207`, `benchmarks/sc_rollup.py:160-169`, `stages/code/step.py:714-721,756`, `stages/qa/step.py:69`, `stages/merge/scoping.py:79-111`, `stages/merge/step.py:256-265,582-583`, `vcs/integration.py:97-124,232`, `stages/code/activities.py:180-199`, `stages/research/toolset.py:55-77`, `cli.py:493`, `core/models.py:69,92,383-390`, `benchmarks/workflow.py:157-164`.
4. Specifically judge: (a) is autofix-before-checkpoint + fence exclusion sound vs the C2 test-freeze drift backstop; (b) is "no new workflow command" true for the A3 design (QAInput field + logic in existing activities), and is the replay proof adequate; (c) is the SC-1 `unplanned` rule + steering guard well-defined from RunSummary.gates fields alone.
End `checklists/plan.md` with exactly one line: `VERDICT: approve` or `VERDICT: fixes-needed`, listing gaps (mark BLOCKING / non-blocking).
