# Research — round 023b (DAPER: acts and verifies)

`S/` = `src/sdlc/`. `T/` = `tests/`. Every decision cites the source it rests on. Spec ids: `B-FR-nnn`, `SC-Bnn`. Consults: `consults/advisor.md` (D1–D6), `consults/skeptic.md` (L1–L6).

## R1 — Non-blocking child start, deterministic id, survives roll-over

- **Decision.** A new `start_repair_child(...)` in `S/workflows/pipeline_child.py`, beside `execute_pipeline_child`. It builds the run input exactly as `execute_pipeline_child` does (`build_run_input`, the `GraphStartError` path) and calls `workflow.start_child_workflow(GraphWorkflow.run, run_input, id=child_id, task_queue=..., id_reuse_policy=REJECT_DUPLICATE, parent_close_policy=ABANDON)`.
  - It returns once the start is acknowledged and does not await the result.
  - `WorkflowAlreadyStartedError` is caught and mapped to `attached`.
  - It does **not** call `workflow.deprecate_patch(f"e74-graph-child:...")`. That patch belongs to tidyup and benchmark children's histories.
- **Child id.** `maint-{project}-{first_execution_run_id[:8]}-inc{no}-a{attempt}`. `workflow.info().first_execution_run_id` is stable across `continue_as_new` and new on every enable, so a re-enabled loop cannot collide with an abandoned child (advisor D1).
- **Recorded in the same step as the start.** The execution record (child id, attempt, base commit, start time) is written to `MaintenanceState` before the `await` on the start, so a replay of the start decision finds the record (B-FR-014).
- **Proof before reliance.** Temporal task 1 of the workflow phase (plan D1) is a temporal-tier test showing that a child started with `ABANDON` keeps running after the parent's `continue_as_new` and after the parent is terminated. Both consults flag this as the one behaviour the design rests on.
- **Rationale.** `execute_pipeline_child` awaits the child's final result (`pipeline_child.py:49`), which breaks B-FR-005. `ParentClosePolicy.ABANDON` has repo precedent (`workflows/deployment.py:9`). Under the default reuse policy a finished id could be re-run, and `REJECT_DUPLICATE` closes that.
- **Alternatives.** An inline `execute_child_workflow` on a coroutine, like 023a's gate coroutines (R3 there). Rejected because a child parked at merge for days would block `continue_as_new` indefinitely (skeptic L6.1).

## R2 — Observing a child across roll-over

- **Decision.** A new activity, `probe_repair_child(child_id) -> ChildProbe`, in `S/maintenance/activities.py`. It uses `activity.client()` (available in temporalio 1.31, verified) to `describe()` the workflow and, while it is running, to query `pending_decisions()` and `run_state()`. It returns:
  - `phase`: `running` | `awaiting_merge` | `completed` | `failed` | `cancelled` | `terminated` | `timed_out` | `not_found`
  - `pending_merge_round` (an int, or `None`)
  - `integration_branch`
  - `base_sha`
  - `result`: the outcome string, when completed
- **"Branch ready" = `awaiting_merge`.** `pending_decisions()` lists the `merge` gate (`workflows/gates.py:143-146`). The seeded graph parks at merge before it opens the PR (`workflows/graphs/seeded.graph.yaml`; `stages/merge/activities.py:189`).
- **Integration branch.** `sdlc/{child_id}/integration`. This is the single canonical construction in `setup_integration_branch` (`vcs/integration.py:47`). It is read from `RunState` (`run_id`) and built with the same formula through one shared helper extracted from `integration.py`, so the convention lives in one place. This meets the advisor's "not a naming convention" concern: the name comes from the one function that creates it.
- **Polled once per cycle,** for each incident in `executing`. No signal from child to parent is added, so `GraphWorkflow` is not touched.
- **Child execution timeout.** `child_timeout_hours` (default 24, range 1–168). On timeout the loop calls `get_external_workflow_handle(child_id).cancel()` (a workflow-side API) and counts a failed attempt (B-FR-005).
- **Alternatives.** A completion signal from the child. Rejected because it would change `GraphWorkflow` and every replay golden of it, against B-FR-021.

