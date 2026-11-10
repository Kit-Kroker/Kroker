# Feature Specification: Delete FeatureWorkflow After Grace-Retention

**Feature Branch**: `020-delete-featureworkflow` (spec directory only; no branch created)

**Created**: 2026-11-08

**Status**: Approved. GATE 1 cleared by the user (relayed by the
orchestrator) on 2026-11-08: Q1 = A, Q2 = A. See Rulings.

**Input**: Orchestrator brief (2026-11-08): "Delete FeatureWorkflow after
grace-retention (E-74 spec section 8.5)." Source card:
`.workspace/tasks/2026-09-17-featureworkflow-deletion-followup.md` (size L).
Code references are against `main` at `d57c381d`.

## Context

E-74 moved every new run onto `GraphWorkflow` and kept `FeatureWorkflow`
registered on the worker only to carry in-flight runs to a terminal state
(PRD OQ-10, grace-retention). While it stays registered, every edit to code
it shares is bound by the grace-edit rule in `src/sdlc/workflows/AGENTS.md`
(wrap command-sequence changes in `workflow.patched`, never re-record the
FeatureWorkflow histories). That rule is a standing tax on the pipeline and
on every slice (`stages/*`, `build`, `run_host`).

The card says the grace gate passed on 2026-10-02. That reading is five weeks
old, and the card never recorded the M2 worker-deploy instant that its second
query needs. The deletion therefore starts from a fresh gate, not from the
card's triage note.

This feature removes the grace-only code and the grace-edit rule, and keeps
the two things that must outlive it: closed pre-cutover runs stay visible on
the fleet view, and the golden traces stay as the permanent behavioural
baseline.

## Card verification (the card's file list treated as hypotheses)

| Card item | Verdict | Evidence |
|---|---|---|
| `FeatureWorkflow` class, `_pipeline`, dead `_run_handoff` | **Confirmed** | `workflows/feature.py:146`, `:347`, `:193`. `_run_handoff` has no caller; only a source-grep test (`tests/review/test_adversary_workflow.py:151`) mentions it. The live `_run_handoff` is `stages/code/step.py:391` and **stays**. |
| `_revisable_stage` and `StageServices.revisable_stage` | **WRONG: shared with GraphWorkflow** | `GraphWorkflow` builds its `StageServices` with `revisable_stage=self._revisable_stage` (`workflows/graph.py:74`); the method lives on `RoleHost` (`role_host.py:327`) and is pinned by `tests/calibration/*` and `tests/test_soft_gate_auto_approval.py`. Cannot be removed by this feature without re-homing the generic gate. See FR-006. |
| `step()` composites of architecture and plan | **Confirmed** | `stages/architecture/step.py:279`, `stages/plan/step.py:174`. Graph nodes call only `prepare`/`produce`/`finish` of these two. The other stages' `step()` functions (intake, research, clarify, analyze, merge, deploy, ...) are **used by graph nodes and stay**. |
| `else` branch of `workflows/pipeline_child.py` | **Confirmed, with a replay trap** | `pipeline_child.py:48-52`. The `workflow.patched("e74-graph-child:<id>")` marker is already in the histories of parents that started children after cutover; see FR-009. |
| `tests/replay/histories/` deleted wholesale | **PARTLY WRONG** (see C1) | Three histories are not FeatureWorkflow runs and are loaded by live tests: `benchmark_one_cell` (`test_benchmark_replay.py`), `assessment_discover_risk` (`test_capture_assessment.py`), `architect_research_usage`. `research_retain_grounded` (`test_research_retain_replay.py`) is a FeatureWorkflow history that a live test loads. `greenfield_happy` is the chaos baseline in `test_graph_golden_chaos.py:80`. |
| `tests/replay/test_feature_replay.py` | **Confirmed** | Replays FeatureWorkflow histories only. |
| FeatureWorkflow-only tests, migrate the rest | **Confirmed, large** | 113 test files mention `FeatureWorkflow`; the split between "delete", "migrate to GraphWorkflow" and "just a comment" is not done yet (plan task). |
| `FeatureWorkflow` out of `channels/inbox.py` open-run types | **Confirmed** | `channels/inbox.py:91` default tuple and `:111` `fetch_inbox`. Also the open-run default used by `dashboard/fleet.py` via `list_open_run_ids`. |
| Grace-edit rule out of `workflows/AGENTS.md` | **Confirmed** | Section "Grace edits while FeatureWorkflow is registered (E-74 U6)". Also the ownership table's `FeatureWorkflow` columns and rule 4 wording. |
| Keep `FeatureWorkflow` in `fleet.py` `_CLOSED_QUERY` / `_CLOSED_QUERY_UNORDERED` | **Confirmed, but incomplete** | The type filter lives in `_PIPELINE_TYPES` (`fleet.py:61`) and survives. **But** `_fetch_closed` (`fleet.py:105`) sends a `run_summary` query to every closed run, and Temporal can only answer a query on a closed run through a worker that has the workflow type registered. Resolved by Q1 = A. |
| Keep `tests/replay/golden/` | **Confirmed** | 19 golden files (18 FeatureWorkflow-captured scenarios plus `assessment_discover_risk`, which is AssessmentWorkflow and stays unchanged), consumed by `test_graph_golden.py`, `test_graph_golden_chaos.py`, `test_fixtures_present.py`. They were captured from FeatureWorkflow (`FEATURE_STARTER`); that starter goes away. |
| Out of scope: E74-OQ-2, E74-OQ-3, E74-OQ-5 | Taken as given | |

