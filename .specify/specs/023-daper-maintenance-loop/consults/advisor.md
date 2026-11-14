# Advisor consult — round 023 (DAPER maintenance loop)

Read: spec Part B + open decisions, ARCHITECTURE §7, PRD FR-501..503, ADR-7, E-14, `workflows/AGENTS.md`, and the reuse candidates. Paths are relative to `src/sdlc/` unless noted. All cites checked against the tree today.

## Headline

Reuse is larger than the spec assumes: **Detect, re-detect and the verify-branch machinery already exist** in Triage and TidyUp. The spec is wrong on **five points** (§7). I recommend **splitting into 023a and 023b** (§5).

---

## 1. Loop shape → long-lived per-project `MaintenanceWorkflow`, with the schedule asset as a kicker

**Recommendation: one long-lived workflow per project (`id = maint-<project>`).** A Temporal Schedule (the E-14 asset) is the timer. It does not run the cycle itself. The CLI nudge and the schedule both signal-with-start the one workflow.

Why not per-cycle-from-schedule:
- **Incidents must outlive a cycle.** An incident whose repair PR is open, waiting on the operator, spans many cycles (see §4). A per-cycle workflow needs a new incident store. The repo has none, and ADR-8 says Temporal is the single source of truth. That store is the cost that pushes the round toward XL.
- **Gates target a workflow id.** `deployment.py:5-7` records that "operators know their run's id, not a child's". A repair-plan gate needs one stable owner id for the inbox and CLI.
- **The per-cycle shape gives no extra freedom.** A cycle parked on a 48h gate blocks the next cycle either way.

How FR-004 is met (about 10 lines, no Temporal overlap tricks):
- `self._nudged: bool`, set by the `nudge` signal.
- The idle loop is `await workflow.wait_condition(lambda: self._nudged, timeout=cadence)`.
- Clear the flag at cycle start. Signals during a cycle set it again, so you get **exactly one** follow-up cycle. One workflow means one cycle at a time by construction.
- `GateHost` signals and queries come free (`gates.py:107-131`). The queries (`pending_decisions`) cover FR-017's inbox side. Add an `incidents` query.

How the schedule asset (FR-002) works:
- `ReflectWorkflow` exists "only because Temporal Schedules start workflows, never activities" (`reflect.py:1-8`). A thin `MaintenanceKickWorkflow` follows the same precedent.
- The kicker runs one activity that does client `start_workflow(..., id_conflict_policy=USE_EXISTING, start_signal="nudge")`.
- **Open point:** activities have no client today. The only client user is the janitor, created in `worker.py:275`. Plan must pick closure-binding the client into the one activity, or an `ABANDON` child. Either is S-cost.
- The CLI nudge uses the same client call directly (stateless shell, ADR-8).
- If the client injection turns out ugly, the fallback is an in-workflow cron timer with the yaml as pure input. That loses the dry-run diff, so prefer the kicker.

How FR-015 is met:
- `continue_as_new` **only at the idle boundary**: no pending gate, no outstanding child. Carry `incidents` + `baseline` in the input model.
- Use `workflow.info().is_continue_as_new_suggested()`.
- **First use of `continue_as_new` in `src/`.** `grep continue_as_new` returns nothing. Plan needs a replay test and a state-carry round-trip test.
- While a child is outstanding, continue-as-new is deferred. That is bounded by the repair cap (FR-013).

Execute must **not** `execute_child_workflow` inline. The repair child's `merge` gate defaults to HOLD (`core/models.py:374`) and TidyUp only turns `deploy` OFF (`tidyup.py:51-62`). A child can therefore park indefinitely on a human decision. Instead:
- `start_child_workflow` with a deterministic id, shaped like `fix_workflow_id` (`tidyup.py:121-124`): `maint-{project}-inc-{n}-fix-{attempt}`.
- Record the id on the incident.
- Await the handle in a tracked coroutine.
- The deterministic id, plus recording it before the await, satisfies FR-016/SC-005 "no repair child starts twice".

## 2. Confidence → code-computed floor; the proposer can only lower it

**Recommendation: yes.** Add a pure function `confidence_floor(incident, plan) -> float` in a pure `maintenance/` module, like `triage/` (`triage/models.py` header documents the purity rule). Final confidence is `min(floor, proposer_self_rating)`.

