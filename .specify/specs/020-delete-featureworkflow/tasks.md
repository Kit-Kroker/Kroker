# Tasks: Delete FeatureWorkflow After Grace-Retention (round 020)

**Status**: Reviewer-approved (tasks checklist, pass 2, 2026-11-08).
- **Pass 1**: fixes-needed with 3 doc gaps: two missing plan-id citations
  and stale task ids in the `temporal` rule.
- **Pass 2**: approve.
- **Record**: [checklists/tasks.md](checklists/tasks.md).
- **Commits**: T001 (the planning artifacts) is done by the orchestrator.

**Input**: `.specify/specs/020-delete-featureworkflow/`:
- spec.md (GATE 1 approved: Q1 = A, Q2 = A; corrections C1 to C5);
- plan.md (plan ids T010 to T092);
- research.md (R-1 to R-10);
- data-model.md (§1 to §5);
- contracts/fleet-legacy-row.md (§1 to §5);
- contracts/gate-runbook.md;
- quickstart.md (§1 to §4);
- test-inventory.md.

The ids below are sequential (T001 and up). Each task names the plan id it
implements as `(plan Txxx)`.

**Tests**: required for every code change. Each new behaviour gets its test
written first, and the test is seen failing for the expected reason before
the implementation. The exceptions are pure deletions, which are verified by
the suites already in place.

**Order is dependency order, not story priority.** The gates fix the
sequence:

```text
PR-1 (Phases 1-4)
  → gate run 1 (Phase 5, orchestrator)
  → PR-2 (Phases 6-9)
  → gate run 2 and deploy (Phase 10, orchestrator)
```

**Integration (user decision, 2026-11-08)**: fast-forward merges to `main`,
with **no pull requests**. "PR-1" and "PR-2" are stage names: each is a
branch that the orchestrator verifies and then fast-forwards `main` to.
The crew never pushes.

**Orchestrator-only tasks**: T001, T015, T016, T035 (the fast-forward),
T036 and T037. The executor:
- **stops and hands back** after T014 (PR-1), and resumes at T017 only once
  T016 has PASSED;
- **stops and hands back** after T034 (PR-2), before T035 and T036.

It never runs T036 or T037.

US1 (the gate) is P1, but its tasks sit at Phases 5 and 10, because that is
where the gate has to run.

**Conventions for every task**:
- `S/` = `src/sdlc/`, `T/` = `tests/`, `FE/` = `interfaces/dashboard/frontend/src/`,
  `F/` = `.specify/specs/020-delete-featureworkflow/`.
- **Worktrees**:
  - PR-1 runs in `../Kroker-020-1` on branch `020-delete-featureworkflow`,
    created from `main`;
  - PR-2 runs in `../Kroker-020-2` on branch `020-delete-featureworkflow-2`,
    created from `main` **after** `main` is fast-forwarded to PR-1.
  - **Exception**: `S/stages/*/*.md` clause edits (T029) are made in the
    primary checkout, per root `AGENTS.md`.
- **Commit recipe** (round 019 convention):
  1. Write the message to a file in the session scratchpad.
  2. `git add <path>` once per path.
  3. `git commit -F <file>`.

  No `--no-verify`. If a pre-commit hook rewrites files, re-add those paths
  and commit again.
- **The executor never runs any `temporal` CLI command.** The only tasks
  that do are T016 and T036, and both are orchestrator-only.
- **A STOP is binding**: on a STOP, leave the tree as it is and report to
  the orchestrator. The STOPs are:
  - a gate FAIL;
  - a non-empty `commands`, `close` or `trace` golden diff;
  - `test_feature_replay.py` turning red in PR-1.
- Fast tier: `pytest -q`. The 8 known fast-tier failures on `main` are
  excepted. Record them by name in T002 and compare against that list.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no unmet dependency).
- **[Story]**:
  - US1: fresh gate evidence;
  - US2: no grace-edit tax;
  - US3: legacy rows stay visible;
  - US4: goldens re-baselined;
  - US5: replay-safe restart.

---

## Phase 1: Setup

