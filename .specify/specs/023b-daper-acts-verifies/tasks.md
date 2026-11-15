# Tasks: DAPER maintenance loop — round 023b (acts and verifies)

**Input**: `.specify/specs/023b-daper-acts-verifies/`:
- spec.md: US1–US6, B-FR-001..025 + 006a, SC-B01..B11
- plan.md: phases A–G
- research.md: R1–R16
- data-model.md, contracts/{workflow-wire,cli}.md, quickstart.md

**Tests**: REQUIRED (test-first). Every implementation task is preceded by a RED test task, which must fail before its implementation lands. The exceptions:
- T008 is a proof test of Temporal behaviour, not RED: if it fails, **STOP and report**, and do not work around it (plan risk 1).
- The docs and riders tasks (T048–T051) are guarded by the battery.

**Sizes**: **S** ≈ ≤30 min; **M** ≈ one focused sitting. No task is L.

**Executor rules** (orchestration protocol):
- One commit per task, with the task id in the subject.
- Commit messages are subject + body, with **no attribution trailers**.
- Never `git add -A`, never stash, never revert files you did not create.
- `S/` = `src/sdlc/`, `T/` = `tests/`.

**Standing constraints for every task**:
- `GraphWorkflow` (`S/workflows/graph.py`) is **not modified**.
- Every new workflow command path sits behind `cfg.execute` **and** `workflow.patched("maint-023b-execute")` (R15).
- No file under `T/replay/` changes.
- No git mutation in `S/maintenance/`: git writes live only in `S/vcs/` activities.
- The only `GateDecision` the loop builds for a child is `REJECT` (R5).
- No ops action is ever executed.

## Format: `[ID] [P?] [Story] Description (size)`

---

## Phase 1: Setup

- [ ] T001 Capture the fast-tier baseline. Run `uv run pytest -q` on HEAD in a throwaway `git worktree`. Write the sorted FAILED ids to `.specify/specs/023b-daper-acts-verifies/baseline-failures.txt` with a header naming the commit; 2 ids are expected per `f576d2f7`. Diff against `.specify/specs/023-daper-maintenance-loop/baseline-failures.txt` and report any novel id rather than proceeding. (plan A1) **(S)**
- [ ] T002 [P] Capture the 023a state fixture **before** any model change. Add a capture test, `T/maintenance/test_state_fixture_capture.py`, gated behind `SDLC_CAPTURE_FIXTURES=1`, that builds a representative 023a `MaintenanceState` and writes `T/maintenance/fixtures/state_023a.json`. The state covers baseline, prev, incidents in every 023a state, a plan, a policy decision and a not-collected streak. Run it once and commit the JSON. This is the fixture R7's round-trip pin loads. It is not a `T/replay/` fixture, so `T/replay/AGENTS.md` is untouched. (R7) **(S)**
- [ ] T003 [P] Add the stub repair child in `T/maintenance/stub_child.py`: `@workflow.defn(name="GraphWorkflow") class StubRepairChild(GateHost)`.
  - It takes the real `run_input` shape.
  - Per a script chosen by `run_input.idea.title` prefix (`fix:` / `nofix:` / `empty:` / `fail:` / `configfail:` / `hang:`), it commits a fix, a non-fix or nothing onto `sdlc/<workflow_id>/integration`, cut from `idea.base_branch` in the fixture repo, through `S/vcs/integration.py::setup_integration_branch`.
  - It opens a real `merge` gate through the inherited `GateHost._gate`, so `pending_decisions` and `submit_gate_decision` are the real code (plan risk 3).
  - On approve it fast-forwards the default branch to its integration head (`squash:` prefix: a squash commit instead) and returns `merged-not-deployed:stub`. On reject it returns `rejected:merge`.
  - It exposes `run_state()` with `run_id` and `status`.
  - Also add `T/maintenance/conftest.py` helpers (existing file, additions only): a temporal worker fixture registering `MaintenanceWorkflow`, `TriageWorkflow`, `StubRepairChild` and the 023b activities; `fix_commit(repo, finding)` builders per seeded fault.
  (quickstart §2, plan risk 3) **(M)**

---

## Phase 2: Foundational (blocks every story)