Further places the card did not list that name or register the type:
`worker.py:122,286` (import and registration), `cli.py:730` (comment),
`benchmarks/workflow.py` and `workflows/tidyup.py` (docstrings and a
`FeatureWorkflow` return-string comment), `core/context.py` (docstrings),
`core/models.py`, `workflows/models.py`, `workflows/report_host.py`,
`workflows/run_host.py`, `workflows/gates.py`, `workflows/build.py`,
`prompts.py`, `scripts/dump_read_fixtures.py:86` (a `legacy-run` fixture that
must keep working), the `docs/` and `*.md` slice docs, and ROADMAP/PRD/
ARCHITECTURE prose.

## Rulings (GATE 1, user via orchestrator, 2026-11-08)

- **Q1 = A**: closed `FeatureWorkflow` runs are listed from visibility
  metadata only (id, status, close time). No `run_summary` (or `run_state`)
  query is sent to a `FeatureWorkflow`-typed row; the fleet renders a
  "legacy run, summary unavailable" row. No `FeatureWorkflow` stub is kept.
- **Q2 = A**: gate query 2 has no time filter. The gate requires **no
  Running `TidyUpWorkflow` or `BenchmarkWorkflow` of any start time**:

      temporal workflow list --query "ExecutionStatus='Running' AND WorkflowType='FeatureWorkflow'"
      temporal workflow list --query "ExecutionStatus='Running' AND (WorkflowType='TidyUpWorkflow' OR WorkflowType='BenchmarkWorkflow')"

  The gate queries are run only by the blocking implementation tasks
  (FR-001, FR-002), never during planning.

## Factual corrections after GATE 1 (2026-11-08, from the advisor and skeptic consults)

These correct the verification table above. None of them changes a ruling.

- **C1 (histories)**: `research_retain_grounded` **is** a FeatureWorkflow
  history (the 009 replay proof, `test_research_retain_replay.py` asserts
  `fixture["workflow"] == "FeatureWorkflow"`). 19 of 22 histories are
  FeatureWorkflow (the 18 `SCENARIOS` plus `research_retain_grounded`); only `benchmark_one_cell` (BenchmarkWorkflow with
  GraphWorkflow children), `assessment_discover_risk` and
  `architect_research_usage` (GraphWorkflow) are not. FeatureWorkflow
  histories are also loaded by `test_graph_golden_chaos.py`,
  `test_fixtures_present.py`, `test_architect_research_usage_replay.py:172`
  (`architect_research_tool`), `durability/test_inflight_resume.py`,
  `durability/test_priced_usage_parity.py` and
  `review/test_review_step_shadowing_chaos.py`. FR-010 is therefore met by
  **re-capturing** the 18 scenario histories (and `research_retain_grounded`)
  from GraphWorkflow, not by deleting them.
