# Reviewer brief: round 022 tasks, pass 1

RESET: we are planning feature 022 (E-11 MCP channel adapter); prior 021 context is unrelated — disregard it.

You are the SPEC & PLAN REVIEWER. Judge `tasks.md` **only** by spec-kit's tasks checklist method. The questions are whether every task is in the strict format (`- [ ] Txxx [P?] [USn?] description with exact path`), whether it is executable without extra context, and whether it is dependency-ordered, traceable and free of placeholders.

Artifacts are in `.specify/specs/022-mcp-channel-adapter/`. `tasks.md` is the subject. The references are:
- `plan.md` (approved pass 2);
- `spec.md` (GATE 1 rulings; FR-001..FR-018, SC-001..SC-006; US1-US4);
- `research.md` (R1-R10), `data-model.md`, `contracts/bridge-protocol.md`, `contracts/mcp-tools.md`, `quickstart.md`.

Do:
1. Run `/speckit-checklist` for the **tasks** domain. Write the result to `checklists/tasks.md`.
2. Check consistency, `/speckit-analyze` style:
   - Every plan task id (T010-T013, T020-T024, T030-T036, T040-T042, T050-T051, T060-T062, T070) is implemented by at least one tasks.md task citing `(plan Txxx)`; nothing in the plan is dropped.
   - Every FR-001..FR-018 and SC-001..SC-006 is covered (tasks.md §Traceability).
   - GATE 1 rulings are reflected:
     - Rust on rmcp;
     - elicitation fail-closed on both E1 (< 2026-07-28) and E2 (MRTR, ≥ 2026-07-28), with the no-support → directing-error consequence;
     - all twelve verbs.
   - Every skeptic disposition in plan §Skeptic disposition lands in a concrete task: TOCTOU digest, sealed single-use requestState, runtime extraction, stdout fd hygiene, kill_on_drop + PDEATHSIG, real-binary parity, Cargo.lock exemption, single check_mcp gate + verify.py parity, actor regex, answer actor gap scoped (write log), thaw_tests/budget_usd negative assertions, follow progress/cancel.
   - The implementer rules hold: no edit to `tests/test_operator_layering.py`; `tools.py` gets only the tuples + `_check_kind` + docstring; no new Python dependency; no `pytest -m temporal`; no paid runs; shared-tree staging rule.
   - Tests come before implementation for every new behaviour.
   - Every `[P]` claim is true (disjoint files, no unmet dependency).
   - Story labels match spec US1-US4 and phases are independently testable as stated.
   - Every cited path and `file:line` exists in the tree (spot-check at least 10, e.g. `src/sdlc/worker.py:128`, `src/sdlc/operator/agent.py:85-96`, `src/sdlc/dashboard/fleet.py:316`, `src/sdlc/cli.py:481`, `src/sdlc/benchmarks/cli.py:333`, `src/sdlc/schedules/apply.py:42`, `ROADMAP.md:345`, `ROADMAP.md:505`, `ARCHITECTURE.md:886`), or is explicitly marked new.
3. Put the verdict on the **first line** of `checklists/tasks.md`, exactly `VERDICT: approve` or `VERDICT: fixes-needed`. Number each gap below it with its task id.

Rules: edit nothing but `checklists/tasks.md`. No git commands that write. Do not run the test suite, cargo, or any `temporal` CLI command. Reply only with the verdict word.

## Pass 2 (2026-11-14)

All three pass-1 gaps were folded in:
1. **Rust test-first.** The Rust foundational block is reordered:
   - T016 = the fake bridge fixture;
   - T017 = the failing `M/tests/server.rs` "list" + "supervisor" sections against compiling `todo!()` stubs, plus `verb_names_absent`;
   - T018 = implement `bridge.rs`; T019 = implement `server.rs`/`main.rs`; T020 = the Python stdio client.
   - T028 is now the failing "confirm" test section against a fail-closed `confirm.rs` stub, and T029 implements `confirm.rs`.
   - T036 now writes its "progress" section first and runs it red; respawn moved into T017's "supervisor" section.
   - The Tests preamble states the Rust red-against-stub rule.
   - §Dependencies, §Parallel examples and §Traceability (FR-001/003/007/012, SC-005) are renumbered accordingly.
2. **Parallel examples.** The US3/US4 bullet now keeps only the Python∥Rust pairs (T031 ∥ T036, T034 ∥ T036) and sequences the shared-file Python pairs T031 → T032 → T034 → T035. §Dependencies notes that T034 follows T032.
3. **T010's xfail** now cites T023.

Re-check those three, plus a fresh stale-id sweep (task ids were renumbered in T016-T020 and T028-T029). Overwrite line 1 of `checklists/tasks.md` with the pass-2 verdict and append a "## Pass 2" section marking each gap resolved or open.

## Pass 3 (2026-11-14)

The pass-2 items are fixed:
3. T010's parenthetical now reads "`T/mcp_fake_bridge.py` (T023)".
4. The implementer rule now reads "(T017 enforces this)".

Notes applied: §Dependencies now states T015 → T019, and the blank line before the foundational Checkpoint is restored. Re-check items 3 and 4, plus a quick stale-id sweep. Overwrite line 1 of `checklists/tasks.md` with the pass-3 verdict and append a "## Pass 3" section.