- [ ] T004 [P] RED: write `T/maintenance/test_models_023b.py`.
  - **Config.** New `MaintenanceConfig` fields and bounds per data-model.md (`execute`, `max_starts_per_cycle` 1–3, `max_starts_per_window` 1–10, `max_reopens` 0–2, `child_timeout_hours` 1–168). `execute=True` without `ack_unattended_build_probe`, or with `build_probe=False`, is refused. There is still no gate, policy or on_timeout field.
  - **States.** New `IncidentState` members; `TERMINAL_INCIDENT_STATES` gains only `closed`.
  - **New fields and models.** New `Incident` fields with their defaults; `ExecutionRecord`, `VerificationResult` and `ChildProbe` shapes; `MaintenanceState.exec_starts`.
  - **Duplicate keys.** The non-terminal duplicate-key validator covers the new live states.
  - **Fixture.** For `T/maintenance/fixtures/state_023a.json`: the 023a payload validates under the new models; every 023a field round-trips unchanged (`json.loads` of the fixture equals the new `model_dump(mode="json")` with the 023b-added keys removed); and every 023b-added field takes its default. The test lists the 023b-added keys explicitly, so a new field cannot slip in unlisted. This is RED before T005, because the new keys and defaults are absent.
  (B-FR-010/011/018/023, R7, R10, R14) **(S)**
- [ ] T005 Implement the data-model.md additions in `S/maintenance/models.py` to make T004 green. All new fields have defaults, and every model keeps `extra="forbid"`. **(M)**
- [ ] T006 [P] RED: write `T/test_memory_kinds_023b.py`. `MemoryKind.INCIDENT_LESSON == "incident_lesson"` and `INCIDENT_EXPERIENCE == "incident_experience"`. `FakeMemory` retains and recalls both with a `kind` filter. `HindsightMemory`'s `_filter_tags` accepts a `kind` filter for both without raising (`S/memory/hindsight_client.py:79,99`). (R13) **(S)**
- [ ] T007 Add the two kinds in `S/memory/models.py:20`. Grep `MemoryKind.` across `S/` and `T/` for exhaustive matches or kind lists (e.g. docs-site generators, recall filters), and update each one found. Make T006 green. **(S)**
- [ ] T008 [P] PROOF (not RED): write `T/maintenance/test_abandon_proof.py` (`-m temporal`).
  - A throwaway parent workflow defined in the test starts `StubRepairChild` (`hang:` script) via `workflow.start_child_workflow(..., parent_close_policy=ParentClosePolicy.ABANDON, id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)`, then calls `continue_as_new`.
  - Assert that the child is still running and that the new parent run can `get_external_workflow_handle(id).signal(...)` it.
  - Assert that terminating the parent leaves the child running.
  - Assert that a second start of the same id raises `WorkflowAlreadyStartedError`.
  - **If any assertion fails, STOP and report to the orchestrator before any task after T009** (plan D1, risk 1). (R1, SC-B11) **(S)**
