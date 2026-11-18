# Reviewer brief — round 026 tasks, pass 1

Role: SPEC & PLAN REVIEWER, advice only. Edit nothing except `checklists/tasks.md` in the 026 dir. No git writes; do not run the suite or temporal; never write to ../kroker-fleet-runs-025 or ../scratch-repos.

Inputs: `tasks.md` (T001–T027 Part A, T040–T052 Part B), judged against `plan.md` (REVISION 2, approved at plan pass 2 with 6 non-blocking notes in checklists/plan.md), `spec.md` (GATE 1 record; amendments A-1..A-8), `research.md` R1–R9, `data-model.md`, `quickstart.md`.

Do:
1. Run `/speckit-checklist` for the **tasks** domain; write `checklists/tasks.md`.
2. Coverage both directions: every plan step (A1–A6, B) and every FR (FR-001..006, 010..012, 020..023, 030, 040, 050..054) and SC (SC-A1..A4, SC-B1..B4) maps to ≥1 task; no orphan task; plan's forward references realized 1:1.
3. RED/GREEN discipline: every implementation task preceded by a RED task with an explicit failing command; move-only (T011) and docs/ops tasks exempt with a stated proof.
4. Command and path exactness: every command runnable from repo root; every file path resolves or is clearly new; the local AGENTS.md named for each slice touched (code, qa, merge, review, research, workflows).
5. Ordering: T008 after T006/T010/T023; `sc_rollup.py` (T006→T010→T023) and `stages/code/step.py` (T016→T020) serialization; Part B gated on T027 + T008 + GATE 2; runs sequential until two done, ≤2 overlap.
6. Specific checks: plan pass-2 note 5 (source guard targets reads; `demo/__main__.py:56` write allowed) is pinned in T001; T002's 8 call sites match research R1; T016 includes the replay + golden-rebaseline STOP rule and the 1000-line budget; T021/T022 are conditional with an evidence-first step and the narrow `UnexpectedModelBehavior` catch; T040 pre-flight covers the 025 host fixes, containment/adversary off, attendant scope (gates + clarification waits, approve-only, 30-min watchdog, 60 s cost polling); T049's run-6 rule (SC-2-measured < 5 AND headroom ≥ $1.73); T050's report includes deltas vs the T008 baseline, CI, the three SC-3 rows, the MergeVerdict disclosure; safety rules (no rm -rf of variable paths; mktemp copies).
End `checklists/tasks.md` with exactly one line: `VERDICT: approve` or `VERDICT: fixes-needed` (mark gaps BLOCKING / non-blocking).
