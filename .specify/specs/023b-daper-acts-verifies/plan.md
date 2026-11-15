# Implementation Plan: DAPER maintenance loop — round 023b (acts and verifies)

**Branch**: none (shared tree; spec dir `023b-daper-acts-verifies`) | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: `.specify/specs/023b-daper-acts-verifies/spec.md` (GATE 1 cleared 2026-11-15; advisor/skeptic folded — `consults/`)

`S/` = `src/sdlc/`. `T/` = `tests/`.

## Summary

When a project is enabled with `--execute`, the 023a `MaintenanceWorkflow` gains two phases after the gate: **Execute** and **Report**. With execution off, every 023a path is byte-for-byte unchanged (research R15).

- **Execute.** An approved incident passes the path-overlap check, the per-cycle and 7-day start caps, and the pure `may_execute` guard (R6, R10). It then starts **one** seeded brownfield `GraphWorkflow` child:
  - Started non-blocking, with `REJECT_DUPLICATE` + `ABANDON` and a run-id-scoped deterministic id (R1).
  - Cut from the incident's current commit, which the loop has already triaged (R3).
  - The seeded work is `seeded_work_for` for mechanical single-action plans and the new `repair_work_for` otherwise (R12).
- **Report.** Each cycle, a client-side activity probes every in-flight child (R2). When a child parks at its HARD merge gate, before any PR opens, the loop:
  1. builds the existing verification branch from the child's base plus its integration branch;
  2. re-triages it with gating off;
  3. classifies with `compute_delta` (R4);
  4. on a clean verdict, marks the incident `verified` and leaves the merge to a human;
  5. on a dirty one, sends the child's merge gate a `REJECT`, never an approve (R5), and reopens the incident (2 reopens), then escalates (R11).
- **Closure.** A collected default-branch Detect closes a `verified` incident when the identity is gone **and** the child head is an ancestor of the detected commit. This is a read-only check (R8).
- **Memory.** Every terminal incident is retained once, as a lesson (`closed`) or an experience (anything else), through the existing non-blocking retain path (R13).
- **Ops actions are never executed** (B-FR-017).

## Technical Context

**Language/Version**: Python 3.13 (existing).

**Primary Dependencies**:
- `temporalio` 1.31 (existing). This is the repo's first `start_child_workflow` with `ABANDON` from a long-lived parent, and its first `activity.client()` use. External signal and cancel from workflow code have 023a precedent.
- `pydantic`. No new packages.

**Storage**: none. Workflow state is carried across `continue_as_new` (ADR-8).

**Testing**:
- The fast tier covers the pure `S/maintenance/execution.py`, `incidents.py`, `models.py` and `tidyup/backlog.py` additions.
- `-m temporal` covers e2e with a **stub child workflow registered under the name `GraphWorkflow`** in the test worker. It is scripted per test: fix or non-fix commit on `sdlc/<id>/integration`, park at `merge`, honour `submit_gate_decision`. It serves the same `pending_decisions`/`run_state` queries.
- Fixture git repos come from `T/maintenance/conftest.py`. Determinism is proven by in-test `Replayer`.

**Target Platform**: the existing worker on the single `ai-sdlc` queue. Children run on the same queue; the pools split is R024.

**Project Type**: backend workflow and CLI inside the `sdlc` package.

**Performance Goals**:
- At most 1 child start per cycle by default.
- The probe is one describe plus two queries per in-flight child.
- Verification is one merge plus one triage child (≤ 40 min, the probe bound).

**Constraints**:
- The 1000-line ceiling (R16).
- The loop makes no git mutation (B-FR-016). All git writes are in `S/vcs/` activities or inside children.
- No stored replay golden changes.
- Shared tree: never `git add -A`, never stash.
- No paid run (B-FR-022).
- `GraphWorkflow` is **not modified**.

**Scale/Scope**: one operator, a handful of projects, at most `max_starts_per_window` (3) children per project per 7 days.

## Constitution Check

`.specify/memory/constitution.md` is an unfilled template. The binding rules are root `AGENTS.md`, `S/workflows/AGENTS.md`, `S/maintenance/AGENTS.md` and `T/replay/AGENTS.md`.