- [x] T001 **Orchestrator-only, done by the orchestrator (2026-11-08).**
  Not an executor task. Recorded for traceability: commit the planning
  artifacts on `main`'s working tree, before creating any worktree. Paths, one `git add` each:
  - `F/spec.md`, `F/plan.md`, `F/research.md`, `F/data-model.md`,
    `F/quickstart.md`, `F/test-inventory.md`, `F/tasks.md`;
  - `F/contracts/fleet-legacy-row.md`, `F/contracts/gate-runbook.md`;
  - `F/checklists/requirements.md`, `F/checklists/plan.md`,
    `F/checklists/tasks.md`;
  - `F/checklists/reviewer-brief-plan-1.md`,
    `F/checklists/reviewer-brief-tasks-1.md`;
  - `F/advisor-brief-1.md`, `F/advisor-answer-1.md`,
    `F/skeptic-brief-1.md`, `F/skeptic-answer-1.md`;
  - `.specify/feature.json`, `CLAUDE.md`.

  Subject: `docs(020): spec, plan and tasks for FeatureWorkflow deletion`.
- [x] T002 Create the worktree `../Kroker-020-1` on the new branch
  `020-delete-featureworkflow`, and run `uv sync --frozen --extra dev` in
  it. Run `pytest -q` and write the failing test ids to
  `F/verification.md` §Baseline as the known-failure list. Run
  `pytest -m temporal T/replay -q` and record that it is green, including
  `T/replay/test_feature_replay.py`.

## Phase 2: Foundational (PR-1; blocks every later phase)

- [x] T003 Finalise the test classification (plan T010, FR-012) in
  `F/test-inventory.md`:
  - give each of the 76 `.py` rows exactly one class: `delete`, `migrate`,
    `repoint`, `comment-only` or `keep`;
  - each `delete` names its GraphWorkflow counterpart test as
    `path::test_name`, or it becomes `migrate`;
  - each `migrate` says what replaces the FeatureWorkflow leg.

  Add a closing tally line, which must total 76. Commit this document only.
- [x] T004 [P] Move `replayer()` (plan T011) from
  `T/replay/test_feature_replay.py` into `T/replay/harness.py` as
  `replayer(*workflows: type)`, with an explicit default tuple unchanged
  from today. Re-point its four users to import from `tests.replay.harness`:
  - `T/replay/test_feature_replay.py`;
  - `T/replay/test_benchmark_replay.py`;
  - `T/replay/test_architect_research_usage_replay.py`;
  - `T/replay/test_research_retain_replay.py`.

  Verify with `pytest -m temporal T/replay -q`, which must stay green.
- [x] T005 [P] Re-point the six helper imports (plan T012) per
  `F/test-inventory.md` "Known special cases":
  - `T/plan/test_plan_validation_module.py:5` and
    `T/plan/test_plan_graph_validation.py:9` become
    `from sdlc.stages.plan.validation import validate_task_graph`, with
    the call sites renamed;
  - `T/test_untraced_criteria.py:7` imports from `sdlc.stages.analyze.models`;
  - `T/merge/test_merge_gate_wiring.py:91` imports from
    `sdlc.stages.merge.step`;
  - `T/test_stack_contract.py:4` imports `DEFAULT_LINT_CMD` from
    `sdlc.stages.merge.step`;
  - `T/clarify/test_clarify_stage_wiring.py:30` imports
    `_requirements_for_downstream` from `sdlc.stages.architecture.step`.

  Run those six files.
- [x] T006 [P] Pin the live graph gate path (plan T013, R-7, C2) in three
  files:
  - `T/calibration/test_gate_requires_calibration.py`: add tests that
    `S/workflows/graph_nodes/gate.py` passes `judge_error` and
    `author_model` into its `ctx.gate` calls (C7);
  - `T/test_soft_gate_auto_approval.py`: add tests that it passes
    `calibration=` (SG-4);
  - `T/calibration/test_calibration_plumbing.py`: add a test that
    `S/workflows/graph_nodes/precode.py` hands `resolved_model` to the
    pending gate.

  To prove each test is not vacuous, run it once against a scratch copy of
  the source with the asserted argument removed, see it fail, and record
  the output in `F/verification.md` §T006. Then run it green on the real
  source.
