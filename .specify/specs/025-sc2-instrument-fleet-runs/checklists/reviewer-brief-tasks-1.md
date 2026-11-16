# Reviewer brief — round 025 tasks, pass 1

RESET: round **025** (SC-2 instrument + fleet runs), dir `.specify/specs/025-sc2-instrument-fleet-runs/`. NOT 024. Role: SPEC & PLAN REVIEWER, advice only; edit no artifact except `checklists/tasks.md`; no git writes; no test runs.

Plan checklist passed (`checklists/plan.md`, approve; its 4 non-blocking gaps were folded in). Now judge `tasks.md` by spec-kit's tasks method:
1. Run `/speckit-checklist` for the **tasks** domain; write `checklists/tasks.md`.
2. Check: every plan step A–K and every FR/SC maps to at least one task (and the reverse: no orphan task); each Part A implementation task is preceded by a RED task with an explicit failing command; test commands are exact and runnable from the repo root; file paths exact; dependencies and ordering correct (RED before GREEN; Part B gated behind T014 and GATE 2); task sizes plausible (none L); Part B `[OPS]` tasks each have an announce step, an evidence artifact, and the stop rules (infra stop, two-stop limit, run cap 7, commit freeze T022→last run, smoke failure stops for the owner); the spec's B.2 prerequisites are all covered by T020/T021; no task changes workflow/trust-layer code or adds events; Spot-check 6 claims against code (e.g. `cli.py` verbs for `smoke`/`run`/`score --all`/`verify-case`, `--arm` name `zai-coding-plan-glm-5.3`, fixture paths named in T011, `tests/replay` existence, the `-k` selectors).
End with exactly one line `VERDICT: approve` or `VERDICT: fixes-needed`, gaps marked BLOCKING / non-blocking.

PASS 2 (appended): tasks-1 findings 1–5 were folded into tasks.md (T011 retargeted to tests/test_fleet_fixture_fresh.py and the dashboard fixtures; commands use literal paths; RED commands added; verification.md path named; FR-011 note in T033). Re-verify only those, spot-check no regression, append "# Pass 2" to checklists/tasks.md and end with the VERDICT line.
