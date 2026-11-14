# Implementation Plan: DAPER maintenance loop — round 023a (plans, gated, never acts)

**Branch**: none (shared tree; spec dir `023-daper-maintenance-loop`) | **Date**: 2026-11-14 | **Spec**: [spec.md](spec.md)

**Input**: `.specify/specs/023-daper-maintenance-loop/spec.md` (GATE 1 cleared 2026-11-14; advisor/skeptic folded — `consults/`)

`S/` = `src/sdlc/`. `T/` = `tests/`.

## Summary

The plan adds one long-lived `MaintenanceWorkflow(GateHost)` per project (`maint-<project>`).

- **Triggers.** It is enabled from the CLI and kicked by an E-14 schedule asset through a tiny `MaintenanceKickWorkflow`, which signals the loop from workflow code (research R1). The CLI can also nudge it. Nudges coalesce through one flag (R2).
- **Each cycle.**
  - Runs the existing `TriageWorkflow` **unchanged** as a child and keeps three signals: build probe, dependencies and secrets (R5).
  - Records a baseline on cycle 1. Later cycles classify findings with `compute_delta` (R6) and key incidents by `finding_identity` (R7).
  - Asks one new `maintainer` proposer for a `RepairProposal`. Code caps the proposal's self-rating with a deterministic floor (R8).
  - Opens a per-incident `repair:<n>` gate. The gate's config is built in code, so neither configuration nor a timeout can approve it (R9). Gates run in their own coroutines and never block the next cycle (R3).
- **Nothing executes.** An approved plan is recorded `approved_not_executed`.
- **History.** It is bounded by the repo's first `continue_as_new`, taken only at idle (R4).
- **Schedules.** The Reflect-only schedules package becomes a discriminated union. The nightly-reflect asset stays byte-identical (R10).
- **Operator surfaces.** The CLI gets `enable`, `nudge`, `incidents` and `disable`. Repair gates join the CLI inbox (R11, R12).

## Technical Context

**Language/Version**: Python 3.13 (existing). Nothing new in the toolchain.

**Primary Dependencies**: `temporalio` (existing; first use of `continue_as_new`, `get_external_workflow_handle`, `all_handlers_finished`) and `pydantic-ai` (existing; one new proposer role). No new packages.

**Storage**: none. State lives in workflow state, carried across `continue_as_new` (ADR-8).

**Testing**:
- pytest fast tier for the pure domain (`T/maintenance/`).
- `-m temporal` for workflow e2e with a `TestModel` maintainer and fixture git repos, plus in-test `Replayer` replay (R13).
- The existing replay corpus and the fast-tier baseline diff as the regression gate.

**Target Platform**: the existing worker, on the single task queue `ai-sdlc` (two pools are R024).

**Project Type**: a backend workflow plus CLI verbs inside the existing `sdlc` package.

**Performance Goals**:
- A cycle is dominated by the build probe (≤ 40 min, `PROBE_ACT`).
- Pure classification is O(findings).
- Cadence is at most hourly, enforced by the schedule validator.

**Constraints**:
- The 1000-line file ceiling. `cli.py` is at 908, so the new verbs live in `S/maintenance/cli.py`.
- No repository writes by the loop (FR-016).
- Existing replay goldens unchanged (FR-017).
- The shared working tree: never `git add -A`, never stash.
- No paid model runs except SC-007, on the owner's word.

**Scale/Scope**: one operator and a handful of projects. Each cycle is capped at 10 new incidents and 2000 prior findings.

## Constitution Check

`.specify/memory/constitution.md` is an unfilled template. The binding rules are root `AGENTS.md`, `S/workflows/AGENTS.md` and `T/replay/AGENTS.md`.

