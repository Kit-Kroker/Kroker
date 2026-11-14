# Reviewer brief: round 022 plan, pass 1

RESET: we are planning feature 022 (E-11 MCP channel adapter); prior 021 context is unrelated — disregard it.

You are the SPEC & PLAN REVIEWER. Judge the plan **only** by spec-kit's checklist method. The questions are whether every requirement is traceable, the steps are concrete, nothing is left as a placeholder, file paths are exact, and test commands are explicit.

Artifacts, all under `.specify/specs/022-mcp-channel-adapter/`:
- `spec.md` (GATE 1 ruled 2026-11-14; see "GATE 1 Rulings": Q1 Rust held, Q2 elicitation fail-closed, Q3 twelve verbs)
- `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/bridge-protocol.md`, `contracts/mcp-tools.md`
- background only: `advisor-answer-1.md` (partial, see its recovery note), `skeptic-answer-1.md`

Do:
1. Run `/speckit-checklist` for the **plan** domain against these artifacts. Write the checklist to `checklists/plan.md` in that directory.
2. Check spec-to-plan consistency, `/speckit-analyze` style:
   - FR-001..FR-018 and SC-001..SC-006 each map to a plan task (T0xx) and to a validation in quickstart or a test task (see plan §Traceability).
   - The GATE 1 rulings are honoured exactly:
     - Rust on rmcp;
     - (a)/(b)/(c) re-costed for all twelve verbs against rmcp docs (research R1, R2);
     - elicitation fail-closed, including the "no support → directing error until it does" consequence;
     - twelve verbs regardless of seam.
   - Every skeptic finding in `skeptic-answer-1.md` (L1-L4b, S1-S10) is dispositioned in plan §Skeptic disposition, and the disposition is actually reflected in a task.
   - The repo constraints hold:
     - 1000-line ceiling incl. `Cargo.lock`;
     - `tests/test_operator_layering.py` assertions unchanged;
     - no dashboard/worker boot import;
     - `tests/test_verify.py` parity for the new CI line;
     - bounded pins.
   - Every cited `file:line` exists in this tree (spot-check at least 10, e.g. `src/sdlc/worker.py:128`, `src/sdlc/operator/agent.py:85-96`, `src/sdlc/channels/contract.py:182-186`, `src/sdlc/cli.py:469`, `ROADMAP.md:345`, `ARCHITECTURE.md:886`).
3. Put the verdict on the **first line** of `checklists/plan.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. List each gap below it as a numbered item with the file and section.

Rules:
- Do not edit any artifact other than `checklists/plan.md`.
- No git commands that write. Do not run the test suite, cargo, or any `temporal` CLI command.
- Reply in the pane with only the verdict word.

## Pass 2 (2026-11-14)

All four pass-1 gaps were folded in:
1. plan §Traceability now has rows for SC-001, SC-003 and SC-004.
2. research R10 now pins **every** crate as a bounded minor `"~MAJOR.MINOR"` (no bare major, no `*`), with a committed `Cargo.lock`, and T030 takes its pins from R10.
3. Constitution Check row 3 now cites T024 for the import probe. It also records the `_check_kind` helper (T022) as the other `tools.py` change.
4. spec §Test commands now runs the parity file as `SDLC_MCP_BIN=… pytest -m mcp …` and names `scripts/check_mcp.py`; the default-tier line lists the bridge, layering and task_queue tests.

Re-check only those four, plus a fresh placeholder and stale-ref sweep. Overwrite line 1 of `checklists/plan.md` with the pass-2 verdict and append a "## Pass 2" section that marks each pass-1 gap resolved or open.