- [ ] T009 RED: write `T/maintenance/test_start_repair_child.py`.
  - **Temporal tier.** `start_repair_child` returns without awaiting the child. The child runs with ABANDON. A second call with the same id returns `attached`, not an error. No `deprecate_patch` marker appears in the history.
  - **Fast tier.** `build_run_input(IdeaBrief(mode=BROWNFIELD, base_branch="<40-hex sha>"), _default_fix_cfg(), SeededWork)` succeeds. The intake stage's brownfield validation in `S/stages/intake/` does not reject a sha `base_branch` (call its pure validator if one exists; otherwise assert on `setup_integration_branch` with a sha `from_ref` against the fixture repo).
  - **If intake rejects a sha,** record it in the task's commit body and switch to R3's named fallback (record the child's actual base from `RunState`). Do not weaken the test.
  (R1, R3) **(M)**
- [ ] T010 Implement `start_repair_child(*, child_id, idea, cfg, seeded, task_queue) -> Literal["started","attached"]` in `S/workflows/pipeline_child.py`, beside `execute_pipeline_child` (unchanged). It reuses `build_run_input`, and calls `start_child_workflow` with `REJECT_DUPLICATE` + `ABANDON`, mapping `WorkflowAlreadyStartedError` to `"attached"`. Make T009 green. **(S)**
- [ ] T011 [P] RED: write `T/test_vcs_maint_verify.py` against the fixture repo.
  - `is_ancestor(repo, a, d)` returns True and False on real commits and never mutates (assert `git for-each-ref` and `git status` byte-equal).
  - `remove_verification_tree(repo, key)` removes `<worktrees_root>/<key>/verify` and the ref `sdlc/tidyup-verify/<key>`, is idempotent on a second call, and never raises when both are already absent.
  - `build_verification_branch` with a single-element `branches` list and `tidyup_id=<child id>` produces the ref under that key.
  (R4, R8, B-FR-016) **(S)**
- [ ] T012 Implement the `is_ancestor` and `remove_verification_tree` activities in `S/vcs/integration.py`. Use `git merge-base --is-ancestor` with exit codes mapped (0 → True, 1 → False, otherwise raise). Removal mirrors `cleanup_run_dir`'s tolerance (`S/vcs/worktree.py:253`). Make T011 green. **(S)**
- [ ] T013 RED: write `T/maintenance/test_probe.py` (`-m temporal`, `StubRepairChild`). `probe_repair_child(child_id)` maps the child's state to `ChildProbe.phase`:
  - running → `running`; parked at merge → `awaiting_merge`, with `pending_merge_round`, `integration_branch == f"sdlc/{child_id}/integration"` and `integration_head`;
  - completed → `completed`, with `result`; failed → `failed`, with `non_retryable` true for the `configfail:` script;
  - an unknown id → `not_found`.
  (R2) **(S)**
- [ ] T014 Implement `probe_repair_child` in the new `S/maintenance/activities.py`, using `activity.client()` to describe and to query `pending_decisions`/`run_state`. It makes no git mutation; `integration_head` is read with a read-only `git rev-parse`, through a helper imported from `S/vcs/integration.py`. Extract the `sdlc/{run_id}/integration` formula in `S/vcs/integration.py:47` into one helper used by both `setup_integration_branch` and the probe. Register `probe_repair_child`, `is_ancestor` and `remove_verification_tree` in `S/worker.py`. Make T013 green, with zero change under `T/replay/`. (R2, plan C2–C3) **(M)**

**Checkpoint**: models, memory kinds, the proven ABANDON semantics, the non-blocking start, and the three activities are in place. The fast tier sits at the T001 baseline.

---

## Phase 3: User Story 1 — an approved code fix runs as a child run without blocking (P1) 🎯 MVP

**Goal**: an approved, execution-authorised incident starts exactly one seeded child, the cycle does not wait on it, and every unauthorised plan is refused.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us1.py`.

- [ ] T015 [P] [US1] RED: write `T/maintenance/test_execution.py::test_may_execute_*` over the R6 matrix.
  - **Policy refused:** judgement; structural; mixed (ops + `code_fix`); ops-only; `consecutive_seen == 1`; `reopens == 1`; and `effective == threshold` (strict).
  - **Refused at threshold 0.55:** a reproduced judgement plan (floor 0.60) and an unreproduced mechanical plan (floor 0.80).
  - **Policy accepted:** mechanical + all `code_fix` + `consecutive_seen >= 2` + `reopens == 0` + `effective > threshold`.
  - **Human accepted:** any plan with at least one `code_fix`.
  - **Human refused:** an ops-only plan, with outcome `not executed — ops proposal only`.
  - **Timeout:** never.
  (B-FR-002, B-FR-017, SC-B02, SC-B03) **(S)**
- [ ] T016 [US1] Implement `may_execute(incident, plan, decision, cfg) -> Refusal | None` and `executable_actions(plan)` (the `code_fix` subset) in the new pure `S/maintenance/execution.py`. Make T015 green. **(S)**
- [ ] T017 [P] [US1] RED: write `T/maintenance/test_repair_work.py`. `repair_work_for(identity, finding, signal_version, actions)`:
  - returns one-task `SeededWork` whose acceptance criterion names the signal, rule and version;
  - lists every `code_fix` action in order, and no ops action;
  - does not contain "Change nothing else";
  - is deterministic (same input, same output).
  `seeded_work_for` is unchanged (its existing tests pass). (B-FR-003, R12) **(S)**
- [ ] T018 [US1] Implement `repair_work_for` in `S/tidyup/backlog.py`, beside `seeded_work_for:63`. Make T017 green. **(S)**
- [ ] T019 [P] [US1] RED: write `T/maintenance/test_incidents_023b.py` for `step()` with `execute=True`.
  - `approved`, `queued`, `executing`, `verifying`, `verified` and `reopened` are matched by identity, and no duplicate incident opens.
  - `approved`/`queued` + RESOLVED (collected) → `resolved_externally`.
  - `executing`/`verifying` + RESOLVED → unchanged.
  - PERSISTED refreshes `finding` and `commit_sha` and increments `consecutive_seen`. A not-collected cycle for the signal resets it to 0, and NEW sets 1.
  - With `execute=False`, the output for the same inputs equals 023a's `step()` exactly. Compare `model_dump_json()` against a run with the refresh disabled.
  (B-FR-023, B-FR-024, R7, R9) **(M)**
- [ ] T020 [US1] Implement the T019 behaviour in `S/maintenance/incidents.py`, with the refresh and `consecutive_seen` gated on `state.config.execute`. Make T019 green, and the 023a `T/maintenance/test_incidents.py` stays green unchanged. **(M)**
- [ ] T021 [US1] RED: write `T/maintenance/test_workflow_exec_us1.py` (`-m temporal`, stub child, `execute=True`).
  - **Policy start.** A mechanical `.env` fault reproduced on two cycles is policy-approved to `approved`, and the next cycle starts exactly one child with id `maint-<p>-<run8>-inc1-a1` and `base_branch == incident.commit_sha`. The cycle completes while the child is parked (`hang:`), and two more nudged cycles complete (SC-B05).
  - **Refusal round.** At threshold 0.55, a reproduced judgement (credential) plan is refused, goes back to `awaiting_decision` with a `repair:1` round 2 that has **no auto-decision**, and the operator is notified once. There is no re-approve loop across 3 cycles.
  - **Human approval.** A human-approved judgement plan starts a child seeded by `repair_work_for`.
  - **Ops.** A human-approved mixed plan starts one child with only the `code_fix`, and records the ops action `not executed — ops proposal only`. An ops-only plan starts nothing (SC-B03).
  - **Execute off.** With `execute=False`, the 023a `test_workflow_us1.py` and `test_workflow_us2.py` pass unchanged, and an approval lands `approved_not_executed`.
  - **Replay.** Each history replays through `Replayer`.
  (US1 AC1–AC4, B-FR-001/002/005/017/018) **(M)**
- [ ] T022 [US1] Implement `execute_step(state, cfg, now) -> list[...]` in the new `S/workflows/maintenance_execute.py`. These are async step functions over explicit arguments, owning no attribute and defining no handler.
  - Walk `approved`/`queued` incidents in number order.
  - Apply `may_execute`. On refusal: `awaiting_decision`, `gate_round += 1`, and notify.
  - Pick the builder: `seeded_work_for` for a mechanical single-action plan, `repair_work_for` otherwise.
  - In one step, write the `ExecutionRecord`, `attempt += 1` and `exec_starts.append(now)`, then call `start_repair_child`.
  - Mark ops actions not executed.
  Caps arrive in US5: here, honour only `max_starts_per_cycle=1`, with an interim `choose_starts` that returns the first eligible incident. T037 replaces it. **(M)**
- [ ] T023 [US1] Wire Execute into `S/workflows/maintenance.py` behind `cfg.execute` + `workflow.patched("maint-023b-execute")`:
  - the gate APPROVE routes to `approved` when execute is on (otherwise 023a's `approved_not_executed`);
  - `repair:<n>` uses `incident.gate_round`, and rounds with `gate_round > 1` are built with no auto-decision (`S/maintenance/gate.py` gains `repair_gate_settings(cfg, name, *, human_only: bool)`; the 023a call site passes `False`);
  - `execute_step` runs after the plan/gate phase.
  Make T021 green, with zero change under `T/replay/`. **(M)**

**Checkpoint**: MVP. The loop acts on authorised code fixes without blocking.

---

## Phase 4: User Story 2 — a fix is verified on a verification branch before any PR (P1)

**Goal**: a parked child is verified from its base. A clean verdict gives `verified`, with the merge left to a human. A dirty one rejects the child's merge gate.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us2.py`.

- [ ] T024 [US2] RED: add `T/maintenance/test_execution.py::test_merge_reject_*` and `::test_classify_verification_*`. This writes the same file as T015, so it is not [P] with it.
  - `merge_reject_decision(round, verdict)` returns `GateDecision(gate="merge", outcome=REJECT, decided_by="policy")`, and no function in `execution.py` builds any other outcome: a parametrized scan of every builder's output (SC-B10).
  - `classify_verification(base_triage, verify_triage, identity, conflicted)` maps `compute_delta` to `resolved`, `persisted`, `new`, `unverifiable`, `conflicted` or `absent_at_base`, with `collected` computed per the identity's signal.
  (B-FR-006a/007, R4, R5) **(S)**
- [ ] T025 [US2] Implement `merge_reject_decision` and `classify_verification` in `S/maintenance/execution.py`. Make T024 green. **(S)**
- [ ] T026 [US2] RED: write `T/maintenance/test_workflow_exec_us2.py` (`-m temporal`, stub child).
  - **`fix:`.** The child parks, the verification is built from `base_sha` + `sdlc/<id>/integration`, and the re-detect is collected and resolved. The incident goes to `verified`, with the child's merge gate **still pending** and no decision from the loop.
  - **`nofix:`.** Exactly one `REJECT` (`decided_by="policy"`) reaches the child, the child returns `rejected:merge`, and the incident goes to `reopened`.
  - **`empty:` and `fail:`.** Each is a failed attempt and goes to `reopened`.
  - **Not collected.** A not-collected verification triage, simulated through the triage fixture's not-collected path, stays `verifying`.
  - **Conflict.** A conflict gives `conflicted` and is dirty.
  - **`hang:`.** Past `child_timeout_hours` (time-skipped), the child is cancelled and the attempt is failed.
  - **Cleanup.** After each attempt, the verify worktree and `sdlc/tidyup-verify/<id>` are gone.
  - **Replay.** Each history replays through `Replayer`.
  (US2 AC1–AC5, B-FR-005/006/006a/007, SC-B01, SC-B10) **(M)**
- [ ] T027 [US2] Implement `report_step` and `timeout_step` in `S/workflows/maintenance_execute.py`, and wire them into `S/workflows/maintenance.py` after `execute_step`, under the same patch guard.
  - **`report_step`.** Probe each `executing`/`verifying` incident, then on `awaiting_merge`:
    1. record `integration_branch`/`integration_head`;
    2. run `build_verification_branch` (catching the non-conflict failure → `conflicted`);
    3. run the verify triage child `maint-<p>-<run8>-inc<n>-a<k>-verify` with `gating=False`, plus a base triage when `base_sha` is not the cycle's commit;
    4. `classify_verification`;
    5. on dirty, signal `submit_gate_decision(merge_reject_decision(...))` to the child via `get_external_workflow_handle`;
    6. run `remove_verification_tree`.
  - **`timeout_step`.** Cancel and fail a child that has not reached merge within `child_timeout_hours`.
  Make T026 green. **(M)**

---

## Phase 5: User Story 3 — a failed repair reopens, then escalates, within a bound (P1)

**Goal**: exactly three attempts at `max_reopens=2`, then `escalated`. Configuration failures escalate at once. Retries are human-gated.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us3.py`.

- [ ] T028 [US3] RED: add `T/maintenance/test_execution.py::test_apply_verdict_*` (same file as T015/T024, not [P]).
  - Dirty with `reopens` 0 → 1 → 2 → `escalated`: three attempts, then escalate.
  - `config_failed` escalates on attempt 1.
  - `resolved` → `verified`, with `reopens` unchanged.
  - The plan is cleared on reopen.
  - Plus `T/maintenance/test_confidence.py::test_reopened_mechanical_floor_is_human_gated`: `confidence_floor(mechanical, reproduced=True, reopens=1, n_actions=1) == 0.75 < 0.8`.
  (B-FR-009, R11) **(S)**
- [ ] T029 [US3] Implement `apply_verdict(incident, verdict, cfg)` in `S/maintenance/execution.py`. In `S/workflows/maintenance.py:199,252`, replace the hard-coded `reopens=0` with `inc.reopens`, and remove the "priced in already" comment. Make T028 green. The 023a suite stays green, because `reopens` is 0 there. **(S)**
- [ ] T030 [US3] RED: write `T/maintenance/test_workflow_exec_us3.py` (`-m temporal`, stub child).
  - Three `nofix:` attempts give attempts a1, a2 and a3, with one REJECT to each child, then `escalated` and one notification. Each re-plan opens `repair:<n>` at round `gate_round`, human-only, with no auto-decision even for a mechanical plan.
  - A per-cycle PERSISTED while the incident is `executing` or `verifying` never moves `reopens`.
  - `configfail:` escalates after a1 with no reopen, and one start is consumed in `exec_starts`.
  (US3 AC1–AC2, SC-B01) **(S)**
- [ ] T031 [US3] Wire the `reopened` → re-plan → human-only gate path in `S/workflows/maintenance.py`: `apply_verdict` results feed back into 023a's plan step, with `gate_round += 1` on reopen. Make T030 green. **(S)**

---

## Phase 6: User Story 4 — closure needs a later default-branch Detect (P2)

**Goal**: `closed` only when the identity is absent at a commit containing the child head. Squash merges and unmerged fixes are handled honestly.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us4.py`.

- [ ] T032 [US4] RED: add `T/maintenance/test_execution.py::test_closure_outcome_*`:
  - absent + ancestor → `closed`;
  - absent + not ancestor → `resolved_externally`;
  - present + ancestor → dirty;
  - present + not ancestor → stays `verified` with the hint "fix not on default branch";
  - not collected → no change.
  Also add to `T/maintenance/test_incidents_023b.py`: `step()` never sends a `verified`/`executing`/`verifying` incident to `resolved_externally` on RESOLVED (the guard, R8). (B-FR-008, R8) **(S)**
- [ ] T033 [US4] Implement `closure_outcome(incident, detect_collected, identity_present, child_head_is_ancestor)` in `S/maintenance/execution.py`, and the RESOLVED guard in `S/maintenance/incidents.py:216`. Make T032 green. **(S)**
- [ ] T034 [US4] RED: write `T/maintenance/test_workflow_exec_us4.py` (`-m temporal`, stub child, `fix:` script).
  - **Merge.** The incident reaches `verified`. The test sends a human `APPROVE` to the child's merge gate, the stub fast-forwards the default branch, and the next nudged cycle's collected Detect gives `closed`.
  - **Squash.** With `squash:` + `fix:`, it is `resolved_externally`.
  - **Never merged.** It stays `verified` across 2 cycles, with the hint shown by `render`.
  - **Regression.** A merged fix followed by a re-break commit gives a dirty verdict and `reopened`.
  - **Lost cycle.** A not-collected cycle between merge and closure does not strand the incident: the next collected cycle closes it (advisor D6.1).
  (US4 AC1–AC4, SC-B04) **(M)**
- [ ] T035 [US4] Implement `closure_step` in `S/workflows/maintenance_execute.py`: for `verified` incidents on each collected cycle, run `is_ancestor(repo, integration_head, cycle_commit)` and apply `closure_outcome`. Wire it into `S/workflows/maintenance.py` after Detect and before plan/gate. Make T034 green. **(S)**

---

## Phase 7: User Story 5 — execution is bounded per cycle and per project (P2)

**Goal**: at most the per-cycle and 7-day caps. Capped work is `queued`, keeps its approval, and is never re-gated.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us5.py`.

- [ ] T036 [US5] RED: add `T/maintenance/test_execution.py::test_choose_starts_*`.
  - Three eligible incidents at cap 1: one start and two `queued`.
  - A window holding 3 starts in the last 7 days: none start.
  - Starts older than 7 days, by the injected `now`, are pruned.
  - Two incidents on the same path: the second is `queued` while the first is `executing`/`verifying`.
  - Order is by incident number. One `cap_notice` per call, not per incident.
  (B-FR-010/011, R10, SC-B06) **(S)**
- [ ] T037 [US5] Implement `choose_starts(incidents, exec_starts, cfg, now)` in `S/maintenance/execution.py`, and replace T022's stub in `S/workflows/maintenance_execute.py` with it. Make T036 green, and T021 stays green. **(S)**
- [ ] T038 [US5] RED: write `T/maintenance/test_workflow_exec_us5.py` (`-m temporal`, stub child, `hang:`).
  - Three approved mechanical incidents give one start per cycle, with the others `queued`. No second `repair:<n>` gate opens for a queued incident across 3 cycles (contrast 023a `DEFERRED`).
  - With `max_starts_per_window=3` and 3 starts done, the 4th approved incident stays `queued`, with one window notification per cycle.
  - The window survives a forced roll-over (`max_cycles_per_history=2`).
  (US5 AC1–AC2, SC-B06) **(S)**
- [ ] T039 [US5] Wire the queued handling and the once-per-cycle cap notification in `S/workflows/maintenance_execute.py`, and carry `exec_starts` through `continue_as_new` in `S/workflows/maintenance.py`. Make T038 green. **(S)**

---

## Phase 8: User Story 6 — terminal incidents are retained to memory without blocking (P3)

**Goal**: one scrubbed record per terminal incident: a lesson for `closed`, an experience otherwise. An outage never fails a cycle.

**Independent test**: `pytest -q -m temporal T/maintenance/test_workflow_exec_us6.py`.

- [ ] T040 [P] [US6] RED: write `T/maintenance/test_render_023b.py`.
  - `render_retention(incident)` includes symptom (rule, path, severity), cause (plan analysis), fix (the `code_fix` actions), outcome, attempts and the source child id. It is bounded at 2000 chars.
  - `retention_kind(incident)` is `INCIDENT_LESSON` for `closed` and `INCIDENT_EXPERIENCE` for `escalated`, `rejected`, `timed_out`, `withdrawn` and `resolved_externally`, and `None` for `verified` and every non-terminal state.
  (B-FR-012, R13) **(S)**
- [ ] T041 [P] [US6] Implement `render_retention` and `retention_kind` in `S/maintenance/render.py`. Make T040 green. **(S)**
- [ ] T042 [US6] RED: write `T/maintenance/test_workflow_exec_us6.py` (`-m temporal`).
  - A closed incident (reuse T034's merge path) writes exactly one `INCIDENT_LESSON` to `FakeMemory`, in `project_bank`, with `retained` true. A further cycle writes nothing more.
  - An escalated incident writes one `INCIDENT_EXPERIENCE`.
  - With a failing memory fake, the cycle completes, the incident still closes, and there is no unhandled failure.
  - A `verified` incident writes nothing.
  (US6 AC1–AC2, SC-B07) **(S)**
- [ ] T043 [US6] Implement `retain_step` in `S/workflows/maintenance_execute.py`. It runs on every terminal entry, reads memory settings from `_default_fix_cfg().memory`, and calls the existing `retain` activity with `MEM_ACT` inside the swallow pattern of `S/workflows/memory_host.py:83-100`. It sets `retained` in the same step. Wire it into `S/workflows/maintenance.py`. Make T042 green. **(S)**

---

## Phase 9: Durability and disable (cross-story: B-FR-014/015, SC-B08/B11)

- [ ] T044 RED: write `T/maintenance/test_workflow_exec_durability.py` (`-m temporal`).
  - **Restart.** A worker killed between Execute's record step and the start acknowledgement, with `max_cached_workflows=0` and a restarted worker, gives exactly one child, one `ExecutionRecord`, one gate and one retention (SC-B08).
  - **Roll-over.** A forced roll-over while a child is parked at merge carries the execution records, `reopens`, `exec_starts` and `verification`. The child survives, and the next history's `report_step` re-attaches through the probe and verifies (SC-B11). Incidents and baseline are byte-equal across the boundary, as in 023a SC-005.
  - **Disable.** `disable` with one `executing` incident withdraws the loop's own open gates and marks the in-flight incident `withdrawn`. The child is **not** cancelled: it is still running and its merge gate is still pending.
  - **Re-enable.** A new loop's child ids differ from the old loop's (`run8`).
  (B-FR-014/015, R1) **(M)**
- [ ] T045 Implement the remaining carry and disable behaviour in `S/workflows/maintenance.py`. Roll-over is not deferred by in-flight children, only by the loop's own pending gates. Disable marks `executing`/`verifying` incidents `withdrawn` without cancelling children. Make T044 green. **(S)**

---

## Phase 10: Operator surfaces (B-FR-018/025)

- [ ] T046 RED: write `T/maintenance/test_cli_023b.py`. Each refusal in `contracts/cli.md` exits 2 with a message naming what is missing:
  - `--execute` without `--ack-unattended-build-probe`;
  - `--execute --no-build-probe`;
  - no `gh` on PATH (monkeypatch `shutil.which`);
  - no `origin` remote (fixture repo without a remote);
  - `default_branch` does not resolve;
  - a cap flag without `--execute`;
  - out-of-range values.
  Also: the help text mentions the 7-day window reset, `--gate-policy`/`--on-timeout` still do not exist (argparse exit 2), and `incidents` renders `attempt`/`reopens`/`child` and the new states verbatim. (contracts/cli.md, R14) **(S)**
- [ ] T047 Implement `--execute`, the four cap flags, the client-side preconditions and the help note in `S/maintenance/cli.py`, and the incident-table columns in `S/maintenance/render.py`. Make T046 green. `wc -l` on both files stays under 1000. **(M)**

---

## Phase 11: Polish, riders and close-out

- [ ] T048 Docs:
  - `S/maintenance/AGENTS.md`: reword invariant 1 to the B-FR-016 form ("the loop makes no git mutation; children and the `S/vcs/` verification activities write; read-only git allowed"). Add the REJECT-only rule and the `maintenance_execute.py` no-handler rule, plus a pointer to `.specify/specs/023b-daper-acts-verifies/contracts/workflow-wire.md`.
  - `S/workflows/AGENTS.md`: add the new `MaintenanceWorkflow` attribute rows.
  (plan F1) **(S)**
- [ ] T049 Update the `ARCHITECTURE.md` §7 status banner: Execute and Report are built (023b); ops actions are proposal-only; rollback and deploy liveness are deferred past P4; a dirty verdict rejects the child's merge gate. (plan F2) **(S)**
- [ ] T050 Update `ROADMAP.md`:
  - FR-502 stays `[ ]`, with the note "code-fix clause delivered (023b); ops clause open — honest partial at P4 close".
  - FR-501 and FR-503 ⚠️ notes say Execute/Report have landed.
  - FR-401 notes that incidents are retained (023b).
  - The P4 row note.
  - Prepend the full entry to `docs/roadmap/last-verified-log.md` and refresh the one-sentence "Last verified" cell (root `AGENTS.md` rule).
  The PRD is untouched. (plan F3, F5) **(S)**
- [ ] T051 Threshold-wording rider: in `.specify/specs/023-daper-maintenance-loop/research.md:111`, change `effective >= threshold` to `effective > threshold`, with a dated note ("corrected 2026-11-15 per 023a verification T025; code is strict"). In `.specify/specs/023-daper-maintenance-loop/verification.md`, add a one-line correction that the conflicting `>=` was in research R8, not data-model §R9. This is a factual correction only. (spec Part D.1, plan F4) **(S)**
- [ ] T052 Run the quickstart §3 battery on the final tree:
  - `ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py`;
  - `uv run pytest -q`, with a sorted-FAILED diff against T001's `baseline-failures.txt` that must be identical;
  - `pytest -q tests/replay/`;
  - `pytest -q -m temporal tests/maintenance/ tests/test_tidyup*.py tests/test_triage_workflow_e2e.py`;
  - `git status --short tests/replay/`, which must be empty.
  Any red is fixed in the owning task's files, not suppressed. (SC-B09, plan G1) **(M)**
- [ ] T053 Write `.specify/specs/023b-daper-acts-verifies/verification.md`.
  - **SC mapping.** SC-B01..SC-B11 mapped to the test ids and outputs from T052.
  - **FR-502 re-read** against the shipped behaviour (code-fix clause met; ops clause open).
  - **Residuals:**
    - the live execution run is owner-deferred (B-FR-022, quickstart §5);
    - no lesson invalidation;
    - no stale-PR handling (`verified` with the fix not on the default branch);
    - squash merges are experience-only;
    - advisory execution is unit-tier only;
    - the T009 outcome (sha base accepted, or the fallback used);
    - the benchmark-provenance note, if the registry was touched (it should not be).
  - Tick the tasks.md boxes from the commit log.
  (plan G2) **(S)**

---

## Dependencies & execution order

- **Setup.** T001 runs first, before anything is committed. T002 must land **before T005**, because it captures 023a state with the 023a models. T003 is independent.
- **Phase 2.** T004→T005; T006→T007; T008 (needs T003); T009→T010 (needs T003, T005); T011→T012; T013→T014 (needs T003, T012).
  - **T008 gates everything from T010 onward.** If the proof fails, stop.
- **US1** needs Phase 2 complete. T015→T016 and T017→T018 run in parallel; T019→T020; then T021→T022→T023.
- **US2** needs T023. T024→T025, then T026→T027.
- **US3** needs T027. T028→T029→T030→T031.
- **US4** needs T027. T032→T033→T034→T035. It may run beside US3, but both write `S/workflows/maintenance.py` and `S/maintenance/execution.py`, so the single executor runs them in sequence: US3 then US4.
- **US5** needs T022. T036→T037→T038→T039. It is sequenced after US4 for the same shared files.
- **US6** needs T035 for the closed path. T040→T041 may start any time after Phase 2; then T042→T043.
- **Durability** needs T039 and T043. T044→T045.
- **CLI.** T046→T047 needs T005 only. T047 writes `S/maintenance/render.py`, as T041 does, so run it after T041.
- **Polish.** T048–T051 come after T045/T047. T050 shares no file with T048/T049/T051. T052 then T053 come last.

### Shared-file sequencing (why some RED tasks are not [P])

- `T/maintenance/test_execution.py`: T015 → T024 → T028 → T032 → T036.
- `S/maintenance/execution.py`: T016 → T025 → T029 → T033 → T037.
- `S/workflows/maintenance.py`: T023 → T027 → T029 → T031 → T035 → T039 → T043 → T045.
- `S/workflows/maintenance_execute.py`: T022 → T027 → T035 → T037 → T039 → T043.
- `T/maintenance/test_incidents_023b.py`: T019 → T032.
- `S/maintenance/incidents.py`: T020 → T033.
- `S/maintenance/render.py`: T041 → T047.

## Parallel opportunities

- **Setup:** T002 and T003.
- **Phase 2:** T004, T006, T008 (after T003) and T011. These are different files.
- **US1:** T015, T017 and T019 (three different test files), then their implementations T016, T018 and T020.
- **US6:** T040/T041 alongside any of US2–US5.

The crew has one executor, so [P] marks safe reordering rather than concurrent writers.

## Implementation strategy

1. **MVP = Phases 1–3 (US1).** Authorised code fixes start as non-blocking children, and unauthorised ones are refused. This is demonstrable via `test_workflow_exec_us1.py`.
2. **US2 + US3 (P1)** add the evidence boundary: verification before any PR, REJECT on dirty, and a bounded reopen. Together with US1 this is the A.3 "023b-i" slice. If the round must be cut at plan time, cut here.
3. **US4 + US5 (P2)** add closure and caps. **US6 (P3)** adds memory.
4. **Durability, CLI, then polish, riders and close-out,** then GATE 3 / verification.

## Size summary

53 tasks: **38 S, 15 M, 0 L.**

| Phase | Tasks |
|---|---|
| Setup | 3 |
| Foundational | 11 |
| US1 | 9 |
| US2 | 4 |
| US3 | 4 |
| US4 | 4 |
| US5 | 4 |
| US6 | 4 |
| Durability | 2 |
| CLI | 2 |
| Polish | 6 |

The M tasks are T003, T005, T009, T014, T019, T020, T021, T022, T023, T026, T027, T034, T044, T047 and T052.