- **C2 (`_revisable_stage`)**: it is wired into GraphWorkflow's
  `StageServices` (`graph.py:74`) but **no graph node calls it**; its only
  callers are the architecture/plan `step()` composites that FR-007 deletes.
  FR-006 stands as ruled (kept this round). The C7/SG-4 source pins in
  `tests/calibration/` and `tests/test_soft_gate_auto_approval.py` must also
  pin the live `graph_nodes/gate.py` path, or they become vacuous. Whether to
  delete `_revisable_stage` is raised at GATE 2.
- **C3 (FR-009)**: the "removable" alternative is withdrawn.
  `benchmark_one_cell.json` carries an `e74-graph-child:` marker, and closed
  parents are replayed for queries (`sdlc tidyup report`). FR-009 is met by
  `workflow.deprecate_patch` only.
- **C4 (SC-004)**: "GraphWorkflow histories" means the re-captured scenario
  histories of C1 plus `architect_research_usage`.
- **C5 (stage packages)**: `stages/architecture/__init__.py` and
  `stages/plan/__init__.py` export `step` through a `_StageModule` property;
  FR-007 includes removing it, and updating the `ARCH-1.x` / `PLAN-1.x`
  clauses in `architecture.md` / `plan.md` in the same diff.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator is told, with fresh evidence, that deletion is safe (Priority: P1)

Before any code is removed, the person landing the change re-runs both
Temporal gate queries against the live store and records the result.

**Why this priority**: Unregistering a workflow type while a run of that type
(or a parent that can still start one) is open strands it: its next workflow
task fails with an unregistered-type error and, for a pre-cutover parent, the
`else` branch is gone. This is the only irreversible-by-roll-back step
(rollback is roll-forward only, per E-74).

**Independent Test**: Run the two queries and record output, timestamp and
store identity in the verification file; the deletion tasks cannot start
without an empty result for both.

**Acceptance Scenarios**:

1. **Given** zero Running `FeatureWorkflow` and zero Running TidyUp/Benchmark parents of any start time (Q2 = A),
   **When** the gate is run, **Then** the verification file records both
   empty results with time and store, and deletion tasks may proceed.
2. **Given** either query returns a run, **When** the gate is run, **Then**
   no deletion task runs; the run ids are recorded and the work waits for
   drain. There is no override flag.
3. **Given** the gate passed but a deploy of the new worker has not yet
   happened, **When** the plan orders work, **Then** the gate is re-run
   immediately before the worker with the type removed is deployed, not only
   before the branch is merged.

---

### User Story 2 - Maintainers edit pipeline code without the grace-edit tax (Priority: P1)

After the change, no workflow class carries the legacy command sequence.
`FeatureWorkflow`, `_pipeline`, `_run_handoff` (the dead one), the
architecture/plan `step()` composites, the `pipeline_child` else-branch and
the grace-edit rule are gone; the worker registers `GraphWorkflow` and the
other live types only.

**Why this priority**: This is the purpose of the feature.

**Independent Test**: `FeatureWorkflow` appears nowhere in `src/` except the
fleet closed-run filter and the Q1 legacy-row type check; the fast test tier is
green apart from the 8 pre-existing fast-tier failures recorded in memory;
`ruff`, `mypy` clean.

**Acceptance Scenarios**:

1. **Given** the change is merged, **When** the worker boots, **Then** it
   registers every workflow type it did before except `FeatureWorkflow`, and
   `get_worker_activities` still passes its durable-agent guard check.
2. **Given** a new run is started by CLI, dashboard, operator, benchmark cell
   or tidy-up fix run, **When** it executes, **Then** it runs as
   `GraphWorkflow` with command sequences identical to the goldens.
3. **Given** `workflows/AGENTS.md`, **When** read after the change, **Then**
   it contains no grace-edit section, no claim that `FeatureWorkflow` is
   registered, and an ownership table without dead `FeatureWorkflow` columns.

---

### User Story 3 - Closed pre-cutover runs stay visible on the fleet (Priority: P1)

The fleet view keeps listing closed `FeatureWorkflow` runs indefinitely,
from visibility metadata only, as "legacy run, summary unavailable" rows
(Q1 = A).

**Why this priority**: The card marks this as permanent. Losing it silently
would hide run history.