| Rule (source) | How the plan complies | Status |
|---|---|---|
| 1000 physical lines per file | New modules are each < 400 lines. `cli.py` grows ≤ 10 lines (R12). `workflows/maintenance.py` is planned at ~350 lines, with the kicker in the same file | PASS |
| Cross-stage calls banned; the producer owns its artifacts (root `AGENTS.md`) | No stage is touched. `S/maintenance/` owns its models and imports triage **types** only. The triage child is a workflow child, not a stage call | PASS |
| One owning host per attribute; handlers only on the concrete class or GateHost (`S/workflows/AGENTS.md` rules 1–4) | The signals and queries live on `MaintenanceWorkflow` itself. The new attribute rows are added to the AGENTS.md table (T-docs) | PASS |
| Replay goldens are written only by the capture tests; no hand edits (`T/replay/AGENTS.md`) | The round adds no stored fixture. New-workflow determinism is proven by in-test replay (R13). The `triage_gates` lift is an import move only | PASS |
| Sandbox / artifact boundary (root `AGENTS.md`) | Plan-side seats edit specs. Exec seats edit code and tests. No `<stage>.md` contract changes, because no stage changes | PASS |
| Fail-closed trust layer (ADR-6/17/24, PRD FR-503) | The gate config is code-built. `decided_by` is recorded. The confidence floor is code. The maintainer is not a judge | PASS |
| NFR-9 hostile input | An explicit enable-time acknowledgement, or `--no-build-probe` (R14) | PASS (accepted risk, recorded) |

Post-design re-check: there are no violations and nothing is carried in Complexity Tracking.

## Phases

Each step lands green on the fast tier, and RED tests come first (test-first, as rounds 021/022 did).

### Phase A — setup and baseline
- **A1.** Capture the fast-tier baseline on current `main` in a throwaway worktree. Record `baseline-failures.txt` in this spec dir and diff it against 021's 11-id file.

### Phase B — pure domain (`S/maintenance/`, no Temporal)
- **B1.** `models.py`: the models in data-model.md with their validators, including R9's "no gates field" rule and R14's acknowledgement.
- **B2.** `confidence.py`: the R8 floor table.
- **B3.** `incidents.py::step`: baseline, `compute_delta` classification, opens/attaches/resolutions, not-collected streaks, the per-cycle cap, the `prev` cap, and signal-version re-baselining.
- **B4.** `gate.py`: `repair_gate_settings` and `escalation_gate_settings`.
- **B5.** `prompt.py` and `render.py`: a bounded prompt, the `GateContext` text and the CLI table.

### Phase C — the proposer role
- **C1.** `agents/maintainer/{agent.yaml, agent.py, instructions.md}`, with `output_type=RepairProposal` (evidence first).
- **C2.** Wiring in `S/agents/roles.py` (optional role, the `risk` pattern) and `S/agents/loader.py` if needed. The direct call forwards the FR-202 per-role validation-retry count (VR-3a pattern, `S/workflows/assessment.py:685-695`).
- **C3.** The registry tests named in R8, following commit `73a809c0`'s precedent, plus a fake in `T/conftest.py` / `T/fakes/`.

### Phase D — schedules generalisation (R10)
- **D1.** A discriminated `ScheduleAction` with `MaintenanceKickAction` and the cron validator.
- **D2.** `apply.py` dispatch in `to_temporal` / `from_temporal`.
- **D3.** A back-compat pin test for the reflect asset, plus kick-asset round-trip and refusal tests.

### Phase E — the workflows (`S/workflows/maintenance.py`)
- **E1.** Lift `triage_gates` into `S/workflows/triage_child.py`, re-exported from `tidyup.py`.
- **E2.** `MaintenanceWorkflow`: run loop, `nudge`/`disable` signals, queries, the cycle (triage child → `step` → plan → gate coroutines), the proposer degrade path, `continue_as_new` at idle, disable withdrawal.
- **E3.** `MaintenanceKickWorkflow`: an external signal, finishing `not-enabled` when the loop is absent.
- **E4.** Register both in `S/worker.py`.
- **E5.** Temporal e2e plus in-test replay for every quickstart §2 bullet.