- [x] T007 [P] Pin the values that need FeatureWorkflow alive (plan T014,
  R-5):
  1. Write `T/durability/fixtures/priced_usage_pre_e74.json` holding the
     `price_usage` tuples extracted from the current
     `T/replay/histories/greenfield_happy.json`. The extraction script is
     run once and not committed; its command line goes in the commit body.
  2. Add `T/durability/test_priced_usage_parity.py::test_pinned_tuples_match_the_recorded_history`.
  3. Add a constant `MEMO_PARITY_KEYS` in `T/replay/test_graph_golden.py`,
     computed from today's FeatureWorkflow leg.
  4. Add an assertion that both live legs still equal it.

  Run `pytest -m temporal T/durability T/replay/test_graph_golden.py -q`.

**Checkpoint**: the foundation is in place and `test_feature_replay.py` is
still green.

## Phase 3: User Story 3, legacy rows stay visible (P1, PR-1)

**Goal**: closed FeatureWorkflow runs are listed without being queried
(Q1 = A).

**Independent test**: quickstart §1, SC-005.

- [x] T008 [US3] Write the fleet tests first in `T/test_dashboard_fleet.py`.
  The fake `list_workflows` yields rows with `workflow_type`, `status`,
  `start_time` and `close_time`, and a handle factory counts calls per id.
  The cases are:
  - (a) N closed FeatureWorkflow rows give N `closed_legacy` entries, zero
    handle calls for those ids, and `errors == []`;
  - (b) a mixed window of GraphWorkflow and FeatureWorkflow rows;
  - (c) both the ordered and unordered query paths
    (`_ORDER_BY_SUPPORTED` toggled);
  - (d) a row with no `workflow_type` is still queried for `run_summary`;
  - (e) a legacy id that is also open is dropped;
  - (f) `_CLOSED_QUERY` and `_CLOSED_QUERY_UNORDERED` contain
    `WorkflowType='FeatureWorkflow'`.

  Run them and confirm (a), (b), (c) and (e) fail.
- [x] T009 [US3] Implement `LegacyRun`, `ClosedRef`,
  `FleetSnapshot.closed_legacy` and the partition in `S/dashboard/fleet.py`
  (plan T015), per contract §1 and data-model §1 and §2. Add the comment
  "never removed: pre-cutover runs stay visible" at `_PIPELINE_TYPES`.
  T008 must go green. Also run `T/test_dashboard_fleet_marks.py`,
  `T/test_dashboard_fleet_summary.py` and `T/test_read_fixtures_fresh.py`.
  If the `/api/inbox` read fixture changes, regenerate it with
  `python scripts/dump_read_fixtures.py` and commit the regenerated file.
- [x] T010 [US3] Make `GET /runs/{run_id}` in `S/dashboard/api.py` search
  `closed_legacy` after `closed` (contract §2), test first in
  `T/test_dashboard_api.py`. Add the comment "legacy
  FeatureWorkflow rows are intentionally absent (020 contract §3)" in
  `S/dashboard/fleet_summary.py` (plan T016).
- [x] T011 [P] [US3] Frontend (plan T017, contract §4), tests first in
  `FE/api/http.test.ts`:
  - add the `LegacyRun` wire type and `Run.legacy: boolean` in
    `FE/api/types.ts`;
  - add `mapLegacy` and its merge into the closed list in `FE/api/http.ts`;
  - add one legacy row to `FE/api/mock/index.ts`;
  - in `FE/features/fleet/FleetTable.vue`, hide the mode badge and the
    cost cell when `run.legacy` is true.

  Run `cd interfaces/dashboard/frontend && npm test`.

## Phase 4: User Story 5 (PR-1 part), legacy-run errors; then hand back PR-1

**Goal**: a query on a legacy id fails cleanly (R-3, contract §5).

- [x] T012 [US5] (plan T018) Write the tests first for `LegacyRunError`, in
  `T/test_channel_transport.py`:
  - a fake handle whose `query` raises and whose `describe()` reports
    `workflow_type="FeatureWorkflow"` raises `LegacyRunError`;
  - a non-legacy query failure re-raises the original exception;
  - the happy path calls `describe()` zero times.
- [x] T013 [US5] (plan T018) Implement `LegacyRunError` and the describe-on-failure
  check in `fetch_pending` in `S/channels/transport.py`.
  - Map it to HTTP 410 in `S/dashboard/api.py` (`/answer`, `/decide`).
  - Map it to an stderr message and exit 1 in `S/cli.py` (the reply path
    and `cmd_status`). `cmd_status` reaches the check through the same
    helper.
  - Map it to a tool error in `S/operator/tools.py`.

  Add one test per surface:
  - `T/test_dashboard_api.py` (410);
  - new `T/test_cli_legacy_run.py` (no CLI reply test module exists today):
    `approve --id` and `status --id` against a fake client print the
    message and exit 1;
  - `T/test_operator_errors.py`.