| Rule (source) | How the plan complies | Status |
|---|---|---|
| 1000 physical lines per file | R16 table: the largest touched file is ~510 lines. New modules are each < 300 lines | PASS |
| Cross-stage calls banned; the producer owns its artifacts | No stage is touched. `repair_work_for` lives in `S/tidyup/backlog.py` beside its sibling. The new `MemoryKind`s live in `S/memory/models.py` (memory owns them). `ChildProbe`/`ExecutionRecord` live in `S/maintenance/models.py` | PASS |
| Handlers only on the concrete class or GateHost; one owning host per attribute (`S/workflows/AGENTS.md`) | `S/workflows/maintenance_execute.py` holds async step functions over explicit arguments. They own no attribute and define no handler. New attribute rows are added to the AGENTS.md table | PASS |
| `S/maintenance/AGENTS.md` invariants (no git mutation; triage types only; purity of domain modules) | `execution.py` is pure. The two git activities live in `S/vcs/`. `S/maintenance/activities.py` only queries Temporal. The invariant "never writes to a repository" is **reworded** in the same diff to the B-FR-016 form (approved at GATE 1, Q4) | PASS (amended with authority) |
| Replay goldens are written only by capture tests (`T/replay/AGENTS.md`) | No stored fixture changes. The 023a-state pin fixture is written by a capture test. All new paths are gated by `cfg.execute` + `workflow.patched` (R15) | PASS |
| Sandbox / artifact boundary | Plan seats edit specs. Exec seats edit code and tests. No `<stage>.md` changes | PASS |
| Trust layer (ADR-6/17/24; FR-503; brief) | Deterministic checks decide (`may_execute`, `compute_delta`, ancestry). Humans decide the risky direction: every child merge gate is approved only by a human, and judgement, mixed and reopened plans need a human decision. Judges stay independent inside the child (`_fix_gates`). The loop's only decision power over a child is `REJECT` (R5) | PASS |
| NFR-9 hostile input | `--execute` requires the unattended-build acknowledgement (R14) | PASS (accepted risk, extended to children; recorded) |

**Post-design re-check:** no violations. One item is surfaced for GATE 2: the loop gains `REJECT` authority over a child's merge gate (spec "Items the owner should see", 1).

## Phases

Each step lands green on the fast tier, and RED tests come first.

### Phase A — setup and baseline
- **A1.** Capture the fast-tier baseline on HEAD in a throwaway worktree. Record `baseline-failures.txt` here. Expect 2 ids per `f576d2f7`, and diff against 023a's file.

### Phase B — pure domain
- **B1.** `S/maintenance/models.py`: the data-model additions (config fields + validator, states, `Incident` fields, `ExecutionRecord`, `VerificationResult`, `ChildProbe`, `exec_starts`). Plus the 023a-state capture and pin test (R7).
- **B2.** `S/memory/models.py`: `INCIDENT_LESSON` and `INCIDENT_EXPERIENCE`. Check exhaustive-match sites, and fakes and recall filters, for the new kinds.
- **B3.** `S/maintenance/execution.py`: `may_execute` (R6), `choose_starts` (R10), `apply_verdict` (R11), `closure_outcome` (R8), `merge_reject_decision` (R5, REJECT-only).
- **B4.** `S/maintenance/incidents.py::step`: live-state handling for the new states, the `RESOLVED_EXTERNALLY` guard, the PERSISTED refresh, and `consecutive_seen`. The last two apply only when `execute` is on (R7, R9).
- **B5.** `S/tidyup/backlog.py::repair_work_for` (R12).
- **B6.** `S/maintenance/render.py`: `render_retention`, plus the incident-table columns (contracts/cli.md).

### Phase C — activities
- **C1.** `S/vcs/integration.py`: `is_ancestor` (read-only) and `remove_verification_tree` (idempotent). Fixture-repo tests.
- **C2.** `S/maintenance/activities.py::probe_repair_child` via `activity.client()`. Phase mapping and non-retryable classification, tested against a stub child on the temporal tier.
- **C3.** Register the three activities in `S/worker.py`.

### Phase D — the workflow
- **D1.** **First:** the ABANDON-across-`continue_as_new` proof test (R1, SC-B11). If it fails, stop and re-plan R1/R2 before D2.
- **D2.** `S/workflows/pipeline_child.py::start_repair_child` (R1). This adds no `deprecate_patch`. Also the `IdeaBrief.base_branch=<sha>` check (R3; fallback named there).
- **D3.** `S/workflows/maintenance_execute.py`: `execute_step`, `report_step` (probe → verify → verdict → reject-or-verified → cleanup), `closure_step`, `retain_step`, `timeout_step`.
- **D4.** `S/workflows/maintenance.py` wiring, all behind `cfg.execute` and `workflow.patched("maint-023b-execute")`:
  - the cycle order becomes Detect → step → closure check → plan/gate (023a) → Execute → Report;
  - the gate approve path routes to `approved` when execute is on;
  - `gate_round` is used for `repair:<n>`, and rounds opened by a refusal or a reopen carry no auto-decision (R6);
  - `reopens` is fed to the floor (R11);
  - disable marks in-flight incidents `withdrawn` without cancelling children;
  - the roll-over carry covers the new fields.