**Independent Test**: With a fake client returning a closed
`FeatureWorkflow`-typed run, the fleet snapshot contains a legacy row for it,
no query was sent to its handle, and no `InboxError` for it.

**Acceptance Scenarios**:

1. **Given** a closed `FeatureWorkflow` run in the closed-run window and the
   type unregistered, **When** the fleet ticks, **Then** it appears as a
   "legacy run, summary unavailable" row, no `run_summary`/`run_state`
   query is issued to it, and `snap.errors` has no entry for it.
2. **Given** both the ordered and unordered closed queries,
   **When** the fleet falls back from ORDER BY, **Then** both still include
   `FeatureWorkflow`.
3. **Given** an open-run listing (inbox and fleet), **When** queried after
   the change, **Then** `FeatureWorkflow` is no longer in the open-run
   types (nothing can be Running as that type).

---

### User Story 4 - Goldens remain the behavioural baseline, re-baselined with a reviewable diff (Priority: P2)

`tests/replay/golden/` stays. Its provenance moves from "captured from
FeatureWorkflow" to "projected from GraphWorkflow". The re-baseline diff is
attached to the review.

**Why this priority**: Goldens are what stops `GraphWorkflow` command-sequence
drift once FeatureWorkflow no longer exists to compare against.

**Independent Test**: Re-baseline from GraphWorkflow; the diff versus the
committed goldens is empty for `commands` and `close` (the FeatureWorkflow
parity guarantee of `test_graph_golden.py` / SG-3). Any non-empty diff is a
STOP, investigated before merge, not accepted.

**Acceptance Scenarios**:

1. **Given** the 18 FeatureWorkflow-captured goldens, **When** regenerated from GraphWorkflow,
   **Then** the diff is attached to the review and empty (or every hunk is
   explained and individually approved).
2. **Given** the three non-Feature histories (benchmark, assessment,
   architect-research usage), **When** the 19 FeatureWorkflow histories
   (the 18 scenarios and `research_retain_grounded`) are replaced in place
   by GraphWorkflow captures, **Then** the three are byte-unchanged and
   every replay and chaos test, including those that use the
   `greenfield_happy` baseline, still finds the history it loads.
3. **Given** the histories have been replaced in place by GraphWorkflow
   captures, **When** `test_feature_replay.py` is removed, **Then** a
   GraphWorkflow replay test replays every one of them, so no replay
   coverage is lost without a migrated counterpart.

---

### User Story 5 - The worker restart is replay-safe (Priority: P1)

The analysis of what happens to every open and closed execution when the new
worker replaces the old one is written down and tested where testable.

**Why this priority**: The class of bug this feature can cause is silent and
only shows at the next workflow task.

**Independent Test**: See FR-008 and FR-009; the analysis is a checked-in
artifact, the testable parts are replay tests.

**Acceptance Scenarios**:

1. **Given** the histories of parents (`BenchmarkWorkflow`, `TidyUpWorkflow`)
   that recorded `e74-graph-child:<id>` markers, **When** they replay on the
   new code, **Then** replay succeeds (marker handled per FR-009).
2. **Given** `GraphWorkflow`, `CrewTaskWorkflow`, `DeploymentWorkflow`,
   `AssessmentWorkflow` and `TriageWorkflow` histories, **When** replayed on
   the new code, **Then** all pass: no shared module edit changed their
   command sequence.

---

### Edge Cases

- A new `FeatureWorkflow` start request after deletion (stale CLI, scripted
  client, old dashboard): the server accepts the start and the task fails on
  the worker. The plan states how this is surfaced (CLI/dashboard never start
  it today; the analysis records that no in-repo caller does).
- A Running `FeatureWorkflow` that appears *between* the gate and the deploy.
  Hence FR-002 (gate re-run at deploy time).
- Workflow ids reused: a closed FeatureWorkflow id queried by a stale client
  after deletion.
- `scripts/dump_read_fixtures.py` `legacy-run` fixture and its consumers
  (frontend `http.ts` null `stage_marks` contract) keep working: the wire
  contract for "no stage marks / no graph sha" stays, it just stops being
  produced for new runs.
- Memoisation or content keys that embed the workflow type name (to be
  checked in the plan; none found yet).