- [x] T014 PR-1 verification (plan T019):
  - quickstart §1 in full;
  - `pytest -q`, compared against the T002 list;
  - `pytest -m temporal T/replay T/durability -q`, where
    `test_feature_replay.py` must be green (**STOP** if not);
  - `ruff check . && ruff format --check . && mypy`.

  Record the results in `F/verification.md` §PR-1.
  **Executor STOP: hand back to the orchestrator here.**
- [x] T015 **Orchestrator-only.** The orchestrator verifies branch
  `020-delete-featureworkflow` (T014 record) and fast-forwards `main` to it.
  The crew does not push, and no pull request is opened. The integration
  note in `F/verification.md` §PR-1 states that closed FeatureWorkflow rows
  become legacy rows from now on (Q1 = A).

## Phase 5: User Story 1, gate run 1 (P1, BLOCKING)

- [x] T016 [US1] **Orchestrator-only** (it needs live Temporal). Gate run 1
  (plan T030, FR-001): with `main` fast-forwarded to the PR-1 branch, run every command in `F/contracts/gate-runbook.md`
  §Commands verbatim. Paste the commands and their full output into
  `F/verification.md` §Gate-1, then apply §Pass rule.
  **FAIL is a STOP**: record the ids, start no Phase 6 task, and re-run
  this task after the drain. On a PASS, the orchestrator hands back to the
  executor to start T017.
  Commit `F/verification.md` on `main` with the subject
  `docs(020): gate run 1`.

## Phase 6: User Story 4, goldens re-baselined (P2, PR-2; first, before any `src/` edit)

**Goal**: the GraphWorkflow provenance of every pipeline fixture, with an
empty behavioural diff.

**Independent test**: T019 and T020.

- [x] T017 [US4] (executor resumes here, only after T016 PASSED) Create
  the worktree `../Kroker-020-2` on branch `020-delete-featureworkflow-2`
  from `main` at or after the T016 commit.
  Add `T/replay/test_capture_graph.py` (plan T040), a twin of
  `T/replay/test_capture_feature.py`: the same `SDLC_CAPTURE_HISTORIES=1`
  switch, the same capture-twice asserts, and `GRAPH_STARTER` with
  `write_fixtures(scenario.name, first, GRAPH_STARTER.name)`.
- [x] T018 [US4] Re-capture (plan T041). First check that
  `git diff --stat main -- src/` is empty.
  1. Run
     `SDLC_CAPTURE_HISTORIES=1 pytest -m temporal T/replay/test_capture_graph.py`
     for the 18 `SCENARIOS`.
  2. In `T/replay/test_research_retain_replay.py`:
     - switch its capture test to `GRAPH_STARTER`;
     - change the assertion `fixture["workflow"] == "FeatureWorkflow"` to
       `"GraphWorkflow"`;
     - run `SDLC_CAPTURE_RESEARCH_RETAIN=1 pytest -m temporal T/replay/test_research_retain_replay.py -k capture`.
  3. Check that exactly 19 histories and 18 goldens changed, and that
     `golden/assessment_discover_risk.json` and the three non-Feature
     histories are untouched:
     `git status --short T/replay/histories T/replay/golden`.
- [x] T019 [US4] Golden diff gate (plan T042, FR-011, SC-003):
  - write `scripts/check_golden_rebaseline.py`. It takes no arguments. For
    each `T/replay/golden/*.json` it compares the `git show HEAD:<path>`
    JSON with the working-tree JSON, and exits 1 naming the file and key
    if any key other than `workflow` or `source_commit` differs;
  - run it;
  - write `git diff T/replay/golden/` to `F/golden-rebaseline.diff`.

  **A non-zero exit is a STOP.** Commit the re-captured fixtures, the
  script and the diff together.