- **D5.** Temporal e2e plus in-test replay for every quickstart §2 bullet, and the 023a e2e suite unchanged with execute off.

### Phase E — operator surfaces
- **E1.** `S/maintenance/cli.py`: `--execute` and the cap flags, with refusals, the client-side preconditions (R14) and the help note on the window reset.
- **E2.** CLI tests for every refusal in contracts/cli.md.

### Phase F — docs and riders (S tasks)
- **F1.** `S/maintenance/AGENTS.md`: reword the "never writes" invariant to the B-FR-016 form, and add the REJECT-only rule. `S/workflows/AGENTS.md`: new attribute rows. A pointer to this round's wire contract.
- **F2.** `ARCHITECTURE.md` §7 banner: Execute and Report built (023b); ops actions are proposal-only; rollback and deploy liveness are deferred past P4.
- **F3.** `ROADMAP.md`:
  - FR-502 stays `[ ]` with the note "code-fix clause delivered (023b); ops clause open — honest partial at P4 close".
  - FR-501 and FR-503 ⚠️ notes updated.
  - FR-401 incidents note.
  - The `last-verified-log.md` entry and "Last verified" cell.
- **F4. Threshold-wording rider.** `.specify/specs/023-daper-maintenance-loop/research.md:111` changes `>=` to `>`, with a dated note, and the verification note's pointer is corrected (spec Part D.1). This is an edit to a closed round's research doc, limited to a factual correction. The round's executor makes it in T051, following 023a's precedent for docs riders.
- **F5.** PRD untouched. FR-502 is re-read against the shipped behaviour in `verification.md`.

### Phase G — close-out
- **G1.** The quickstart §3 battery, the sorted-baseline diff, and replay untouched.
- **G2.** `verification.md`: SC-B01..B11 mapping. The live run is recorded as an owner-deferred residual (B-FR-022). The residuals are no lesson invalidation, no stale-PR handling (including a `verified` incident whose fix never reaches the default branch), the squash-merge experience-only outcome, and advisory execution being unit-tier only (spec Part D.2).

## Skeptic / advisor disposition

