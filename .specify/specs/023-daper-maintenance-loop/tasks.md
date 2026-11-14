# Tasks: DAPER maintenance loop — round 023a (plans, gated, never acts)

**Input**: `.specify/specs/023-daper-maintenance-loop/` — spec.md (US1–US3, FR-001..018, SC-001..007), plan.md (phases A–H), research.md (R1–R15), data-model.md, contracts/{workflow-wire,cli}.md, quickstart.md

**Tests**: REQUIRED. The plan mandates test-first, so every implementation task is preceded by a RED test task that must fail before the implementation lands. The exceptions are pure moves and docs: T008 is guarded by the existing suites, and the polish tasks are guarded by the battery.

**Sizes**: **S** ≈ ≤30 min; **M** ≈ one focused sitting. No task is L.

**Executor rules** (orchestration protocol):
- One commit per task, with the task id in the subject.
- Commit messages are subject + body only, with **no attribution trailers**.
- Never `git add -A`, never stash, never revert files you did not create.
- `S/` = `src/sdlc/`, `T/` = `tests/`.

## Format: `[ID] [P?] [Story] Description (size)`

---

## Phase 1: Setup

- [ ] T001 Capture the fast-tier baseline. Run `uv run pytest -q` on current `main` in a throwaway `git worktree`, write the sorted FAILED ids to `.specify/specs/023-daper-maintenance-loop/baseline-failures.txt` with a header naming the commit, and diff against `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`. Report any novel id rather than proceeding silently. (plan A1) **(S)**
- [ ] T002 [P] Create the package skeleton: `S/maintenance/__init__.py`, plus `S/maintenance/AGENTS.md` with the local invariants. The invariants are: the loop never writes to a repository; the repair gate is built in code, never from config; `step`/`confidence_floor`/`gate.py` are pure; maintenance imports triage types only. Also create `T/maintenance/__init__.py`. (plan B, G1) **(S)**
- [ ] T003 [P] Add a fixture git repo factory in `T/maintenance/conftest.py`. It builds a tmp repo with a passing build, plus helpers to commit a build break, a committed `.env` (MECHANICAL secret), and a provider-credential line (JUDGEMENT secret), and returns `repo_dir`. Also add a `RepoTriage` builder for pure tests (findings per signal, collected/not-collected, signal versions), with a helper that seeds a critical `dependencies` advisory finding. Advisory faults are exercised at the pure tier, because the workflow tier runs with `advisory_source=none` (no OSV egress in tests). (quickstart §1–§2) **(M)**

---

## Phase 2: Foundational (blocks every story)