- [x] T020 [US4] Add `T/replay/test_graph_replay.py` (plan T043). It
  replays each of the 18 scenario histories with
  `replayer(GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow)` and
  `raise_on_replay_failure=True`, parametrised over `SCENARIOS`. Re-point:
  - `T/durability/test_inflight_resume.py` (register GraphWorkflow);
  - `T/durability/test_priced_usage_parity.py` (assert against the T007
    fixture);
  - `T/replay/test_graph_golden_chaos.py` (delete the activity-skew filter
    at `:61-70`, assert equality outright);
  - `T/replay/test_architect_research_usage_replay.py:172`;
  - `T/review/test_review_step_shadowing_chaos.py`;
  - `T/replay/test_fixtures_present.py` (expect
    `workflow == "GraphWorkflow"` for `SCENARIOS`).

  Run `pytest -m temporal T/replay T/durability T/review -q`.
- [x] T021 [US4] Retire the Feature replay (plan T044):
  - delete `T/replay/test_feature_replay.py` and
    `T/replay/test_capture_feature.py`;
  - delete `FEATURE_STARTER`, `_start_feature` and `_feature_workflows`
    from `T/replay/harness.py`;
  - in `T/replay/test_graph_golden.py`, drop the memo_parity FeatureWorkflow
    leg and assert the GraphWorkflow keys `== MEMO_PARITY_KEYS`.

  Run `pytest -m temporal T/replay -q`.

## Phase 7: User Story 5, replay-safe restart (P1, PR-2)

- [x] T022 [P] [US5] Tests first (plan T046):
  - in `T/replay/test_benchmark_replay.py`, add
    `test_replays_with_the_e74_marker_stripped`, which loads
    `benchmark_one_cell`, drops every `MARKER_RECORDED` event whose
    patch-data id starts `e74-graph-child:`, and replays;
  - rewrite `T/graph_workflow/test_pipeline_child_upgrade.py`: remove the
    `StubFeature` stub and the pre-cutover parent, and assert that a new
    parent starts a GraphWorkflow child and that its history replays.

  Confirm the stripped-marker test fails on the current
  `workflow.patched` code: it takes the FeatureWorkflow branch.
- [x] T023 [US5] In `S/workflows/pipeline_child.py`, replace
  `if workflow.patched(f"e74-graph-child:{child_id}"):` with
  `workflow.deprecate_patch(f"e74-graph-child:{child_id}")`, then start
  GraphWorkflow unconditionally (R-1). Delete the else branch and the
  `from .feature import FeatureWorkflow` import. Update the module
  docstring: the marker is deprecated in 020 and its removal is a standing
  item.
  T022 and `test_benchmark_replay_one_cell` must be green.
- [x] T024 [US5] Remove FeatureWorkflow from the inbox open-run types (plan
  T045, FR-005) in `S/channels/inbox.py`:
  - the `list_open_run_ids` default becomes `("GraphWorkflow",)`;
  - `fetch_inbox` uses `"GraphWorkflow", "CrewTaskWorkflow"`;
  - update the docstring.

  Update `T/test_channel_inbox.py` and `T/test_inbox_query.py` first, so
  they fail before the edit.

## Phase 8: User Story 2, no grace-edit tax (P1, PR-2)

**Independent test**: SC-002 and SC-007; quickstart §3.

- [x] T025 [US2] Delete FeatureWorkflow (plan T050, FR-003):
  - update `T/test_worker_registration.py` first to the registered set
    without FeatureWorkflow, and see it fail;
  - delete `S/workflows/feature.py`;
  - in `S/worker.py`, remove the import (`:122`) and the registration
    (`:286`), and update the module docstring (`:3`).

  Run `pytest T/test_worker_registration.py T/graph_workflow/test_cold_import.py T/graph_workflow/test_store_import_pin.py -q`.
- [x] T026 [US2] Execute the T003 classification (plan T070), one commit per
  class:
  - `delete`: the commit body lists each file with its counterpart;
  - `migrate`;
  - `comment-only`.

  `repoint` was done in T005 and `keep` needs no commit. This includes
  `T/review/test_adversary_workflow.py:151` (plan T051), which T003
  classifies. After each commit, run `pytest -q` and compare against the
  T002 list.
- [x] T027 [US2] Delete the architecture and plan composites (plan T052,
  R-6, C5):
  - remove `step()` at `S/stages/architecture/step.py:279` and
    `S/stages/plan/step.py:174`;
  - in `S/stages/architecture/__init__.py` and `S/stages/plan/__init__.py`,
    remove `"step"` from `__all__`, remove the `if name == "step":` branch
    of `__getattr__`, and remove the `_StageModule` class and the
    `sys.modules[__name__].__class__` assignment;
  - update the `revisable_stage` mentions in the docstrings of
    `S/stages/architecture/step.py` and `S/stages/plan/step.py`, and the
    `S/core/context.py` and `S/prompts.py` docstrings.
