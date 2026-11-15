# Skeptic consult — round 023b (2026-11-15)

Seat: `skeptic` (agy). Brief: L1–L6 pressure-test of locked decisions. Verbatim reply (terminal capture):

```text
  ### L1. Q4 / B-FR-016: Children write the repo & open PRs; verification branch on pinned commit
  • Counter-scenario 1 (Pinned-commit vs. Moving-HEAD attribution skew):
      • Inputs/State: Cycle 2 detects INC-1 at pinned commit C0. While INC-1 waits at its gate or
      cap, main advances to C5 (where commit C2 fixed the finding, or C3 introduced a file move).
      Execute starts the child with base_branch="main", so setup_integration_branch
      (src/sdlc/vcs/integration.py:37-51) cuts sdlc/<child_id>/integration from C5, not C0 (Edge
      Case 3, .specify/specs/023b-daper-acts-verifies/spec.md:144). Report then runs
      build_verification_branch(base_sha=C0, branches=[child_branch]) (B-FR-006,
      src/sdlc/vcs/integration.py:162-172).
      • Wrong outcome: Because C0 is an ancestor of C5, git merge --no-ff child_branch into C0
      merges all upstream commits C1..C5 plus the child's diff. compute_delta(triage(C0),
      triage(verify)) attributes C2's external fix to a no-op child run, marking INC-1 verified and
      retaining a false lesson.
  • Counter-scenario 2 (PR opened before verification + child merge-gate ordering paradox):
      • Inputs/State: GraphWorkflow (src/sdlc/workflows/graphs/seeded.graph.yaml:8-22) parks at its
      merge gate (GatePolicy.HARD, TimeoutAction.HOLD, src/sdlc/core/models.py:374) before calling
      open_pull_request (src/sdlc/stages/merge/activities.py:189) and returning merged-not-
      deployed:<pr_url> (src/sdlc/workflows/tidyup.py:137).
      • Wrong outcome:
          1. If Report waits for child completion (reached_a_pr), then (a) open_pull_request pushes
          to origin and opens a PR before Report ever runs build_verification_branch—so a broken
          repair opens a bad PR on GitHub before reopening and spawning a 2nd PR; and (b) no child
          can ever reach verified while parked at its merge gate (contradicting US1 AC4 + 023a
          preview line 206).
          2. If Report verifies sdlc/<child_id>/integration before child completion without checking
          child stage state, it races with merge_into_integration during code.

  • Trust layer check: Inside the child, independent judges (zai:glm-5.3-flash vs. dev glm-5.3) and
  deterministic evaluate_quality_gate hold. The breach is at the seam between child merge and parent
  Report.
  • Covered by spec? No.
  • Minimal spec change: In B-FR-006 / Edge Case 3, require the child's base commit (child_base_sha,
  recorded at child start) to be the base_sha for build_verification_branch (comparing
  triage(child_base_sha) or prev against triage(verify)), AND specify whether Report verifies the
  child's integration branch once the child reaches awaiting:merge (before open_pull_request) or
  after child completion. Also require cleanup of sdlc/tidyup-verify/<id> worktrees
  (src/sdlc/vcs/worktree.py:253).
  ──────
  ### L2. Q2 / B-FR-011: Cap = 3 child starts per 7-day window vs. infra failures
  • Counter-scenario:
      • Inputs/State: Project has a missing origin remote or missing gh binary
      (src/sdlc/stages/merge/activities.py:210-225), or transient venv setup failure. INC-1 is
      approved. Over 3 cycles, INC-1 starts attempt 1, reopens (Q3 bound = 2 reopens / 3 attempts),
      starts attempt 2, reopens, starts attempt 3, and escalates.
      • Wrong outcome: One incident's 3 infra-failed attempts consume 100% of the 7-day project cap
      (3/3 starts), starving all legitimate fixes for 7 days.
  • Should "failed for infra" count as a start? Yes—it MUST count. In GraphWorkflow, an "infra
  failure" in merge (open_pull_request failing on gh/network) happens after code and qa have already
  burned full coding-harness and judge tokens. Exempting failed children creates an unbounded token-
  spend loophole (the exact hazard H3 identified).
  • Covered by spec? No. Edge Case 1 (.specify/specs/023b-daper-acts-verifies/spec.md:142) routes
  all child failures through the reopen bound (3 attempts = full 7-day cap).
  • Minimal spec change: Keep every child start counting toward B-FR-011, but amend Edge Case 1 / B-
  FR-009: if a child fails with a non-retryable configuration/infra ApplicationError (e.g., missing
  gh, no origin, GraphStartError), transition directly to escalated on attempt 1 without reopening
  (burning 1 start, not 3).
  ──────
  ### L3. Q5 / B-FR-012: verified and closed retained as lessons
  • Counter-scenario:
      • Inputs/State: INC-1 reaches verified in cycle 3. Per Q5 / B-FR-012, the loop retains a
      memory record labelled as a lesson. In cycle 4, either (a) the fix is merged and the finding
      reappears on main (US4 AC3: verified -> reopened -> escalated), or (b) the fix merges and
      closes (verified -> closed).
      • Wrong outcome:
          1. verified is NOT a terminal state (US2, US4 AC1/AC3). Retaining at verified AND at a
          terminal state (closed or escalated) writes two memory records for one incident (violating
          B-FR-012 "as one record" and B-FR-014 "MUST NOT write a second... retention record").
          2. In src/sdlc/memory/hindsight_client.py:88-90, _document_id hashes f"{bank}|{kind}|
          {text}". A later escalated record has different text, so it does not overwrite the
          verified lesson in Hindsight—the poisoned lesson stays recallable forever.
          3. ARCHITECTURE.md:527-540's "reflect drops lessons from tasks that later failed" is under
          Target (plan, not built); HindsightMemory.reflect()
          (src/sdlc/memory/hindsight_client.py:243-255) only triggers /consolidate and never prunes
          invalidated lessons. Furthermore, TAG_PROMOTED_KEYS = ("stage", "gate")
          (src/sdlc/memory/hindsight_client.py:79) rejects any recall filter on outcome with a
          ValueError!

  • Covered by spec? No—Q5 / B-FR-012 directly contradicts US2/US4 by calling verified a terminal
  outcome.
  • Minimal spec change: In B-FR-012 / Q5: (1) Retain only when an incident enters
  TERMINAL_INCIDENT_STATES, where closed is the sole state retained as a lesson (verified is non-
  terminal and does not trigger retention); (2) distinguish lessons vs. experiences via MemoryKind
  (or promote "outcome" in TAG_PROMOTED_KEYS) so recall can filter them without crashing
  _filter_tags.
  ──────
  ### L4. Q6 / B-FR-002 / B-FR-017: Mixed plans execute code_fix and skip ops
  • Counter-scenario:
      • Inputs/State: A reproduced MECHANICAL finding gets a 2-action proposal from t_maintainer:
      Action 1 is ops: rollback, Action 2 is a code_fix written assuming the rollback occurred (e.g.,
      removing a migration compatibility shim). In src/sdlc/maintenance/confidence.py:48-60,
      confidence_floor does not inspect action.kind: for MECHANICAL (0.95), reproduced=True (-0.0),
      n_actions=2 (-0.05), floor = 0.90 > 0.80.
      • Wrong outcome: _repair_gate (src/sdlc/workflows/maintenance.py:309-313) auto-approves the
      mixed plan with decided_by="policy". Execute silently drops the rollback and runs the
      compensating code_fix unattended, with zero human review of the half-plan.
  • Covered by spec? No. RepairAction (src/sdlc/maintenance/models.py:161-171) has no fix_class—only
  TriageFinding does.
  • Minimal spec change: In B-FR-002 and Q6, specify that decided_by == "policy" is accepted only
  when finding.fix_class == FixClass.MECHANICAL AND all(a.kind == "code_fix" for a in plan.actions).
  Any mixed plan containing an ops action requires decided_by == "human".
  ──────
  ### L5. B-FR-002 / B-FR-020: Can a mechanical plan reach policy approval with a stale or
  unreproduced finding?
  • Confirmation & Floor Math (src/sdlc/maintenance/confidence.py:25-60):
      • At default threshold = 0.8 with strict > (maintenance.py:206,311): an unreproduced
      (seen_count == 1) mechanical 1-action plan gets floor = 0.95 - 0.15 = 0.80. Because 0.80 > 0.
      80 is False, it stays human-gated at the default threshold.
      • HOWEVER, two code paths STILL let an unreproduced or stale mechanical plan reach
      decided_by="policy":
          1. Lowered cfg.threshold (ge=0.5, src/sdlc/maintenance/models.py:93): If a project sets
          threshold = 0.75, an unreproduced (seen_count == 1) mechanical plan (floor = 0.80 > 0.75)
          or a reopened (reopens = 1, seen_count = 2, floor = 0.95 - 0.20 = 0.75 > 0.70) mechanical
          plan gets decided_by="policy". Even worse, at threshold = 0.55, a reproduced JUDGEMENT
          plan (floor = 0.60 > 0.55) gets decided_by="policy" in _repair_gate!
          2. Non-consecutive seen_count >= 2 and stale commit_sha
          (src/sdlc/maintenance/incidents.py:201-209): reproduced checks inc.seen_count >= 2
          (src/sdlc/workflows/maintenance.py:197), which is true even across non-consecutive cycles
          separated by UNVERIFIABLE (not-collected) cycles. Worse, on FindingState.PERSISTED,
          incidents.py:201-209 increments seen_count and last_seen_cycle but never updates inc.
          commit_sha or inc.finding—so _reprice() approves the plan at cycle k while inc.commit_sha
          is still pinned to cycle 2's stale commit!

  • Covered by spec? No.
  • Minimal spec change: In B-FR-002 / B-FR-020, require Execute's decided_by == "policy" check to
  verify finding.fix_class == FixClass.MECHANICAL, inc.seen_count >= 2, inc.reopens == 0, and inc.
  plan.effective > max(cfg.threshold, 0.80), and update inc.commit_sha = cur.commit_sha on PERSISTED
  in incidents.step().
  ──────
  ### L6. Three additional spec/code contradictions that break 023b
  1. continue_as_new kills in-flight children (B-FR-005 vs. B-FR-015 vs.
  src/sdlc/workflows/pipeline_child.py:49):
      • execute_pipeline_child calls await workflow.execute_child_workflow(...) with Temporal's
      default ParentClosePolicy.TERMINATE. If MaintenanceWorkflow calls continue_as_new while a
      child is parked at merge, Temporal terminates the child. If it waits for the child before
      continue_as_new, a parked child blocks continue_as_new indefinitely (violating B-FR-005/FR-
      013). And after continue_as_new, Temporal's ExternalWorkflowHandle cannot .result() or .
      describe() from workflow code—re-attaching requires ParentClosePolicy.ABANDON plus an activity
      or child-completion signal.
      • Fix: Specify ParentClosePolicy.ABANDON on child start and an activity/signal mechanism to
      poll/receive child completion across continue_as_new.
  2. APPROVED_NOT_EXECUTED in TERMINAL_INCIDENT_STATES (src/sdlc/maintenance/models.py:63) causes
  duplicate incidents & races before Execute:
      • When a gate resolves between cycles, _record_repair_outcome sets APPROVED_NOT_EXECUTED. At
      the start of the next cycle, step() runs Detect before Execute and ignores all
      TERMINAL_INCIDENT_STATES (src/sdlc/maintenance/incidents.py:126). If the finding was fixed on
      main (RESOLVED), step() fails to mark it RESOLVED_EXTERNALLY and Execute launches a child for
      an already-fixed bug; if a signal recovers from not-collected (NEW), step() opens a duplicate
      incident.
      • Fix: Remove APPROVED_NOT_EXECUTED from TERMINAL_INCIDENT_STATES when execution is enabled
      (or introduce non-terminal APPROVED distinct from APPROVED_NOT_EXECUTED).
  3. Multi-action code_fix plans collide on child ID (incident, attempt) (B-FR-001 vs. US1 AC1):
      • RepairPlan.actions allows up to 5 actions (src/sdlc/maintenance/models.py:181). B-FR-001
      says "run code_fix actions only, each as a seeded brownfield factory child run... derived from
      (incident, attempt)", while US1 AC1 says "starts exactly one child run". Multiple code_fix
      actions in one plan collide on (incident, attempt).
      • Fix: Clarify in B-FR-001 that one (incident, attempt) starts one child run whose SeededWork
      compiles all code_fix actions of the plan (or cap code_fix actions to 1 per plan).


```
