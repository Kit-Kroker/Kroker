# Advisor consult — round 023b (2026-11-15)

Seat: `advisor` (claude). Brief: D1–D6 open design decisions. Verbatim reply:

**Design advice for 023b: D1–D6**

Nothing was edited. Line numbers are from this tree. The spec's `tidyup.py:140-200` is `workflows/tidyup.py`. The verification activity itself is at `vcs/integration.py:123`.

**D1. Child id and re-attach: an id alone is not enough.**
- **Blocking helper.** `execute_pipeline_child` (`pipeline_child.py:31-51`) awaits the child's final result with `execute_child_workflow(..., id=child_id)`. That contradicts B-FR-005, so Execute needs a non-blocking variant built on `start_child_workflow`.
- **Missing options.** The helper exposes neither `id_reuse_policy` nor `parent_close_policy`. Both exist in the installed SDK (`workflow/_workflow_ops.py:161,165`).
- **Duplicate starts.** Temporal rejects a second start only while the id is running. After completion the default policy allows a rerun under the same id. Set `REJECT_DUPLICATE` and treat `WorkflowAlreadyStarted` as "already attached", not as a failure.
- **Parent close.** The default policy is terminate. Set `ABANDON` explicitly, as `deployment.py:9` does. I could not confirm whether `continue_as_new` applies the policy, so verify that in a test.
- **Replay vs roll-over.** Within one run, replay restores the child handle, so a worker restart is safe. After `continue_as_new` there is no handle. Workflow code can only get a signal-only external handle, so child status needs an activity that calls `client.get_workflow_handle(id).describe()` or `.result()`. The repo already does this client-side (`cli.py:733`, `dashboard/fleet.py:101`).
- **Id collision on re-enable.** `maintain enable` starts `maint-<project>` with fresh state (`maintenance/cli.py:5,93-96`), so `next_incident_no` restarts at 1. Disable deliberately leaves children running. A re-enabled `inc1-a1` would collide with a running abandoned child, or rerun a finished one. Recommended id: `maint-{project}-{first_execution_run_id[:8]}-inc{no}-a{attempt}`. `first_execution_run_id` is stable across `continue_as_new` and new per enable.
- **Attempt counter.** Increment `attempt` and record the id in state in the same workflow step as the start.

**D2. Judgement builder.**
- Put a new pure `judgement_work_for(identity, finding, signal_version)` in `tidyup/backlog.py`, beside `seeded_work_for` (line 63). It returns `SeededWork` and uses the same acceptance-criterion shape, without the "Change nothing else" sentence (lines 78-81).
- Call it from `workflows/maintenance.py`, which already composes children.
- Do not put it in `maintenance/`. Its AGENTS.md allows triage types only, and `tidyup/backlog.py` imports stage models.
- Do not put it in a stage slice. Cross-stage calls are banned (`AGENTS.md:110`), and this is not a stage concern.

**D3. Verification path: reusable as-is for one branch.**
- `VerifyBranchInput.branches` is a list (`integration.py:~100`), so a single-element list works.
- `tidyup_id` only keys the ref `sdlc/tidyup-verify/{id}` and the worktree directory. Pass a per-attempt key, such as the child id.
- Three gaps remain:
  - **Merge failures.** A non-conflict merge failure raises `RuntimeError` after 3 retries. Wrap the call so Report records "conflicted", not a crashed cycle.
  - **Base commit.** The spec says verification uses the pinned commit, but the child branches from the head it resolves itself at start. Pinning to `incident.commit_sha` will mostly yield conflicts. Record the child's start sha in the execution record and use that as `base_sha`.
  - **Branch name.** Tidyup hardcodes `sdlc/{wf_id}/integration` (`tidyup.py:216`). Take the branch from the child's result, not from a naming convention.
- The re-detect triage child needs its own id, distinct from the cycle's `maint-…-c{cycle}-triage` (`maintenance.py:171`). Run it with `gating=False`, as `tidyup.py:335` does.