- [x] T028 [US2] Rewrite the slice tests against
  `prepare`/`produce`/`finish`, keeping every `@pytest.mark.clause`:
  - `T/architecture/test_architecture_slice_contract.py`;
  - `T/plan/test_plan_slice_contract.py`;
  - `T/architecture/test_architecture_step_split.py` (the judge-error
    case at `:116-145`);
  - `T/plan/test_plan_step_split.py` (`:101-130`);
  - `T/calibration/test_calibration_plumbing.py:188-202`, which now
    targets the T006 graph pins.
- [x] T029 [US2] (plan T053) In the **primary checkout**, rewrite ARCH-1.x in
  `S/stages/architecture/architecture.md` and PLAN-1.x in
  `S/stages/plan/plan.md`. They are restated as `prepare`/`produce`/`finish`
  plus the `architect` and `gate.architecture` nodes (and the `plan` and
  `gate.plan` nodes). Remove the "composes them around `revisable_stage`
  for FeatureWorkflow" sentences.
  - Copy the two edited `.md` files into `../Kroker-020-2` (the edit is made
    in the primary checkout; the commit lives on the PR-2 branch,
    `020-delete-featureworkflow-2`).
  - T027, T028 and T029 are **one commit**, staged together in
    `../Kroker-020-2` (Artifact Boundary: the clause change ships with the
    behaviour change).
  - Run `python scripts/check_clauses.py`, then revert the primary
    checkout's copies with `git checkout -- <the two paths>`.
- [x] T030 [US2] Add the comment "no graph node calls this; kept per 020
  FR-006; see .workspace/tasks/2026-11-08-revisable-stage-deletion.md" above
  `_revisable_stage` at `S/workflows/role_host.py:327` (plan T054).
- [x] T031 [US2] PR-2 code verification (plan T059):
  - `pytest -q`, compared against the T002 list;
  - `pytest -m temporal T/replay T/durability T/graph_workflow -q`;
  - `python scripts/check_clauses.py`;
  - `ruff check . && ruff format --check . && mypy`;
  - `cd interfaces/dashboard/frontend && npm test`;
  - `python -c "import sdlc.worker"`.

  Record the results in `F/verification.md` §PR-2.

## Phase 9: Polish (PR-2): docs, AGENTS.md, bookkeeping

- [x] T032 [P] Rewrite `S/workflows/AGENTS.md` (plan T080, FR-013):
  - delete the section "Grace edits while FeatureWorkflow is registered
    (E-74 U6)";
  - remove the FeatureWorkflow readers and writers from every
    ownership-table row, and delete rows owned only by FeatureWorkflow,
    re-homing `_base_sha`, `_integration_wt`, `_codebase_map` and
    `_integration_head` to `GraphWorkflow`;
  - reword rule 4 to name `GraphWorkflow` and `GateHost`.

  Create `T/replay/AGENTS.md` with the replay rules:
  - goldens and histories are written only by the capture tests;
  - intentional golden changes re-baseline from GraphWorkflow with the
    projection diff attached;
  - SG-2 and SG-3 still apply.
- [x] T033 [P] Docs and comments (plan T081, FR-014):
  - update every non-historical `FeatureWorkflow` mention listed by
    `grep -rn FeatureWorkflow src/ docs/ ROADMAP.md PRD.md ARCHITECTURE.md AGENTS.md`;
  - ROADMAP FR-1203 and the E-74 follow-up line in
    `docs/roadmap/pipeline-as-data.md` record the deletion as done;
  - E-74 "Landed" prose and PRD OQ-10's resolution text stay.

  Afterwards, `grep -rn FeatureWorkflow src/` may hit only the plan T081
  allowed list (SC-002): `S/dashboard/fleet.py`,
  `S/channels/transport.py`, the `S/workflows/pipeline_child.py`
  docstring, and the `S/core/models.py` field comments. Paste the grep
  output into `F/verification.md` §SC-002.