### Phase F — operator surfaces
- **F1.** `S/maintenance/cli.py`: `enable`, `nudge`, `incidents`, `disable`, plus the ≤ 10-line hook in `cli.py`.
- **F2.** Add `"MaintenanceWorkflow"` to the types in `S/channels/inbox.py:116`.
- **F3.** R11 check that `sdlc approve|reject maint-<p>` resolves the gate. Add the `maintain decide` fallback only if it does not.
- **F4.** CLI tests.

### Phase G — docs and riders (S tasks)
- **G1.** New rows in `S/workflows/AGENTS.md` for `MaintenanceWorkflow`. A new `S/maintenance/AGENTS.md` with the local invariants: never writes to the repo, gate built in code, purity of `step` and the floor.
- **G2.** ROADMAP:
  - P4 row note.
  - FR-501 → `[ ]` ⚠️ "loop + gate landed (023a), execute in 023b".
  - FR-503 → ⚠️ "gate half".
  - E-14 → `[x]` in `docs/roadmap/filesystem-first.md:78`.
  - The ARCHITECTURE §7 status banner updated, with a note that Detect inputs are deliberately narrowed (CI, quarantined tasks and error budgets are not built).
- **G3. Option B rider.**
  - `ROADMAP.md` §8 item 5/8 re-ranked: P4 first, swarm parked (link to the parked spec).
  - `docs/roadmap/ordering.md` banner updated.
  - A dated addendum on `docs/intent/2026-11-11-swarm-mode-and-poc-finish.md` recording the owner's 2026-11-14 override. The original body is not edited.
- **G4.** `ROADMAP.md:475` → `src/sdlc/benchmarks/sc_rollup.py`. Grep for any other copy of the stale path.
- **G5.** `docs/roadmap/agent-architecture-plan.md:26` AP-1.0 → `[x]`, with the 2026-11-11 landing note.
- **G6.** The `docs/roadmap/last-verified-log.md` entry and the ROADMAP "Last verified" header line.
- **G7.** No PRD wording change (spec assumption). The PRD FR-501..503 lines are re-read against the shipped behaviour; any mismatch is reported rather than patched.

### Phase H — close-out
- **H1.** The full battery (quickstart §3), sorted-baseline diff and replay corpus untouched.
- **H2.** A `verification.md` in this spec dir mapping SC-001..SC-007. SC-007 is marked "owner's run" unless the owner says go during the exec round.

## Skeptic / advisor disposition