- [ ] T004 [P] RED: write `T/maintenance/test_models.py`. `MaintenanceConfig` validation per data-model.md: the project regex; `threshold` bounds 0.5..1.0; `gate_timeout_hours` 1..168; `build_probe=True` without `ack_unattended_build_probe` is refused; `gates=`/`policy=`/`on_timeout=` are refused as extra fields, with the field named in the error; `advisory_source ∈ {none,osv}`. `MaintenanceState` refuses duplicate keys among non-terminal incidents. `RepairProposal` field order is `analysis`, `actions`, `self_confidence`. (FR-001/002/008/011, R9, R14) **(S)**
- [ ] T005 Implement `S/maintenance/models.py` to make T004 green: `MaintenanceConfig`, `MaintenanceState`, `Baseline`, `Incident`, `IncidentState` (`open`, `awaiting_decision`, `approved_not_executed`, `rejected`, `timed_out`, `resolved_externally`, `escalated`, `withdrawn`, `deferred`), `RepairAction`, `RepairProposal`, `RepairPlan`, `MaintenanceSummary`, `DETECT_SIGNALS` (from `S/triage/signals/{secrets,build_probe,dependencies}.SIGNAL_ID`), `MAX_PREV_FINDINGS=2000`. All `extra="forbid"`. (data-model.md) **(M)**
- [ ] T006 [P] RED: write `T/maintenance/test_gate.py`. `repair_gate_settings(cfg, "repair:3")` yields `GateConfig(policy=SOFT, threshold=cfg.threshold, on_timeout=REJECT)` under exactly that name, with `gate_timeout_hours=cfg.gate_timeout_hours`. `escalation_gate_settings` yields HARD + REJECT. No input combination yields OFF, APPROVE or HOLD (parametrize over every valid config corner). (FR-011, R9) **(S)**
- [ ] T007 Implement `S/maintenance/gate.py` (pure) to make T006 green. **(S)**
- [ ] T008 [P] Lift `triage_gates` from `S/workflows/tidyup.py:150-162` into the new `S/workflows/triage_child.py`, unchanged, and re-export it from `tidyup.py` so every existing import keeps working. Run the existing TidyUp tests plus `pytest -q tests/replay/`; both must stay green with zero fixture changes. (R5, plan E1) **(S)**
- [ ] T009 [P] RED: write `T/maintenance/test_role.py`. The registry exposes an optional `maintainer` proposer whose `output_type` is `RepairProposal`. `t_maintainer` is in `ALL_TEMPORAL_AGENTS`. `maintainer` is **not** in the ADR-6 judge set (`check_adr6_families` unchanged). (R8) **(S)**
- [ ] T010 Add the role in `agents/maintainer/agent.yaml` (`kind: proposer`, model as `agents/planner/agent.yaml`), `agents/maintainer/agent.py` (pattern of `agents/risk/agent.py`, `name="maintainer_agent"` with a NEVER-rename comment), and `agents/maintainer/instructions.md` (evidence-first; propose code_fix/ops actions; self-rate confidence; never claim execution). Optionally set `validation_retries` in `agent.yaml` per the FR-202 knob. Wire it in `S/agents/roles.py` exactly as `risk` is (`roles.py:132-133,226,310,338-339`), and in `S/agents/loader.py` only if needed. Update the registry tests touched by precedent commit `73a809c0`: `T/test_agents_registry.py`, `T/test_agent_folders.py`, `T/docs_site/test_agent_registry.py`, `T/test_benchmark_provenance.py`, and a fake in `T/conftest.py`. T009 goes green. `pytest -q tests/replay/` must show zero golden changes. (R8, plan C1–C3) **(M)**

**Checkpoint**: models, the gate builder, the role and the triage_gates lift are in place. The fast tier sits at the baseline.

---

## Phase 3: User Story 1 — a new problem becomes a gated repair plan (P1) 🎯 MVP

**Goal**: enable → cycle 1 records the baseline → a seeded fault → cycle 2 opens one incident, one plan and one pending `repair:<n>` gate, with zero repository writes.

**Independent test**: quickstart §2 bullet 1, through `pytest -q -m temporal tests/maintenance/test_workflow_us1.py`.

