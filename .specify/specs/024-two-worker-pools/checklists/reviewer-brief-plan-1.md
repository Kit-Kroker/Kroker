# Reviewer brief — round 024 plan, pass 1

RESET: this is round **024**, two worker pools (E-91), spec dir `.specify/specs/024-two-worker-pools/`. It is NOT 023a or 023b, so your earlier review context is background only.

Role: you are the SPEC & PLAN REVIEWER. You give review advice only.
- Edit no artifact except `checklists/plan.md` in the 024 dir.
- Never commit, and never run git writes.
- Do not run the test suite or any temporal CLI. Read-only `uv run python -c` probes of installed libraries are allowed.

Judge the plan **only** by spec-kit's checklist method:
- every requirement is traceable;
- steps are concrete;
- there are no placeholders;
- file paths are exact;
- test commands are explicit.

Artifacts, all under the 024 dir:
- `spec.md`. The GATE 1 record at the end is binding: Q1–Q4 were all accepted, and the 024-i/024-ii split was pre-authorized. Requirements are P-FR-001..013 and SC-001..007.
- `plan.md`. It starts with the split decision. Steps are A1..J2.
- `research.md` (R1–R12), `data-model.md`, `quickstart.md`, `contracts/worker-boot.md`, `contracts/routing-wire.md`.
- `consults/advisor.md` (D1–D7) and `consults/skeptic.md` (L1–L6). Every finding must be dispositioned in plan §Skeptic/advisor disposition.

Do:
1. Run `/speckit-checklist` for the **plan** domain against these artifacts. Write it to `checklists/plan.md`.
2. Check spec-to-plan consistency, analyze-style:
   - **Traceability.** Every P-FR and every SC maps to a plan step and to a validation (plan §Traceability; quickstart §0–§5).
   - **Scope honesty.**
     - Routing off is byte-identical (R1 `exclude_if`, R3 `on_harness`, contracts/routing-wire.md W-1). The one deliberate change is registering `check_test_drift` (G-1).
     - There is no change to `GraphWorkflow` node or handler logic, to `<stage>.md` files, or to the trust layer (P-FR-012).
     - R025 fleet runs and AP-2.5b/2.6/2.7 are absent.
     - The GATE 1 rulings are honoured. In particular, check R9's partial rebuttal of skeptic L2 against Q2: does the ruling stand as written?
   - **The split.** 024-i is shippable alone with routing hard-off. 024-ii depends only on 024-i. The cut matches spec A.4 as adjusted by advisor D7.
   - **Claims against the code.**
     - The R3 site table: spot-check at least 10 of the 33 lines.
     - `check_test_drift` is unregistered (`src/sdlc/worker.py` `get_worker_activities` vs `src/sdlc/vcs/__init__.py:48-58`).
     - `src/sdlc/stages/code/step.py` is 998 lines.
     - `paths_exist` reads `repo_path` (`src/sdlc/stages/clarify/step.py:149-151`).
     - `_workflow_instance.py:3311` sets `input.task_queue or info.task_queue`, in the installed temporalio.
     - `Field(exclude_if=)` exists in the installed pydantic.
     - The R1 root input classes exist at the cited lines.
     - The data-model inheritance sites exist.
     - The R6 start-path lines exist.
   - **Determinism.** Can any new command be reached with routing off? Does R7's no-`patched()` reasoning hold?
   - **Repo constraints.** The 1000-line ceiling, `tests/replay/AGENTS.md` (no stored fixture written), and the cross-stage ban.
   - **Citations.** Spot-check at least 10 `file:line` refs beyond those above.
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as a numbered item with the file and section. Mark which gaps are blocking.

Reply in the pane with only the verdict word.