## R3 — Pinning the child's base commit

- **Decision.** Execute passes the incident's **current commit** (`incident.commit_sha`, kept fresh by R9) as `IdeaBrief.base_branch`. `setup_integration_branch` cuts the integration branch with `git worktree add -b <branch> <path> <from_ref>` (`vcs/worktree.py:83-94`), so a commit sha is a valid `from_ref`. The child's base is then the commit the loop already triaged, and it is recorded at start.
- **Consequence.** The "base" Detect in B-FR-006 step 2 is the cycle's already-collected triage at that commit, so no extra triage run is needed. The finding was present there by construction, because the incident was refreshed by that Detect. `resolved_externally`-at-base (B-FR-007) then arises only when the base Detect for the attempt was not the current one. Verification checks `base_sha == incident.commit_sha at start`, and otherwise re-triages the base.
- **Rationale.** This closes skeptic L1 scenario 1 (upstream commits being folded into the delta) at the root: verification merges the child branch into the same commit it was cut from. It also removes the advisor's D3 "mostly conflicts" risk.
- **Check in plan D2.** A temporal-tier test confirms that `IdeaBrief.base_branch=<sha>` passes intake and context unchanged. If intake rejects a sha, the fallback is the advisor's: record the child's actual base from `RunState`, and re-triage that base.

## R4 — Verification (Report)

- **Decision.** Report reuses `build_verification_branch` (`vcs/integration.py:123`) with:
  - `VerifyBranchInput(repo_path, base_sha=<child base>, tidyup_id=<child_id>, branches=[<integration branch>])`.
  - The `tidyup_id` field is a ref key only (advisor D3), so its name is not changed. Renaming it would touch tidyup's histories.
- **Then Detect.** The verification head is triaged with the existing triage child, `gating=False`, under the id `maint-{project}-{run8}-inc{no}-a{attempt}-verify`. That id is distinct from the cycle's triage id (`workflows/maintenance.py:171`).
- **Then the delta.** `compute_delta(base_triage, verify_triage, conflicted)`, with the verdict taken for the incident's identity:
  - `RESOLVED` → `verified`
  - `PERSISTED`, `conflicted` or `NEW` → dirty
  - `UNVERIFIABLE` → stays `verifying`
- **Failure handling.** A non-conflict merge failure after retries raises. The workflow catches it, records `conflicted`, and the verdict is dirty.
- **Cleanup.** A new activity `remove_verification_tree(child_id)` removes `<worktrees_root>/<child_id>/verify` with `git worktree remove -f` and deletes the ref `sdlc/tidyup-verify/<child_id>`. It is idempotent and never raises out. It mirrors `cleanup_run_dir` (`vcs/worktree.py:253`) and lives in `S/vcs/`, so `S/maintenance/` still makes no git mutation (B-FR-016).

## R5 — Dirty verdict rejects the child's merge gate

- **Decision.** On a dirty or conflicted verdict while the child is `awaiting_merge`, the loop signals `get_external_workflow_handle(child_id).signal("submit_gate_decision", GateDecision(gate="merge", round=pending_merge_round, outcome=REJECT, decided_by="policy", comments=<verdict line>))`.
  - The gate is first-decision-wins per (gate, round) (`gates.py:123-126`). A human who already decided wins, and the loop's signal is inert.
  - The loop never sends `APPROVE` to a child. This is a pure-function guard in `S/maintenance/execution.py` plus a test asserting that the only outcome ever built is `REJECT` (SC-B10).
- **Rationale.** No PR opens for a repair the loop has proven wrong (skeptic L1 scenario 2). This is a deterministic check deciding toward inaction, and approval stays human. It is surfaced to the owner at GATE 2 as new decision authority.
- **What the child does on reject.** It is the existing merge-reject path of `GraphWorkflow`. No change is made to it.

## R6 — Execution authority guard (B-FR-002)