Floor inputs, all already deterministic:
- **Finding `fix_class`** (`triage/models.py:19-26`). `MECHANICAL` is the only class that gets a high ceiling. `JUDGEMENT` is capped around 0.6. `STRUCTURAL` is 0, so it is always gated.
- **Reproduced on a second detect** (flake guard).
- **Severity.**
- **Reopen count.** Each reopen lowers it.
- **Action count.**

Gate mechanics already exist. This is the SOFT path in `GateHost._gate`, `gates.py:210-211`:
- Call `_gate("repair_plan", settings, auto_decision=<approve, decided_by="policy"> if conf >= threshold else None, confidence=conf, author_model=...)`.
- `confidence` and `author_model` already flow to `_on_gate_decided`, which is how SC-6 calibration reads them. Maintenance can feed the same calibration later at no cost.

Be honest in the spec about the consequence. Advisory findings are `FixClass.JUDGEMENT` (`triage/signals/dependencies.py:372`). So at default threshold 0.8 **only mechanical, reproduced findings auto-execute**, and every dependency-advisory repair is human-gated. That is the correct conservative default for round 1. US1's fixture path must set the threshold explicitly, or seed a mechanical finding.

Recording `decided_by` is also the hook for §7 item 3.

## 3. Incident identity → reuse `finding_identity`, exactly

**Recommendation: reuse it.** `finding_identity(f) = f"{signal}:{rule}:{path}:{key}"` (`triage/models.py:194-201`). It was built for before/after matching across commits and is deliberately **not** derived from `line`, so a fix shifting lines does not fake a resolved+new pair. A second identity over (signal kind, scope) would diverge from the one `compute_delta` matches on.

Per signal:
- **Advisories:** `key = package:advisory_id` (`dependencies.py:376`). Good.
- **Secrets:** `key = evidence_key(...)`, a hash of the match.
- **Build probe:** no `key`, and `path=""`. So `build_probe:build_failed::` is **one incident per rule**. A build that is broken for two different reasons stays one incident. That is acceptable, but say so in the spec.

Two additions:
- **Not-collected signals** have no finding. Use a synthetic identity `<signal>:not_collected::`, kept apart from finding incidents. This matches the spec's edge case (repeated not-collected escalates, a single one opens nothing).
- **Deploy liveness** is not a triage signal. If it stays in scope, emit identity strings in the same four-part shape so one dedupe code path serves everything.

Use `SignalResult._identities_unique` (`triage/models.py:~85`) as the model. The registry must reject duplicate open-incident identities.

## 4. Re-detect scope → two-step, but the second step is just the next cycle's Detect

**Recommendation: do not build a wait for the merge.** TidyUp already solves the first half:
1. After a repair child reaches a PR (`reached_a_pr`, `tidyup.py:127-132`), call `build_verification_branch(base_sha=pinned_commit, branches=[child branch])` (`tidyup.py:330-339`). Re-triage that head with `_triage(..., gating=False)` and `triage_gates` (`tidyup.py:150-162`, `:345`).
2. Compute `compute_delta(before, after)` (`triage/delta.py`). The incident's identity `RESOLVED` means **`verified`**: clean on the repair branch, PR still awaiting a human.
3. The incident stays `verified` (not `closed`) until a **later ordinary Detect on the default-branch head** no longer reports its identity. Then it becomes `closed`. If the PR merged and the fault is still there, it reopens (bounded).

Why this is better than waiting:
- No workflow ever blocks on the operator's merge.
- No new "re-detect on default" machinery exists. The normal cycle is the machinery.
- The edge case "same symptom while an incident is open attaches as a recurrence" falls out for free, because the identity matches the open incident.

Required in the spec:
- **FR-012 must use `compute_delta`, not a set difference.** `delta.py:3-17` explains why: absence on the after side is not resolution. `UNVERIFIABLE` (signal not collected, signal version changed, merge conflict) must never close an incident. This is exactly FR-915 and the spec's own "not-collected is never healthy" rule.
- **Add an `awaiting_merge` / `verified` state** to the incident state list in FR-017.
- **A stale-PR escalation** (PR unmerged after N days → notify). S-size, optional.