- [ ] T011 [P] [US1] RED: write `T/maintenance/test_confidence.py` over the R8 table. MECHANICAL ceiling 0.95; −0.15 if not reproduced; −0.2 per reopen; −0.05 per action beyond 1; JUDGEMENT ceiling 0.6; STRUCTURAL 0; never below 0. `effective == min(self, floor)`. The function is order-independent and pure. (FR-010) **(S)**
- [ ] T012 [US1] Implement `S/maintenance/confidence.py::confidence_floor(finding, *, reproduced, reopens, n_actions)` to make T011 green. **(S)**
- [ ] T013 [P] [US1] RED: write `T/maintenance/test_incidents.py` for `step(state, curr)`:
  - first triage → baseline recorded, 0 incidents (SC-001);
  - **for each of the three detect kinds** (build_probe, dependencies advisory, secrets), parametrized: a seeded NEW identity not in baseline → exactly one incident (no, key=`finding_identity`, commit_sha, cycle), and its recurrence attaches without a second incident (SC-001's per-kind matrix);
  - PERSISTED on an open incident → `seen_count` + 1, no second incident;
  - RESOLVED with the signal collected on both sides → `resolved_externally`;
  - UNVERIFIABLE → no transition;
  - a signal-version change → that signal is re-baselined and the event recorded;
  - not-collected two cycles running → a `detect_escalation` incident keyed `<signal>:not_collected::`;
  - configured-off signals (`advisory_source=none`, `build_probe=False`) never increment a streak;
  - an excess beyond `max_new_incidents_per_cycle` → `deferred`, picked up next cycle;
  - `prev` over `MAX_PREV_FINDINGS` → `detect_truncated` and no incidents;
  - findings of non-`DETECT_SIGNALS` signals are ignored;
  - output is byte-identical across input orderings.

  (FR-006/007/008, R5–R7) **(M)**
- [ ] T014 [US1] Implement `S/maintenance/incidents.py::step` using `S/triage/delta.py::compute_delta` and `S/triage/models.py::finding_identity` (never a set difference) to make T013 green. **(M)**
- [ ] T015 [P] [US1] RED: write `T/maintenance/test_render.py`. The repair prompt is ≤ 16 KiB, with the evidence excerpt bounded. The `GateContext` text names the incident, the plan, and the floor/self/effective confidence, and carries an "approval does NOT execute in 023a" line. The CLI incidents table has columns `INC-n  state  key  seen  eff.conf  gate` (contracts/cli.md). **(S)**
- [ ] T016 [US1] Implement `S/maintenance/prompt.py::render_repair_prompt` and `S/maintenance/render.py` to make the render RED test green. **(S)**
- [ ] T017 [US1] RED: write `T/maintenance/test_workflow_us1.py` (`@pytest.mark.temporal`), with the fake maintainer from T010 and the T003 repo:
  - start `MaintenanceWorkflow` with a fresh state and nudge → cycle 1, baseline recorded, `incidents` query empty;
  - commit a build break and nudge → one incident `build_probe:…`, a plan with all three confidences, `pending_decisions` showing `repair:1`;
  - the repo's `git for-each-ref`, `git worktree list` and HEAD are unchanged across the test (SC-002);
  - a proposer exception → `open` with note `analysis_failed`, retried next cycle, `escalated` after `max_plan_attempts`;
  - a plan with zero actions → still gated, rendered "no action proposed";
  - the captured history replays clean through `temporalio.worker.Replayer`.

  (US1 AC1–5, FR-009/014/016, R13) **(M)**
- [ ] T018 [US1] Implement `MaintenanceWorkflow(GateHost)` in `S/workflows/maintenance.py`:
  - `@workflow.run` takes a `MaintenanceState`;
  - `nudge` sets `_nudged`; `incidents` and `maintenance_state` queries;
  - the cycle: child `TriageWorkflow` with id `maint-<p>-c<n>-triage` and `triage_gates(..., gating=False)` from `S/workflows/triage_child.py` → `step` → for each incident needing a plan, `t_maintainer.run(render_repair_prompt(...), **run_kwargs)` in the `AssessmentWorkflow._judge` degrade shape. `run_kwargs` forwards `retries={"output": n}` only when `OUTPUT_RETRIES.get("maintainer", 1) != 1`, mirroring FR-202 VR-3a at `S/workflows/assessment.py:685-695` → a `RepairPlan` → a gate coroutine (`self._gate("repair:<n>", repair_gate_settings(...), auto_decision=<APPROVE by policy iff effective>=threshold>, confidence=effective, author_model=...)`) tracked in `_gate_tasks`, recording the outcome on the incident (approve → `approved_not_executed`).

  Gates never block the cycle (R3). Make T017 green. (R1–R3, R5, R8, R9) **(M)**
- [ ] T019 [US1] Register `MaintenanceWorkflow` in `S/worker.py` `workflows=[...]`. Add its attribute rows (`_state`, `_nudged`, `_disabling`, `_running`, `_gate_tasks`) to `S/workflows/AGENTS.md`, noting that it is a GateHost-only host. (contracts/workflow-wire.md) **(S)**
- [ ] T020 [P] [US1] RED: write `T/maintenance/test_cli.py` for `enable` and `incidents` with a mocked Temporal client:
  - `enable` validates `MaintenanceConfig`;
  - `enable` refuses a non-git path (exit 1);
  - `enable` requires exactly one of `--ack-unattended-build-probe` / `--no-build-probe` (exit 2 otherwise);
  - `enable` refuses `--gate-policy` / `--on-timeout` (exit 2);
  - `enable` starts id `maint-<p>`, and "already enabled" → exit 1;
  - `incidents [--all] [--state]` renders the T016 table.

  (contracts/cli.md, FR-001/002/015) **(S)**
- [ ] T021 [US1] Implement `S/maintenance/cli.py::register_maintain_subparsers` / `run_maintain` for `enable` and `incidents`. Hook them into `S/cli.py` with ≤ 10 lines, following the `benchmarks.cli` precedent at `cli.py:357-359`. `cli.py` must stay < 1000 lines. Make T020 green. (R12) **(S)**
- [ ] T022 [US1] RED: write `T/maintenance/test_inbox_decide.py`. (a) Fast tier: `fetch_inbox` lists a `MaintenanceWorkflow` pending `repair:1` item (mocked client). (b) `@pytest.mark.temporal`, the **R11 check**: `sdlc reject maint-<p> …` (the existing decision path, `S/cli.py:859-870` → `S/channels/transport.py`) resolves `repair:1` → incident `rejected`. Expected RED today on (a); (b) may already pass, so record its result. (FR-015, R11) **(S)**
- [ ] T023 [US1] Add `"MaintenanceWorkflow"` to the inbox types at `S/channels/inbox.py:116` so (a) goes green. If (b) is red, add `sdlc maintain decide <project> <gate> {approve,reject} [--comment]` over the same transport, per contracts/cli.md, and switch (b) to that verb. Record which path applied for verification.md. (FR-015, R11) **(M)**

**Checkpoint**: US1 is independently demonstrable. This is the MVP.

---

## Phase 4: User Story 2 — silence and configuration can never open the gate (P1)

**Goal**: timeout → `timed_out`; reject → `rejected` with actor/reason; policy approval recorded as `policy`; no configuration path reaches the gate.

**Independent test**: `pytest -q -m temporal tests/maintenance/test_workflow_us2.py`, plus T004/T006.

- [ ] T024 [US2] RED: write `T/maintenance/test_workflow_us2.py` (`@pytest.mark.temporal`, time-skipping env):
  - a below-threshold plan + time skip past `gate_timeout_hours` → `timed_out`, `decision.decided_by == "timeout"`, never `approved_not_executed` (SC-003);
  - a JUDGEMENT finding (provider-credential secret) at self-rating 1.0 → effective ≤ 0.6 → gated;
  - a MECHANICAL finding (`.env`) reproduced on two consecutive cycles with self 0.9 → `approved_not_executed` with `decided_by == "policy"`;
  - a human reject with a comment → `rejected`, with actor and reason recorded and no re-plan while that incident lives;
  - a REVISE outcome → treated as reject, with guidance kept in `note`;
  - the gate's notify activity is called (fake notify registered);
  - replay is clean.

  (US2 AC1–5, FR-010/011/012) **(M)**
- [ ] T025 [US2] Make T024 green in `S/workflows/maintenance.py`: outcome mapping per data-model §IncidentState, "reproduced" tracking across cycles, the REVISE-as-reject rule and decider recording. No change to `S/workflows/gates.py` is allowed; if one seems needed, stop and report. **(S)**

**Checkpoint**: US1 and US2 both pass; the trust-layer claims are proven.

---

## Phase 5: User Story 3 — schedule, nudge, one cycle at a time, bounded (P2)

**Goal**: the E-14 schedule asset kicks the loop; nudges coalesce; history rolls over at idle; disable withdraws.

**Independent test**: `pytest -q tests/maintenance/test_schedules.py` and `pytest -q -m temporal tests/maintenance/test_workflow_us3.py`.

- [ ] T026 [P] [US3] RED: write `T/maintenance/test_schedules.py` (and extend `T/` schedules tests as found):
  - **back-compat:** `to_temporal(<schedules/nightly-reflect.yaml asset>)` equals a pinned expected value captured **before** the change (write the pin first, against current code);
  - a `MaintenanceKickWorkflow` asset loads, converts and round-trips through `from_temporal`;
  - a sub-hourly cron (`*/15 * * * *`) is refused for kick assets only;
  - an unknown workflow is still refused;
  - reconcile/diff output for a reflect-only set is unchanged.

  (FR-003, R10) **(S)**
- [ ] T027 [US3] Implement the discriminated `ScheduleAction` (`ReflectAction` | `MaintenanceKickAction{project}`) in `S/schedules/models.py`, and per-type dispatch in `to_temporal` / `from_temporal` in `S/schedules/apply.py`. Add `MaintenanceKickInput{project}` to `S/maintenance/models.py` (not the workflow module), so T027 depends only on Phase 2. Make T026 green while existing schedules tests stay green. **(M)**
- [ ] T028 [US3] RED: write `T/maintenance/test_workflow_us3.py` (`@pytest.mark.temporal`):
  - **kicker:** `MaintenanceKickWorkflow("p")` with the loop running → returns `nudged:p` and a cycle runs; with no loop → returns `not-enabled:p` and does not retry;
  - **coalescing:** three nudges during a running cycle → exactly one follow-up cycle (cycle counter +2 total), never overlapping (SC-004);
  - **roll-over:** `max_cycles_per_history=2` → `continue_as_new` happens only when idle, open incidents and the baseline are equal after the roll-over, and a pending gate defers the roll-over until it resolves (SC-005);
  - **restart:** restart the worker mid-cycle → no duplicate incident or gate;
  - **disable:** with an open gate → incident `withdrawn` (no `GateDecision`), workflow returns `disabled:p`;
  - **re-enable:** starts fresh with a new baseline;
  - replay is clean, including across the roll-over.

  (US3 AC1–5, FR-004/005/013/014/018, R2/R4/R15) **(M)**
- [ ] T029 [US3] Implement in `S/workflows/maintenance.py`:
  - `MaintenanceKickWorkflow`: `get_external_workflow_handle("maint-<p>").signal("nudge")`, catching not-found deterministically;
  - the `disable` signal and gate withdrawal (cancel coroutines, set `withdrawn`);
  - the idle-boundary `continue_as_new` (`is_continue_as_new_suggested()` or the cycle cap, `_gate_tasks` empty, `workflow.all_handlers_finished()`), carrying `MaintenanceState`.

  Register `MaintenanceKickWorkflow` in `S/worker.py`. Make T028 green. File must stay < 1000 lines (target ~350–450). **(M)**
- [ ] T030 [US3] RED: extend `T/maintenance/test_cli.py`. `nudge <p>` and `disable <p>` signal `maint-<p>` (mocked client). Not-enabled → exit 1 with `not enabled: <p>`. `schedules/maint-example.yaml.sample` exists and is ignored by the loader (it globs `*.yaml`, `S/schedules/loader.py:37`). (FR-003/004/018, contracts/cli.md) **(S)**
- [ ] T031 [US3] Add `nudge` and `disable` to `S/maintenance/cli.py`, and add the sample asset `schedules/maint-example.yaml.sample`, to make the CLI RED test green. **(S)**

**Checkpoint**: all three stories are independently green.

---

## Phase 6: Polish, docs riders and close-out

- [ ] T032 ROADMAP and docs status for what landed, with no PRD change:
  - `ROADMAP.md` FR-501 → `[ ]` ⚠️ "loop + schedule + nudge + gate landed (023a, 2026-11-xx); execute/report in 023b".
  - FR-503 → `[ ]` ⚠️ "gate half".
  - The P4 row note.
  - `docs/roadmap/filesystem-first.md:78` E-14 → `[x]` with a note.
  - The `ARCHITECTURE.md` §7 status banner updated, recording the deliberate narrowing of Detect inputs (CI, quarantined tasks and error budgets are not built; deploy liveness pending 023b).

  (plan G2) **(S)**
- [ ] T033 Record the Option B override:
  - `ROADMAP.md` §8: item 8's DAPER/two-pools moved to the top as the active program; item 5 marked parked with a link to `.specify/specs/parked-swarm-mode-skeleton/spec.md`.
  - `docs/roadmap/ordering.md`: the banner rewritten to "2026-11-14 — owner chose P4 first".
  - `docs/intent/2026-11-11-swarm-mode-and-poc-finish.md`: a **dated addendum section** at the end recording the 2026-11-14 owner override and the Q2/Q3 standing rulings. The body is not edited.

  (plan G3) **(S)**
- [ ] T034 Fix the stale paths and boxes: `ROADMAP.md:475,479,482,486` `benchmarks/sc_rollup.py` → `src/sdlc/benchmarks/sc_rollup.py` (four copies today; grep the repo docs for any others and fix them in the same commit); `docs/roadmap/agent-architecture-plan.md:26` AP-1.0 → `[x]` with "landed 2026-11-11 (judges on `zai:glm-5.3-flash`)". (plan G4/G5) **(S)**
- [ ] T035 Add a `docs/roadmap/last-verified-log.md` entry and update the `ROADMAP.md` "Last verified" header line. Re-read PRD FR-501..503 against the shipped behaviour and report any mismatch in verification.md without editing PRD. (plan G6/G7) **(S)**
- [ ] T036 Run the full battery (quickstart §3):
  - `ruff check .`, `ruff format --check .`, `mypy`, `python scripts/check_file_size.py`;
  - `uv run pytest -q`, with a sorted-FAILED diff against T001's `baseline-failures.txt` that must be identical;
  - `pytest -q tests/replay/`;
  - `pytest -q -m temporal tests/maintenance/ tests/test_tidyup*.py tests/test_triage_workflow_e2e.py`;
  - `git status --short tests/replay/`, which must be empty.

  Any red is fixed in the owning task's files, not suppressed. (SC-006, plan H1) **(M)**
- [ ] T037 Write `.specify/specs/023-daper-maintenance-loop/verification.md`. It maps SC-001..SC-007 to the test ids and outputs from T036, and records three things: the benchmark-provenance registry change on new records (plan risk 5), the R11 outcome (whether the fallback verb was needed), and SC-007 as "owner's run — quickstart §5" unless the owner authorised it during the round. Tick tasks.md boxes from the commit log. (plan H2) **(S)**

---

## Dependencies & execution order

- **Phase 1 → Phase 2 → stories.** T001 must finish before anything else is committed, because the baseline is taken from clean `main`.
- **Phase 2:** T004→T005, T006→T007, T009→T010. T008 is independent of the rest of the phase.
- **US1** needs T005, T007, T008 and T010. Inside it, T011→T012 and T013→T014 run in parallel with each other, then T015→T016, then T017→T018→T019, then T020→T021→T022→T023.
- **US2** needs T018 (the workflow exists). T024→T025.
- **US3:** T026→T027 can start right after Phase 2 (schedules are independent of the workflow). T028→T029 needs T018. T030→T031 needs T021 and T029.
- **Polish:** T032 needs T031, because its ROADMAP text claims schedule and nudge landed. T033/T034 can run any time after T018, but they share `ROADMAP.md` with T032, so T032→T033→T034 run in sequence. T035–T037 come last.

## Parallel opportunities

- **Phase 2:** T004, T006, T008 and T009 are different files, so they can run in parallel.
- **US1:** T011 and T013 (pure tests), then T012 and T014, alongside T016.
- **Cross-story:** T026/T027 (schedules, with the kick input in `S/maintenance/models.py`) in parallel with US1's workflow tasks.

The crew has one executor, so [P] marks safe reordering rather than concurrent writers.

## Implementation strategy

1. **MVP = Phases 1–3 (US1).** The loop detects, plans and gates, with no schedule (CLI nudge only). It is demonstrable via quickstart §2 bullet 1 and §4.
2. **Add US2,** which proves the trust layer. This is required before any live cycle.
3. **Add US3:** the schedule asset, coalescing, roll-over and disable.
4. **Polish, riders and close-out,** then GATE 3 / verification.

## Size summary

37 tasks: **24 S, 13 M, 0 L.**
- Setup: 3.
- Foundational: 7.
- US1: 13.
- US2: 2.
- US3: 6.
- Polish: 6.