- **Decision.** A pure `may_execute(incident, plan, decision, cfg) -> Refusal | None` in `S/maintenance/execution.py`.
  - **Policy path.** It returns `None` for `decided_by == "policy"` only when **all** of these hold:
    - `finding.fix_class is MECHANICAL`
    - every action has `kind == "code_fix"`
    - `incident.consecutive_seen >= 2` (new field, see R9)
    - `incident.reopens == 0`
    - `plan.effective > cfg.threshold`
  - **Human path.** For `decided_by == "human"` it returns `None` for any plan with at least one `code_fix` action.
  - **Timeout.** `decided_by == "timeout"` never executes. It cannot be an approval anyway (023a R9).
- **Refusal.** The incident goes back to `awaiting_decision`, a fresh gate round opens, and the operator is notified once.
  - **A refusal round is human-only.** A round opened by a refusal carries **no** auto-decision: the policy path is off for `repair:<n>` at that `gate_round`. Without this, at an operator threshold ≤ 0.6 a reproduced judgement plan (floor 0.60) would auto-approve, be refused, and re-open every cycle, livelocking silently, because an auto-resolved gate never reaches the inbox (plan review, gap 2).
  - **Reopen rounds** are human-only too, because a reopened plan floors at ≤ 0.75 (R11), and for uniformity.
- **Rationale.** Advisor D6.6 and skeptic L4/L5. A threshold lowered to 0.55 would otherwise let a reproduced judgement plan (floor 0.60) or a mixed plan reach policy execution (`confidence.py:48-60` ignores action kinds).

## R7 — State machine

- **Decision.** `IncidentState` gains `APPROVED`, `QUEUED`, `EXECUTING`, `VERIFYING`, `VERIFIED` and `REOPENED` (all non-terminal) and `CLOSED` (terminal). The full transition table is in `data-model.md`.
  - **`approved_not_executed` survives.** It stays terminal and is used only when `cfg.execute` is false, so 023a behaviour is byte-for-byte unchanged (B-FR-018).
  - **`DEFERRED` is untouched** (its 023a meaning). Capped work uses `QUEUED` (advisor D6.3).
- **Detect interplay.** `incidents.step` treats `APPROVED`, `QUEUED`, `EXECUTING`, `VERIFYING`, `VERIFIED` and `REOPENED` as live, so they are matched by identity and never duplicated (R7 of 023a).
  - **`RESOLVED` on the default branch:**
    - `APPROVED` or `QUEUED` → `RESOLVED_EXTERNALLY`, with no child started (skeptic L6.2).
    - `EXECUTING` or `VERIFYING` → no change. Report decides.
    - `VERIFIED` → closure check (R8).
  - **`PERSISTED`:** refresh the finding and commit (R9). Never reopen (advisor D4).
  - **A `VERIFIED` identity reappearing:** the verdict is dirty, so it reopens under the bound.
- **Persisted 023a state.** New enum members are additive, and old payloads validate unchanged. The R7 duplicate-key validator (`maintenance/models.py:248-263`) keys on `TERMINAL_INCIDENT_STATES`, which gains only `CLOSED`. A pin test loads a 023a `MaintenanceState` JSON fixture (written by a capture test, not by hand) and asserts that the 023a payload validates under the new models; every 023a field round-trips unchanged (`json.loads` of the fixture equals the new `model_dump(mode="json")` with the 023b-added keys removed); and every 023b-added field takes its default. A byte-equal re-dump is impossible once fields with defaults exist (tasks review, gap 1).

## R8 — Closure (B-FR-008)

- **Decision.** A `VERIFIED` incident whose identity is absent from a collected default-branch Detect goes through a read-only activity, `is_ancestor(repo, ancestor=<child integration head>, descendant=<detect commit>)`, in `S/vcs/` (`git merge-base --is-ancestor`, exit-code mapped, no mutation).
  - True → `CLOSED`.
  - False → `RESOLVED_EXTERNALLY`.
