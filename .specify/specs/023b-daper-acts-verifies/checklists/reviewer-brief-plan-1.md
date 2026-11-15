# Reviewer brief — round 023b plan, pass 1

RESET: this is round **023b** (DAPER maintenance loop, "acts and verifies"), spec dir `.specify/specs/023b-daper-acts-verifies/`. It is NOT 023a; your prior 023a review context is background only. Disregard 021/022.

Role: you are the SPEC & PLAN REVIEWER. Review advice only. Edit no artifact except `checklists/plan.md` in the 023b dir. Never commit and never run git writes. Do not run the test suite or any temporal CLI.

Judge the plan **only** by spec-kit's checklist method:
- every requirement is traceable;
- steps are concrete;
- there are no placeholders;
- file paths are exact;
- test commands are explicit.

Artifacts, all under `.specify/specs/023b-daper-acts-verifies/`:
- `spec.md`: GATE 1 record near the end, binding; all eight recommendations accepted. Part B requirements are B-FR-001..B-FR-025, plus B-FR-006a, and SC-B01..SC-B11.
- `plan.md`, `research.md` (R1–R16), `data-model.md`, `quickstart.md`, `contracts/workflow-wire.md`, `contracts/cli.md`.
- `consults/advisor.md` (D1–D6) and `consults/skeptic.md` (L1–L6). Every finding must be dispositioned.
- Authority for the settled 023a decisions: `.specify/specs/023-daper-maintenance-loop/{spec,research,data-model,verification}.md`.

Do:
1. Run `/speckit-checklist` for the **plan** domain against these artifacts. Write it to `checklists/plan.md`.
2. Check spec-to-plan consistency, analyze-style:
   - **Traceability.** Each B-FR and each SC-B maps to a plan step (A1..G2) and to a quickstart validation or test step (plan §Traceability).
   - **Scope honesty.** Nothing executes an ops action (B-FR-017). Rollback and deploy liveness are absent. Execute-off is byte-for-byte 023a (B-FR-018, R15). `GraphWorkflow` is not modified. No 023a settled decision is reopened beyond what the GATE 1 record approved (Q4 FR-016 amendment; Q5 refinement).
   - **Consults.** Every D/L finding has a row in plan §Skeptic/advisor disposition, and the row is reflected in a research decision or step. Both "not adopted" items carry a reason.
   - **Trust layer against the code.**
     - R5: the loop only ever builds REJECT for a child merge gate. The gate is first-decision-wins at `src/sdlc/workflows/gates.py:123-126`.
     - R6: the `may_execute` conditions against `src/sdlc/maintenance/confidence.py:20-60` and `src/sdlc/maintenance/models.py:93` (threshold range).
     - The child merge gate stays HARD/HOLD: `src/sdlc/core/models.py:374`; `_fix_gates` at `src/sdlc/workflows/tidyup.py:56-72`.
   - **Reuse claims hold.**
     - R1: `execute_pipeline_child` blocks at `src/sdlc/workflows/pipeline_child.py:49`; the ABANDON precedent is at `src/sdlc/workflows/deployment.py:9`.
     - R2: the queries at `src/sdlc/workflows/gates.py:134-146` and `src/sdlc/workflows/graph.py:83-105`; `activity.client` exists in temporalio 1.31.
     - R3: `setup_integration_branch` at `src/sdlc/vcs/integration.py:37-51` and `_ensure_worktree` at `src/sdlc/vcs/worktree.py:83-94` accept a sha as `from_ref`.
     - R4: `build_verification_branch` / `VerifyBranchInput` at `src/sdlc/vcs/integration.py:107-172`.
     - R7/R8/R9: `src/sdlc/maintenance/incidents.py:126,171,201-216` and `src/sdlc/maintenance/models.py:43-63,248-263`.
     - R12: `seeded_work_for` at `src/sdlc/tidyup/backlog.py:63-81`.
     - R13: `MEM_ACT` and `_retain` at `src/sdlc/workflows/memory_host.py:36-38,83-100`; `src/sdlc/memory/hindsight_client.py:79,88,99`; `MemoryKind` at `src/sdlc/memory/models.py:20`.
     - R14: the merge preconditions at `src/sdlc/stages/merge/activities.py:210-225`.
     - H3: `src/sdlc/run_budget.py:14-16`.
   - **Repo constraints.**
     - The 1000-line ceiling (R16 table vs `wc -l`).
     - `tests/replay/AGENTS.md` (no new fixture writer; the 023a-state fixture is written by a capture test).
     - `src/sdlc/workflows/AGENTS.md` (`maintenance_execute.py` owns no attribute or handler).
     - `src/sdlc/maintenance/AGENTS.md` invariants, with the reword scoped to GATE 1 Q4.
   - **Determinism.** R15's `cfg.execute` + `workflow.patched` gating is sufficient for running 023a histories. Flag any new command reachable with execute off.
   - **Riders.** Spec Part D items 1–4 map to F2–F5.
   - **Citations.** Spot-check at least 10 cited `file:line` refs exist in this tree.
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as a numbered item with the file and section. Mark which gaps are blocking.

Reply in the pane with only the verdict word.