## 5. Sizing → split 023a / 023b

**Recommendation: split. One crew run will not hold this at L.**

The "narrow detectors" bound the *detectors*. The weight is elsewhere. Round 023 contains several firsts:
- First `continue_as_new` in the repo.
- First signal-with-start singleton workflow.
- A refactor of the Reflect-only schedules package (§7 item 4).
- A new proposer agent role: `agents/` yaml + registry wiring. `AssessmentWorkflow._judge` (`assessment.py:~648-690`, `t_risk`) is the precedent for a proposer inside a GateHost workflow, including fail-closed degradation.
- An incident state machine with six states.
- Replay fixtures (FR-018).
- The execute and verify path.

**023a — "plans, gated, never acts."**
- `MaintenanceWorkflow` skeleton, nudge coalescing, `continue_as_new`.
- Detect as a **child `TriageWorkflow`** (see below), baseline seeding.
- Incident registry with code-assigned identity.
- One `maintainer` proposer producing analysis and plan in a **single call**. Two calls (Analyze, Plan) double the model spend for no extra independence, because the signals are already deterministic findings with severities.
- Code confidence floor and the repair-plan gate. Timeout is reject.
- Schedule kicker plus the schedules-package generalization.
- CLI nudge and incident query.
- Terminal state of an approved plan: `approved — not executed`. This is a shippable "advisory mode".

**023b — "acts and verifies."**
- Execute: child repair runs.
- Verify-branch re-detect, closure by later cycle.
- Memory retain (FR-014).
- Deploy liveness and rollback, **if** they are kept at all (§7 item 2).
- Per-cycle repair and spend caps.