- **Recorded head.** The child's integration head is `ExecutionRecord.integration_head`, from the probe at `awaiting_merge` (R2), not from `VerifyResult`, which carries the verify-branch head. The advisor's alternative, keying closure on the PR's merge commit, was rejected: the PR may be squash-merged, which breaks ancestry.
- **Squash merges.** Under a squash or rebase merge the child head is not an ancestor, so the incident is `resolved_externally`. The fix is still retained, as an experience, not a lesson. This is conservative and recorded: a lesson is claimed only when provenance is provable. The tasks add a test for it.
- **It is a state check, not a transition.** It runs on every collected Detect while the incident is `VERIFIED`, so a cycle lost to not-collected cannot strand it (advisor D6.1).
- **Identity present while `VERIFIED`.**
  - `is_ancestor` true: the fix is on the default branch and did not hold, so the verdict is dirty.
  - `is_ancestor` false: the PR is unmerged, or it was squash-merged and regressed. The incident stays `verified` and renders the hint "fix not on default branch" in `sdlc maintain incidents`. Since it is live, it blocks a duplicate incident. The operator resolves it by merging, rejecting the child, or disabling. This is a recorded residual, tied to the out-of-scope stale-PR handling (plan review, gap 6a). In `step()`, the `RESOLVED → RESOLVED_EXTERNALLY` branch (`incidents.py:216`) gains a guard that skips `VERIFIED`, `EXECUTING` and `VERIFYING` (advisor D6.2).

## R9 — Keeping the incident current; consecutive reproduction

- **Decision.** On `PERSISTED`, `step()` sets `inc.finding = cur_finding` and `inc.commit_sha = cur.commit_sha` (skeptic L5).
  - A new field, `consecutive_seen`, increments on collected `PERSISTED`, resets to 1 on `NEW`, and resets to 0 on a not-collected cycle for that signal.
  - The 023a floor input `reproduced` keeps using `seen_count >= 2`, so the 023a gate behaviour is unchanged. Only the Execute guard (R6) uses `consecutive_seen`.
- **Execute-only.** The refresh and the `consecutive_seen` tracking run only when `cfg.execute` is true. An execute-off loop's state is then byte-identical to 023a, not merely command-identical (plan review, gap 5). With execute off, nothing consumes either.
- **Rationale.** Changing `reproduced` would alter 023a's gate outcomes for existing loops. Settled decisions are not reopened, and the stricter fact is used where execution happens.
- **Replay.** These are pure-state changes inside an activity-free function, with no new commands, so 023a histories replay identically.

## R10 — Caps

- **Decision.** `MaintenanceConfig` gains:
  - `execute: bool = False`
  - `max_starts_per_cycle: int = 1` (range 1–3)
  - `max_starts_per_window: int = 3` (range 1–10)
  - `max_reopens: int = 2` (range 0–2; the code ceiling is 2, per GATE 1 Q3)
  - `child_timeout_hours: int = 24` (range 1–168)
- **The window.** `MaintenanceState.exec_starts: list[datetime]` is stamped with `workflow.now()` and pruned to 7 days at each Execute. It rides `continue_as_new` (advisor D5).
- **Gate order at Execute.** Incidents are walked in incident-number order:
  1. the path-overlap check (no two `EXECUTING`/`VERIFYING` incidents on one path);
  2. the per-cycle cap;
  3. the window cap;
  4. `may_execute`.
  A cap or overlap leads to `QUEUED`, and the operator is notified once per cycle, not once per incident.
- **Re-enable resets the window.** Accepted and documented in the CLI help (advisor D5). The operator is trusted.

## R11 — Reopen transitions and the floor

- **Decision.** A pure `apply_verdict(incident, verdict, cfg) -> Incident` in `S/maintenance/execution.py`.
  - Dirty with `reopens < max_reopens`: `reopens += 1`, clear the plan, go to `REOPENED`. The next cycle re-plans through 023a's proposer path.
  - Dirty with `reopens == max_reopens`: go to `ESCALATED` and notify.
  - Non-retryable configuration failure: escalate immediately. A child that fails with an `ApplicationError` marked non-retryable, or a `GraphStartError`, is classified by the `ChildProbe` result.
- **The floor gets real counts.** `workflows/maintenance.py:199,252` pass `reopens=inc.reopens` instead of `0`. A reopened mechanical plan floors at 0.75, below 0.8, so it is human-gated. That is intended and pinned by a test.
- **Replay.** For 023a loops, `reopens` is always 0, so the floor is unchanged.