| Finding | Disposition |
|---|---|
| D1 / L6.1: `execute_pipeline_child` blocks; the default parent-close policy is terminate; no re-attach after roll-over | **Adopted:** R1 (non-blocking + ABANDON + REJECT_DUPLICATE) and R2 (client probe activity). D1 proves it first |
| D1: id collision on re-enable | **Adopted:** `first_execution_run_id[:8]` in the id |
| D2: builder location | **Adopted:** `tidyup/backlog.py` (R12) |
| D3 / L1.1: verification base vs the moving head | **Adopted, stronger:** the child is cut *from* the incident's triaged commit (R3), so base, child and verification share one commit. The advisor's record-the-child's-base approach is the named fallback |
| D3: merge failure crashes; hardcoded branch name | **Adopted:** caught → `conflicted` (R4). The branch comes from the one canonical helper (R2) |
| L1.2: PR opens before verification | **Adopted:** verify at `awaiting_merge`, and REJECT on dirty (R5) |
| L1: worktree cleanup | **Adopted:** `remove_verification_tree` (R4) |
| D4: transitions, double-count, hardcoded `reopens=0` | **Adopted:** R11 + the data-model table. Retries are human-gated at 0.75, which is intended and pinned |
| D5: durable window; re-enable reset | **Adopted:** `exec_starts` (R10). The reset is documented |
| D6.1 / D6.2: closure unreachable; `RESOLVED_EXTERNALLY` pre-empts | **Adopted:** R8 (state check + guard) |
| D6.3: `DEFERRED` overloaded | **Adopted:** `QUEUED` |
| D6.4 / L6.2: `APPROVED_NOT_EXECUTED` terminal | **Adopted:** a new non-terminal `approved` under execute; the old state is kept for execute-off (R7) |
| D6.5: "branch ready" undefined; stuck child | **Adopted:** `awaiting_merge` (R2) + `child_timeout_hours` |
| D6.6 / L4 / L5: decider check, mixed plans, lowered threshold, stale reproduction | **Adopted:** `may_execute` (R6) and `consecutive_seen` + the PERSISTED refresh (R9). 023a's gate-side `reproduced` is unchanged |
| L5: clamp `effective > max(threshold, 0.8)` | **Not adopted:** it overrides 023a's settled threshold range, and R6 gives equal safety |
| L2: infra failures burn the window | **Adopted:** every start counts, configuration failures escalate on attempt 1 (R11), and enable-time preconditions (R14) |
| L3: double retention; lessons that later regress | **Adopted:** retain once at terminal entry under distinct kinds (R13). Lesson invalidation is a **residual** (reflect does not prune) |
| L3: `TAG_PROMOTED_KEYS` | **Not adopted:** the `kind` tag is already filterable |
| L6.3: multi-action child-id collision | **Adopted:** one child per attempt carries all `code_fix` actions (R12) |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/023b-daper-acts-verifies/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/{workflow-wire.md, cli.md}
├── consults/{advisor.md, skeptic.md}
├── checklists/requirements.md
├── baseline-failures.txt   (A1)
├── tasks.md                (/speckit-tasks)
└── verification.md         (G2)
```

### Source code touched

```text
src/sdlc/maintenance/models.py        additions (B1)
src/sdlc/maintenance/execution.py     NEW, pure (B3)
src/sdlc/maintenance/incidents.py     step additions (B4)
src/sdlc/maintenance/render.py        retention + columns (B6)
src/sdlc/maintenance/activities.py    NEW: probe_repair_child (C2)
src/sdlc/maintenance/cli.py           --execute + caps (E1)
src/sdlc/maintenance/AGENTS.md        invariant reworded (F1)
src/sdlc/memory/models.py             two MemoryKinds (B2)
src/sdlc/tidyup/backlog.py            repair_work_for (B5)
src/sdlc/vcs/integration.py           is_ancestor, remove_verification_tree (C1)
src/sdlc/workflows/pipeline_child.py  start_repair_child (D2)
src/sdlc/workflows/maintenance_execute.py  NEW (D3)
src/sdlc/workflows/maintenance.py     wiring (D4)
src/sdlc/workflows/AGENTS.md          rows (F1)
src/sdlc/worker.py                    3 activities registered (C3)
tests/maintenance/                    pure + temporal + cli tests, stub child, 023a-state fixture
ARCHITECTURE.md §7, ROADMAP.md, docs/roadmap/last-verified-log.md, 023a research.md:111 (F4)
```

## Traceability

| Spec | Plan |
|---|---|
| B-FR-001 | D1, D2, R1 |
| B-FR-002 | B3 (`may_execute`), R6 |
| B-FR-003 | B5, R12 |
| B-FR-004 | D2 (`_default_fix_cfg`) |
| B-FR-005 | C2, D3 (`timeout_step`), R2 |
| B-FR-006 / 006a | C1, D3 (`report_step`), R4, R5 |
| B-FR-007 | B3, D3, R3, R4 |
| B-FR-008 | B3 (`closure_outcome`), B4, C1, R8 |
| B-FR-009 | B3 (`apply_verdict`), D4 (floor), R11 |
| B-FR-010 / 011 | B1, B3 (`choose_starts`), R10 |
| B-FR-012 / 013 | B2, B6, D3 (`retain_step`), R13 |
| B-FR-014 / 015 | D3, D4, D5 (restart + roll-over tests) |
| B-FR-016 | C1, F1, D5 (no-mutation asserts outside `S/vcs`) |
| B-FR-017 | B3 (ops never executable), D5 |
| B-FR-018 / 025 | B1, E1, R14 |
| B-FR-019 / 020 | unchanged `gate.py`; D5 regression on the 023a suite |
| B-FR-021 | G1, R15 |
| B-FR-022 | quickstart §5, G2 |
| B-FR-023 | B1, B4, R7 |
| B-FR-024 | B4, R9 |
| SC-B01..B11 | B/C/D/E tests + G1 |
| Riders (spec Part D) | F2–F5 |

## Risks

1. **ABANDON across `continue_as_new` is unproven in this repo.** D1 tests it first. If it fails, R1/R2 are re-planned before any further workflow work, and the reviewer is told.
2. **`IdeaBrief.base_branch` as a sha** may be rejected by intake or context (R3). The test is in D2, and the fallback is named.
3. **The stub child must be faithful** to `GraphWorkflow`'s merge-gate wire: the queries and `submit_gate_decision` round semantics. The stub reuses `GateHost` itself, so its gate behaviour is the real code.
4. **Determinism for live 023a loops.** Every new command is behind `cfg.execute` + `patched` (R15). The 023a e2e suite with execute off is the regression gate.
5. **Squash merges give `resolved_externally`, not `closed`.** This is conservative and lowers the lesson yield. It is recorded in verification.md, not hidden.
6. **New decision authority.** The loop REJECTs child merge gates (R5). This is surfaced at GATE 2, and REJECT-only is pinned by a test.

## Complexity Tracking

None.