**D4. Reopen state machine.**
- **Fields.** Add `attempt`, `reopens` and an execution record to `Incident`. Keep them separate from `plan_attempts`, which counts analysis failures (`maintenance.py:223`).
- **Transitions:**
  1. `APPROVED` → `EXECUTING`: decider check passes, caps pass, `attempt += 1`.
  2. `APPROVED` → `AWAITING_DECISION`: the decider check refuses.
  3. `APPROVED` → deferred: a cap is hit.
  4. `EXECUTING` → `VERIFYING`: the child reached a branch.
  5. `EXECUTING` → dirty: the child failed or produced an empty diff.
  6. `VERIFYING` → `VERIFIED`: collected and `RESOLVED`.
  7. `VERIFYING` → `VERIFYING`: not collected. It stays put (B-FR-007).
  8. `VERIFYING` → dirty: `PERSISTED`, or the merge conflicted.
  9. `VERIFIED` → `CLOSED` (see below).
  10. `VERIFIED` → dirty: the identity reappears.
- **Dirty rule.** If `reopens < 2`, set `reopens += 1`, clear the plan, go to `REOPENED`, and re-plan. Otherwise go to `ESCALATED`. B-FR-009 should say this explicitly. Escalating at count == 2 gives only 2 attempts. Escalating on the dirty verdict after the second reopen gives the 3 attempts that Q3 intends.
- **Double-count risks:**
  - **Per-cycle detect.** Only a verdict, never a per-cycle detect, may increment. The PERSISTED branch (`incidents.py:~206`) fires every cycle, so a reappearing identity must move state on first sight.
  - **Wrong state.** An `EXECUTING` or `REOPENED` incident must not be re-reopened by PERSISTED.
  - **Floor penalty.** `reopens=0` is hardcoded in `maintenance.py:199,252`, with a comment claiming it is "priced in already". Wire the real count. Then `0.95 − 0.2 = 0.75` is below 0.8, so every retry is human-gated. State that this is intended.
- **Counter location.** The counter lives on `Incident` in `MaintenanceState`, which `continue_as_new` carries whole (`maintenance.py:136`).

**D5. Caps.**
- **Window.** Add `exec_starts: list[datetime]` to `MaintenanceState`. Stamp each start with `workflow.now()`, not wall-clock time, and prune entries older than 7 days. It rides along with `continue_as_new` for free. The per-cycle counter can stay in memory.
- **Reset on re-enable.** Disable then re-enable starts fresh state, so the window resets and the cap can be bypassed. Either accept and document that, or have `enable` refuse within the window.
- **Wording.** B-FR-011 says "spend" but Q2 counts starts. Reword it.

**D6. Problems that would fail planning.**
1. **Closure is unreachable by delta alone.** `step()` yields `RESOLVED` only on a collected prev→cur transition. If the cycle where the identity vanishes is uncollected, the transition is lost and the incident sticks in `VERIFIED`. Closure must be a state check: collected default-branch detect, identity absent.
2. **`RESOLVED_EXTERNALLY` pre-empts `closed`.** `incidents.py:~229` sends any `RESOLVED` incident there. Split it: `VERIFIED` → `CLOSED`, everything else stays `RESOLVED_EXTERNALLY`.
3. **DEFERRED is overloaded.** `step()` flips `DEFERRED` to `OPEN` on NEW or PERSISTED (`incidents.py:171,206`). An approved-but-capped incident would be re-planned and get a second gate. Use a distinct state, or keep the approval and exempt it.
4. **`APPROVED_NOT_EXECUTED` is terminal** (`models.py:63`), and the R7 validator (`models.py:248-263`) keys on that set. Making it non-terminal changes how old persisted states validate. Plan a migration rule.
5. **How Report learns a child finished is unspecified.** A child parked at the merge gate has no final outcome string, and tidyup's `reached_a_pr` depends on that string. Define which child signal means "branch ready". Also add a child execution timeout, or a stuck child holds `EXECUTING` forever.
6. **The decider check is mostly redundant.** The gate auto-approves purely on `effective > threshold` (`maintenance.py:309`). Judgement caps at 0.6 and structural at 0, so policy cannot clear them. Still add the explicit guard in Execute (B-FR-002), since the floor table could change.