## R12 — Judgement and multi-action seeded work (B-FR-003)

- **Decision.** A pure `repair_work_for(identity, finding, signal_version, actions) -> SeededWork` in `S/tidyup/backlog.py`, beside `seeded_work_for` (advisor D2).
  - It produces one task whose description lists every `code_fix` action in order.
  - The acceptance criterion names signal, rule and version, as `seeded_work_for` does.
  - It omits the "Change nothing else" sentence (`backlog.py:78-81`).
- **Which builder runs.** Mechanical single-action plans keep `seeded_work_for`. Everything else uses `repair_work_for`.
- **Rationale.** Maintenance may not import stage models (`maintenance/AGENTS.md`), and `backlog.py` already imports them. No stage is involved.

## R13 — Memory retention (B-FR-012/013)

- **Decision.** `MemoryKind` gains `INCIDENT_LESSON` and `INCIDENT_EXPERIENCE` (`S/memory/models.py:20`).
  - Retention fires once, on entry to a terminal state, through the existing `retain` activity with `MEM_ACT` (120 s, 5 attempts), wrapped in the `memory_host._retain` swallow pattern (`workflows/memory_host.py:83-100`). It is bounded, never raises, and never fails the cycle. This is exactly how the shipped FR-403 behaves.
  - Text is rendered by a pure `render_retention(incident)` in `S/maintenance/render.py`: symptom, cause, fix, outcome, attempts, and the source child id.
  - The scrub hook runs inside the `retain` activity, as for every retain.
- **Which memory settings.** The loop reads them from `_default_fix_cfg().memory`. These are the same memory settings the repair children run with, so there is no new configuration surface and the bank is `project_bank`.
- **Idempotence.** A `retained: bool` flag on the incident is set in the same step. `_document_id` hashes the text (`hindsight_client.py:88`), so a retry of the same retention is also deduplicated by the backend.
- **The `kind` tag.** It is already filterable (`hindsight_client.py:99`), so `TAG_PROMOTED_KEYS` is not changed (skeptic L3).

## R14 — Enabling execution, and preconditions (B-FR-018, B-FR-025)

- **Decision.** `sdlc maintain enable ... --execute`. The flag is valid only with `--ack-unattended-build-probe`. Children run the repo's build and tests, so `--no-build-probe` with `--execute` is refused: the probe is the precondition for a mechanical build verdict.
- **Preconditions.** At enable time, client-side, before the workflow starts: `gh` on PATH, `git remote get-url origin` succeeds, and `git rev-parse --verify <default_branch>` succeeds. Each refusal names what is missing. The checks mirror the merge activity's checks (`stages/merge/activities.py:210-225`).
- **An enabled loop cannot gain `--execute` live.** Disable and re-enable instead, matching 023a's re-configuration path (FR-018).

## R15 — Determinism for running 023a loops

- **Decision.** Every new command path (child start, probe activity, verification, external signal and cancel, ancestry, retention) runs only when `cfg.execute` is true, **and** behind `workflow.patched("maint-023b-execute")`. Existing loops (`execute` false) issue the same commands as before.
- **Replay coverage.**
  - The new paths get in-test `Replayer` replay (023a R13 pattern).
  - The R7 state fixture plus the existing 023a temporal tests are the regression gate.
  - No stored replay golden changes (B-FR-021).

## R16 — File-size budget

| File | Lines now | Delta | Result |
|---|---|---|---|
| `S/workflows/maintenance.py` | 390 | + ~120 (Execute/Report orchestration only) | ~510 |
| `S/workflows/maintenance_execute.py` (NEW) | — | per-incident execute/report/close steps, as async functions over explicit state, with no handlers (`S/workflows/AGENTS.md` rule: handlers only on the concrete class) | ~250 |
| `S/maintenance/execution.py` (NEW, pure) | — | `may_execute`, `apply_verdict`, `choose_starts`, `closure_outcome` | ~200 |
| `S/maintenance/models.py` | 277 | +~90 | ~370 |
| `S/maintenance/incidents.py` | 273 | +~40 | ~315 |

All are well under the 1000-line ceiling.