Pure-Detect reuse for 023a: **run `TriageWorkflow` as a child unchanged** (`workflows/triage.py:220`). Pass `GateSettings(default_gate_policy=OFF)` as `tidyup.triage_gates(..., gating=False)` does. The child already pins the commit via `triage_resolve_commit` (FR-005's pin), degrades per signal via `run_or_degrade` (`triage.py:160-169`), and returns `RepoTriage`, so there are no new detectors for build, advisory or secret. Its `build_probe` is the "build broken" signal.

---

## 6. Existing components the spec missed

| Reuse | Where | For |
|---|---|---|
| `compute_delta` (4 states, UNVERIFIABLE) | `triage/delta.py` | FR-012 closure; "new since baseline" in FR-005 |
| `build_verification_branch` + `_triage(gating=False)` + `triage_gates` | `tidyup.py:150-162, 330-345` | Re-detect on the repair branch (§4) |
| `fix_workflow_id`, `reached_a_pr`, `_default_fix_cfg` / `_fix_gates` | `tidyup.py:51-69, 121-132` | Deterministic child ids; PR detection; child config. Lift to a shared module rather than import across workflows |
| `seeded_work_for` | `tidyup/backlog.py:63` | Seeded child, with its deterministic frozen-contract criterion "re-running signal X no longer reports rule Y". **Caveat:** its text says "mechanical, change nothing else", so advisory (JUDGEMENT) repairs need different wording |
| `admits(..., require_human=)` pattern | `triage/admission.py` | The model for "a non-human approval does not count" |
| `run_or_degrade` | `workflows/fanout.py` | Detector degradation |
| `GateContext` / `gate_pending` | `gates.py` | Inbox rendering of plans |
| `AssessmentWorkflow._judge` degrade shape | `assessment.py:~648` | Proposer failure becomes "no plan", never a crash |
| `ReflectWorkflow` precedent | `reflect.py:1-8` | The kicker |

## 7. Where the spec is wrong against the code

1. **"Repair against the detected commit" (US1 AC2, edge case 4).** TidyUp seeds the child with `base_branch` only (`tidyup.py:230-236`). The child resolves the branch head when it starts. Only the *verification branch* is built on the pinned `base_sha` (`tidyup.py:332-335`). Either the spec weakens the claim, or the plan adds an explicit pin for the child. Prefer the former and say "the verify branch is on the pinned commit".
2. **FR-005 deploy liveness and FR-011 rollback assume a persistent project deploy plan. None exists.**
   - `DeployPlan` is authored per run by `devops_planner` (`stages/deploy/models.py:76-83`). `PipelineConfig.deploy` is per-run input (`core/models.py:342+`).
   - `smoke_check` and `deploy_rollback` need a `DeployPlan`, a `DeployConfig`, a `repo_path` and, for http, an `endpoint` (`stages/deploy/activities.py`).
   - The rollback target is not recorded anywhere. Worse, both adapters **ignore `to_version`** (`deploy/adapters.py:86-90` compose, `:116-117` script).
   - `_rollback` in `deployment.py:102` is a closure over `previous`, captured before apply. It is not reusable.
   - The code actually lives in `stages/deploy/`. `src/sdlc/deploy/activities.py` is a re-export (`adapters.py` is the real file there).
   - **Recommendation:** drop both from 023a. For 023b, require `MaintenanceConfig.deploy: {cfg, plan}` supplied by the operator, and make rollback human-only (as the spec already says). Otherwise move both to a later round.
3. **FR-008 / SC-003 "no configuration may change that" is not true of the gate as built.**
   - `GateConfig.on_timeout` can be `APPROVE` (`core/models.py:66`, `gates.py:233-237`).
   - `GatePolicy.OFF` returns an approval with `decided_by="policy"` (`gates.py:206-209`).
   - `GatePolicy.SOFT` auto-approves.
   - **Fix:** build the `repair_plan` gate's `GateConfig` in code; never read it from operator config. Reject `on_timeout=APPROVE` in the maintenance config validator. At the execute site, **assert `decision.decided_by == "human"`** for every human-required action, and `in {"human","policy"}` only for confidence-cleared code fixes. Add a test that sets `on_timeout=APPROVE` and `OFF` and proves no action runs. That is the real SC-003/SC-004 test.
4. **FR-002 "applied by the existing schedules mechanism" understates the change.** The package is Reflect-only:
   - `KNOWN_SCHEDULE_WORKFLOWS = {"ReflectWorkflow"}` (`schedules/models.py:15`).
   - `ScheduleAction.banks` is required, `min_length=1` (`models.py:21`).
   - `to_temporal` hardcodes `ReflectScheduleInput` (`apply.py:48-53`).
   - `from_temporal` validates `action.args[0]` as `ReflectScheduleInput` (`apply.py:73`), so it would raise on a maintenance schedule.
   - It needs a discriminated union on `workflow`. Budget it in 023a, with its own tests.
5. **FR-005 "new" findings.** Signals are absolute, not diffs. On a brownfield repo the first cycle would open an incident for every existing finding. Define a **baseline**: the first cycle records the finding-identity set and opens no incidents. Later cycles open incidents only for identities not in the baseline (`compute_delta`'s `NEW`). Also:
   - `advisory_source` defaults to `"none"` (`triage.py:76`, `tidyup.py:76`), so the dependency signal collects nothing unless `MaintenanceConfig` declares a source. The spec's "OSV source" needs a config field, and "none" must read as not-collected-by-config.
   - The build probe runs the repository's own code with network access (`triage.py:7-9`, NFR-9, "operator-run only"). An **unattended scheduled loop is a wider exposure than anything the repo has shipped**. The spec must record this as an accepted risk or an explicit operator opt-in at enablement. Also note `PROBE_ACT` allows 40 minutes per cycle, one attempt (`triage.py:70-72`), which constrains the default cadence.

Smaller: ARCHITECTURE §7 lists "CI, quarantined tasks, error budgets" as Detect inputs. The spec correctly drops them. Record that this is a deliberate narrowing of §7, not an oversight.

## Suggested spec edits, in order

1. Split into 023a/023b (§5) and move FR-011 and the deploy half of FR-005 out of 023a (§7.2).
2. FR-004/015: the long-lived design, the continue-as-new boundary rule, and "do not await children inline" (§1).
3. FR-006/007: one proposer call; the confidence function (§2).
4. FR-008/009: the `decided_by == "human"` assertion and the config-validator rule (§7.3).
5. FR-012/017: `compute_delta` closure; the `verified` state (§4).
6. FR-005: baseline semantics and `advisory_source` (§7.5).
7. FR-002: honest schedules-package scope (§7.4).