- Cold import: `tests/graph_workflow/test_cold_import.py` and
  `test_store_import_pin.py` must still pass once `feature.py` is gone.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before any deletion task, the plan MUST run both Temporal gate
  queries against the live store and record verbatim output, UTC timestamp and
  store identity in the feature's `verification.md`. Query 1: Running
  `FeatureWorkflow`. Query 2: Running `TidyUpWorkflow` or `BenchmarkWorkflow`
  of any start time (Q2 = A; exact text in Rulings). The 2026-10-02 result MUST NOT be reused.
- **FR-002**: The gate MUST be re-run immediately before deploying the worker
  that no longer registers `FeatureWorkflow`. A non-empty result blocks
  deletion and deploy; there is no override.
- **FR-003**: `FeatureWorkflow` (class and its module), `_pipeline`, the dead
  `feature.py:_run_handoff`, its import and its registration in `worker.py`
  MUST be removed. The live `stages/code/step.py:_run_handoff` MUST stay.
- **FR-004**: Closed pre-cutover runs MUST remain listed by the fleet's
  closed-run queries (`_CLOSED_QUERY`, `_CLOSED_QUERY_UNORDERED`) permanently,
  with no per-tick `InboxError`. Per Q1 = A, a closed `FeatureWorkflow`-typed
  row MUST be built from visibility metadata only (id, status, close time),
  MUST NOT trigger a `run_summary` or `run_state` query, and MUST render on
  the dashboard as "legacy run, summary unavailable". No stub class is kept.
  The "never removed" disjunction note MUST be kept at the query.
- **FR-005**: `FeatureWorkflow` MUST be removed from open-run types in
  `channels/inbox.py` (default tuple and `fetch_inbox`) and thereby from the
  fleet's open-run listing.
- **FR-006**: `_revisable_stage` and `StageServices.revisable_stage` MUST stay
  as long as `GraphWorkflow` (or any test of the generic gate) uses them. This
  feature MUST NOT remove or rename them. If the plan finds the graph gate
  could stop using them, that is a separate change.
- **FR-007**: The architecture and plan `step()` composites, their only
  callers in `FeatureWorkflow`, and tests that exist only to exercise them
  MUST be removed; `prepare`/`produce`/`finish` of both stages and every other
  stage's `step()` MUST stay. Tests that cover behaviour reachable only via a
  composite MUST be migrated to the split functions or the graph path, not
  dropped.
- **FR-008**: The plan MUST contain a worker-restart/replay-safety analysis:
  for each workflow type that remains registered, whether any module edited
  by this feature is on its replay path, and the evidence (replay tests run
  against checked-in histories) that its command sequence is unchanged. It
  MUST also address executions that are neither Running `FeatureWorkflow` nor
  gated by the queries: closed `FeatureWorkflow` runs (Q1 = A: never queried), and parents whose
  history already contains a child-start of type `FeatureWorkflow`.
- **FR-009**: The `workflow.patched("e74-graph-child:<id>")` call in
  `execute_pipeline_child` MUST become `workflow.deprecate_patch("e74-graph-child:<id>")`
  followed by the unconditional GraphWorkflow start, so histories with and
  without the marker replay (C3). Removing the `patched` call outright is
  not allowed.
- **FR-010**: `tests/replay/test_feature_replay.py`, the FeatureWorkflow
  capture test and `FEATURE_STARTER` MUST be removed. Every
  FeatureWorkflow-captured history MUST be replaced in place by a
  GraphWorkflow capture of the same scenario (C1), and a GraphWorkflow replay
  test MUST replay each of them. Non-Feature histories stay unchanged. No
  remaining test may fail on a missing history.
- **FR-011**: `tests/replay/golden/` MUST be kept. It MUST be re-baselined
  from `GraphWorkflow`, with the full diff against the committed goldens
  attached to the review. A non-empty diff in `commands` or `close` is a STOP.
  No golden may be edited by hand to make a test pass.
- **FR-012**: Tests that reference `FeatureWorkflow` MUST each be classified
  delete / migrate-to-GraphWorkflow / comment-only, recorded in the plan.
  Coverage of behaviour that GraphWorkflow shares (gates, budget, memory,
  pending, board, integration, brownfield, tidy-up, crew wiring) MUST NOT drop;
  a test with no GraphWorkflow counterpart MUST be migrated first, then the
  old one removed.