| Finding | Disposition |
|---|---|
| Split into 023a/023b (both) | **Adopted.** The spec's A.3 was re-sequenced |
| Long-lived workflow + schedule kicker (advisor §1) | **Adopted**, with the external-signal kicker instead of client-in-activity (R1) |
| Children must not be awaited inline (advisor §1, skeptic (e)2) | Carried to 023b. The **same principle** applied to gates now (R3) |
| Code-computed confidence floor (advisor §2) | **Adopted** (R8) |
| `finding_identity` reuse (advisor §3) | **Adopted** (R7) |
| Baseline + `compute_delta`, never a set difference (both) | **Adopted** (R6) |
| `verified` / `AWAITING_MERGE` state (both) | Carried to 023b (spec §023b preview) |
| Gate config can be opened by `OFF` / `on_timeout=APPROVE` (both) | **Adopted.** The config reaches no gate field (R9) |
| `HOLD` never records a timeout (skeptic (c)) | Moot: the repair gate is forced to `REJECT`, never `HOLD` (R9) |
| Schedules package is Reflect-only (advisor §7.4) | **Adopted**, budgeted as Phase D (R10) |
| Project registration missing (skeptic (a)1) | **Adopted.** Enable-time `MaintenanceConfig` is the registration (FR-001) |
| Deploy liveness / rollback unbuildable today (both) | **Adopted.** Out of 023a. Whether it is in 023b goes to GATE 2 |
| `advisory_source` defaults to none (both) | **Adopted.** It is a config field, and `none` reads *not configured* |
| NFR-9 unattended probe (advisor §7.5) | **Adopted.** An acknowledgement flag (R14) |
| Secrets are always JUDGEMENT (skeptic (a)4) | **Corrected.** Credentials are JUDGEMENT, but a committed `.env` is MECHANICAL (`signals/secrets.py:5-8`). The spec edge case was reworded |
| Memory on escalation in 023a (skeptic (g)) | Not adopted. Memory moves as one piece in 023b |
| Carried to 023b, no 023a work (skeptic (a)5 stale-PR signal, (e)1 `_fix_gates` on children, (e)3 `RepairPlan → SeededWork` builder, (e)4 build-broken paradox; advisor §7.1 pinned-commit weakening) | Carried; spec §023b preview records each |
| Live cycle needs a GitHub remote (skeptic (f)) | Moot for 023a, which opens no PR. Carried to 023b |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/023-daper-maintenance-loop/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── contracts/{workflow-wire.md, cli.md}
├── consults/{advisor.md, skeptic.md}
├── checklists/requirements.md
├── baseline-failures.txt   (A1)
├── tasks.md                (/speckit-tasks)
└── verification.md         (H2)
```

### Source code touched

```text
src/sdlc/maintenance/            NEW: __init__, models, incidents, confidence, gate, prompt, render, cli, AGENTS.md
src/sdlc/workflows/maintenance.py NEW: MaintenanceWorkflow, MaintenanceKickWorkflow
src/sdlc/workflows/triage_child.py NEW: triage_gates (lifted; tidyup re-exports)
src/sdlc/workflows/tidyup.py     import move only
src/sdlc/workflows/AGENTS.md     new rows
src/sdlc/schedules/{models,apply}.py  discriminated action
src/sdlc/agents/roles.py (+loader.py if needed)  optional maintainer role
agents/maintainer/               NEW: agent.yaml, agent.py, instructions.md
src/sdlc/channels/inbox.py       one type added
src/sdlc/worker.py               two workflows registered
src/sdlc/cli.py                  ≤ 10-line hook
tests/maintenance/               NEW: pure + temporal + cli tests, fixture repo conftest
tests/ (registry tests per 73a809c0 precedent; schedules tests)
ROADMAP.md, ARCHITECTURE.md §7 banner, docs/roadmap/{filesystem-first,ordering,agent-architecture-plan,last-verified-log}.md, docs/intent/2026-11-11-…md (addendum)
```

## Traceability

| Spec | Plan |
|---|---|
| FR-001 / 002 | B1, F1, R14 |
| FR-003 | D1–D3, E3 |
| FR-004 / 005 | E2, F1, R2 |
| FR-006 | E1, E2, R5 |
| FR-007 / 008 | B3, R6, R7 |
| FR-009 / 010 | C1–C3, B2, E2, R8 |
| FR-011 / 012 | B4, E2, R9 |
| FR-013 | E2, R4 |
| FR-014 | E2, E5 (restart tests) |
| FR-015 | E2 (queries), F1, F2, F3 |
| FR-016 | E5 (no-write asserts) |
| FR-017 | H1, R13 |
| FR-018 | E2, F1, R15 |
| SC-001..006 | B/E/F tests + H1 |
| SC-007 | quickstart §5 (owner's run) |
| Riders | G2–G7 |

## Risks

1. **First `continue_as_new`.** Handler draining and the state carry are new to the repo. Mitigated by the forced roll-over test (`max_cycles_per_history=2`) plus replay.
2. **External signal to a missing workflow.** The kicker must catch the "not found" failure deterministically. Covered by an E3 test.
3. **Gate coroutines and `continue_as_new`.** A roll-over must wait for them. The idle-boundary predicate requires `_gate_tasks` to be empty, bounded by `gate_timeout_hours ≤ 168`.
4. **The decision CLI may assume GraphWorkflow** (R11). The `maintain decide` fallback is pre-scoped in contracts/cli.md.
5. **Benchmark provenance changes on new records** because the registry gains a role (the 73a809c0 precedent). Stored records are untouched. Recorded in verification.md.

## Complexity Tracking

None.