- [x] T034 Bookkeeping (plan T082, FR-016):
  - mark `.workspace/tasks/2026-09-17-featureworkflow-deletion-followup.md`
    closed, with a link to this round;
  - create `.workspace/tasks/2026-11-08-revisable-stage-deletion.md`
    (the C2 follow-up) and
    `.workspace/tasks/2026-11-08-run-graph-nongraph-source-cache.md`
    (the R-3 deferral);
  - keep E74-OQ-2, OQ-3 and OQ-5 registered;
  - add a line to the roadmap log under `docs/roadmap/`.

  Use the backlog conventions in `.workspace/tasks/` (check an existing
  card for the header table). No `temporal` command runs in this task.
  **Executor STOP: hand back to the orchestrator here. Do not start T035,
  T036 or T037.**
- [x] T035 **Orchestrator-only** (plan T089). With quickstart §3 green, the
  orchestrator verifies branch `020-delete-featureworkflow-2` against
  `F/golden-rebaseline.diff` and `F/verification.md` §Gate-1, then
  fast-forwards `main` to it. The crew does not push, and no pull request
  is opened. **The fast-forward deploys nothing; do not push a `v*` tag in this
  task.**

## Phase 10: User Story 1, gate run 2 and deploy (P1, BLOCKING; orchestrator-only)

The executor never runs T036 or T037. It stopped after T034.

- [x] T036 [US1] **Orchestrator-only.** Gate run 2 (plan T090, FR-002): rerun the
  `F/contracts/gate-runbook.md` §Commands verbatim, under 1 hour before
  T037. Paste the output into `F/verification.md` §Gate-2 and apply
  §Pass rule. **FAIL is a STOP**: no deploy, and no `v*` tag.
- [x] T037 [US1] **Orchestrator-only.** Restart the worker (plan T091):
  `docker compose pull worker && docker compose up -d worker` (or
  `docker compose up -d --build worker` for a local build of `main`
  after T035's fast-forward). Run the quickstart §4 checks:
  - `docker compose logs worker` shows `worker running on task queue`;
  - the dashboard fleet shows the legacy rows and `errors` is empty
    (SC-005).
- [x] T038 Close-out (plan T092), done by whoever the orchestrator assigns
  after T037: record SC-001 to SC-007 with their
  evidence in `F/verification.md` §Close-out, and commit it on `main` with
  the subject `docs(020): close-out`.

---

## Dependencies

- T001 (done) → T002 → Phase 2. T004 to T007 are [P] among themselves; T003 is
  independent of them.
- Phase 3 (T008 → T009 → T010; T011 [P] after T009's wire is defined) and
  Phase 4 (T012 → T013) both depend on Phase 2. Phases 3 and 4 can run in
  parallel.
- T014 → executor STOP → T015 (orchestrator fast-forward) → **T016 (gate 1,
  orchestrator)** → T017 (executor resumes).
- Phase 6 is strictly sequential: T017 → T018 → T019 → T020 → T021.
  T018 requires `src/` to be untouched.
- Phase 7 (T022 → T023; T024) depends on T021.
- Phase 8: T025 depends on T023 (the import removed) and T024. T026 depends
  on T003 and T025. T027 → T028 → T029 form one commit. T030 is
  independent. T031 comes last.
- Phase 9 (T032 and T033 [P]; T034) depends on T031. Then executor STOP.
- T035 (orchestrator fast-forward) → **T036 (gate 2, orchestrator)** → T037
  (orchestrator) → T038.

## Parallel examples

- **Phase 2**: T004, T005, T006 and T007 touch disjoint test files.
- **PR-1**: one agent takes Phase 3 (fleet and frontend), another takes
  Phase 4 (transport, CLI and operator). They share no file except
  `S/dashboard/api.py`: T010 edits `get_run`, T013 edits `/answer` and
  `/decide`, so serialise those two commits.
- **Phase 9**: T032 and T033 touch disjoint files.

## Implementation strategy

- **MVP = PR-1** (Phases 1 to 4, fast-forwarded into `main` by the
  orchestrator). It is valuable on its own: legacy rows
  are never queried, and legacy ids give clean errors. It is safe to ship
  and to pause after.
- **PR-2** happens only after gate run 1. Its internal order is fixed:
  fixtures first (the US4 evidence), then the replay-safety changes (US5),
  then the deletion (US2), then docs.
- **The deploy** comes only after gate run 2. It is the round's one
  irreversible step, and it has its own STOP.