- **FR-013**: The grace-edit section of `src/sdlc/workflows/AGENTS.md` MUST be
  removed, the sentence about regenerating goldens after deletion MUST be
  moved into the replay-test guidance, and the attribute-ownership table and
  rule 4 MUST be corrected for the loss of `FeatureWorkflow`.
- **FR-014**: Docstrings, comments and docs that describe `FeatureWorkflow` as
  current MUST be updated or removed (the `src/`, `docs/`, slice `*.md`,
  ROADMAP, PRD and ARCHITECTURE hits). References that are historical (E-74
  records, roadmap "Landed" prose) MAY stay; the plan MUST say which. The
  ROADMAP FR-1203 line and E-74 follow-up note MUST reflect completion.
- **FR-015**: The persistent wire contracts MUST NOT change: the optional
  `RunState`/`RunSummary` fields that are `None` for FeatureWorkflow runs
  (`graph_sha`, `stage_marks`, ...) stay, since closed legacy summaries and
  the frontend `legacy-run` fixture depend on them.
- **FR-016**: The card (`.workspace/tasks/2026-09-17-featureworkflow-
  deletion-followup.md`) MUST be closed or moved per the repo's backlog
  convention, and the three out-of-scope register candidates stay registered.

### Key Entities

- **Legacy run**: a closed Temporal execution of type `FeatureWorkflow`; has
  visibility metadata and a history, but no registered type to answer queries.
- **Gate**: the pair of Running-workflow queries whose emptiness licenses
  deletion; its record is evidence, with time and store identity.
- **Golden**: per-scenario projection of command sequence, close status and
  stage/gate trace, the permanent regression baseline of the pipeline.
- **Replay-safety analysis**: the written per-workflow-type argument that the
  restart does not change any live or replayed command sequence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both gate queries are recorded empty with timestamps within 24
  hours of the worker deploy; zero deletion commits precede the first record.
- **SC-002**: After deletion, a search of `src/` for `FeatureWorkflow`
  returns only the fleet closed-run filter and the explicitly approved
  historical references listed in the plan; the worker registers one fewer
  workflow type and the rest unchanged.
- **SC-003**: Every golden re-baselined from GraphWorkflow shows an empty
  `commands` and `close` diff versus the previous goldens (or each non-empty
  hunk is individually explained and approved).
- **SC-004**: Replay of every retained history (GraphWorkflow, benchmark,
  assessment, crew, deployment, triage, architect-research, research-retain,
  and parents carrying `e74-graph-child` markers) passes with
  `raise_on_replay_failure`, and no pre-existing passing test is lost
  without a recorded migrated counterpart.
- **SC-005**: With a fake client returning N closed `FeatureWorkflow` runs,
  the fleet snapshot shows N "legacy run, summary unavailable" rows, issues zero queries to them, and zero errors on every
  tick.
- **SC-006**: The fast test tier, `ruff check`, `ruff format --check` and
  `mypy` show no new failures versus main (the 8 known fast-tier failures
  excepted).
- **SC-007**: A contributor editing a stage step needs no `workflow.patched`
  for FeatureWorkflow replay: the grace-edit rule is gone and no test enforces
  it.

## Assumptions

- Rollback is roll-forward only (E-74 decision); this feature does not add
  a way to bring `FeatureWorkflow` back.
- The compose Temporal store (`kroker-temporal-1`) is the production store
  the gates query; the plan confirms the target before running them.
- Standard visibility is in use on the dev server (ORDER BY fallback in
  `fleet.py` stays).
- No in-repo code starts `FeatureWorkflow` (verified: only
  `pipeline_child.py`'s else branch and test harnesses); out-of-repo clients
  are out of scope.
- `GraphWorkflow` golden parity (E-74 §7.3) held at cutover and still holds on
  `main`; the re-baseline is expected to be diff-free.
- The wire fields that are `None` for legacy runs remain optional.
- Per-task topology (E74-OQ-3), research-as-topology (E74-OQ-2) and retro on
  FAILED executions (E74-OQ-5) stay registered candidates and are not touched.
- `.specify/feature.json` is repointed to this directory; the brief's
  `.specify/specs/<slug>/` location is used (not `specs/`).
