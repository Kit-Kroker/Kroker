# Reviewer brief — round 025 plan, pass 1

RESET: this is round **025**, the SC-2 instrument + fleet runs, spec dir `.specify/specs/025-sc2-instrument-fleet-runs/`. It is NOT 024; earlier context is background only.

Role: SPEC & PLAN REVIEWER, advice only. Edit no artifact except `checklists/plan.md` in the 025 dir. No git writes. Do not run the test suite or temporal.

Judge the plan by spec-kit's checklist method: every requirement traceable, steps concrete, no placeholders, exact file paths, explicit test commands.

Artifacts (025 dir): `spec.md` (GATE 1 record binding; amendments B.9/A.5/A.6 at the end), `plan.md`, `research.md` (R1–R9), `data-model.md`, `quickstart.md`, `consults/advisor.md`, `consults/skeptic.md`. Requirements FR-001..015, FR-020..025; SC-A1..A3, SC-B1..B4.

Do:
1. Run `/speckit-checklist` for the **plan** domain; write `checklists/plan.md`.
2. Check spec↔plan consistency: traceability of every FR and SC to a step and a validation; scope honesty (no workflow, trust-layer or gate change; no new events; Part B changes no code; GATE 1 rulings honoured: cap 10 min, SOFT, Q3 check answered); every advisor and skeptic finding dispositioned; claims against code (spot-check at least 8 of: `gates.py:231-244`, `run_host.py:50`, `question_host.py:60-106`, `summary.py:74-87,133-138`, `smoke.py:78-88`, `runs.py:38`, `core/models.py:465,484`, `judge.py:89-91`, `sc_rollup.py:92-101,117-144,179`, `cli.py` `dispatch_smoke`/`_run_matrix`); that no spec text still contradicts an amendment (e.g. B.3 table vs B.9, B.6 budget text).
3. Verify the spec's open questions are all resolved and nothing is silently re-litigated.
End `checklists/plan.md` with exactly one line: `VERDICT: approve` or `VERDICT: fixes-needed`, listing gaps (mark BLOCKING / non-blocking).
