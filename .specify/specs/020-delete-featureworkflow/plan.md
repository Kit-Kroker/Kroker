# Implementation Plan: Delete FeatureWorkflow After Grace-Retention (round 020)

**Branch**: `020-delete-featureworkflow` (PR-1), then `020-delete-featureworkflow-2` (PR-2) | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md) | **Base**: `d57c381d`

**Status**: Reviewer-approved (plan checklist, pass 3, 2026-11-08).
- **Pass 1**: fixes-needed with 5 doc-level gaps: fixture counts, the
  `DEFAULT_LINT_CMD` target, stale task refs, and two citations.
- **Pass 2**: fixes-needed with 1 gap: the US4 scenarios still said
  "removed".
- **Pass 3**: approve.
- **Record**: [checklists/plan.md](checklists/plan.md).

**Integration (user decision, 2026-11-08)**: fast-forward merges to `main`,
with **no pull requests**. "PR-1" and "PR-2" are **stage names** only: each
is a branch that the orchestrator verifies and then fast-forwards `main` to.
The crew never pushes. Gate runs 1 and 2 and the worker restart are
**orchestrator-only** steps (they need live Temporal and the deploy host).
This supersedes the PR wording in research R-9 and quickstart.

**Input**: [spec.md](spec.md). GATE 1 cleared on 2026-11-08 with Q1 = A and
Q2 = A. Corrections C1 to C5 were folded in after the consults. Scope:
- user stories 1 to 5;
- FR-001 to FR-016;
- SC-001 to SC-007.

**Design artifacts**:
- [research.md](research.md): decisions R-1 to R-10;
- [data-model.md](data-model.md): `LegacyRun`, `ClosedRef`,
  `LegacyRunError`, and the fixture changes;
- [contracts/fleet-legacy-row.md](contracts/fleet-legacy-row.md): the wire,
  HTTP and frontend contract for legacy rows and legacy-run errors;
- [contracts/gate-runbook.md](contracts/gate-runbook.md): the exact gate
  commands, the pass rule, placement and recovery;
- [quickstart.md](quickstart.md): how to validate;
- [test-inventory.md](test-inventory.md): the preliminary list of 76 test
  files, finalised by T010.

**Consults**:
- advisor [advisor-answer-1.md](advisor-answer-1.md): D1 (a), D2 (a), D3
  per test, D4, D5 two stages. **D4 was overridden**: R-4 re-captures the
  goldens instead of leaving them byte-identical, because the brief asks for
  a re-baseline with the diff attached, and re-captured histories give
  GraphWorkflow 20 replay histories instead of 1 (18 scenarios, `research_retain_grounded`, `architect_research_usage`).
- skeptic [skeptic-answer-1.md](skeptic-answer-1.md). It found C1, C2, C3
  and C5. L1 led to R-2 and R-3, L2 to R-8, L4 to R-6 and the helper
  repoints, L5 to R-4, L6 to the fixture exemption, and L7 to R-10. Its L1
  "synthesize a RunSummary" fix was rejected in favour of the advisor's
  additive field (research R-2).

`S/` = `src/sdlc/`, `T/` = `tests/`, `FE/` = `interfaces/dashboard/frontend/src/`.

## Summary

FeatureWorkflow is deleted in two stages (PR-1 and PR-2, each a branch
fast-forwarded into `main`) with two blocking gates.

**PR-1** is additive and leaves FeatureWorkflow registered:
- closed FeatureWorkflow runs become `closed_legacy` rows that are never
  queried (Q1 = A);
- a query on a legacy id ends as a typed 410 or exit-1 error, not a 500;
- the live graph gate path gets calibration pins;
- the six test helpers that import through `workflows.feature` are
  repointed;
- the two values that need FeatureWorkflow alive are pinned: the memo keys
  and the priced-usage tuples.

**Gate run 1** is the fresh FR-001 evidence and blocks PR-2.

**PR-2** does the deletion:
- the inbox open-type removal;
- `deprecate_patch` in `pipeline_child`;
- re-capture of 19 histories (18 scenarios plus `research_retain_grounded`)
  and 18 goldens from GraphWorkflow, with only
  the `workflow` and `source_commit` fields allowed to change;
- deleting `feature.py`, the worker registration and the arch/plan `step()`
  composites (`_StageModule` included), with the stage clauses rewritten;
- the finalised test classification, executed;
- AGENTS.md and docs.

**Gate run 2** happens under 1 hour before the worker restart. That
restart is the only irreversible step.

## Technical Context

**Language/Version**:
- Python 3.13;
- TypeScript (Vue 3 frontend, vitest).

**Primary Dependencies**:
- `temporalio`: `workflow.deprecate_patch`, `Replayer`, visibility
  `list_workflows` (`status`, `start_time`, `close_time`);
- pydantic v2;
- FastAPI.

**Storage**:
- Temporal dev server (compose, `kroker-temporal-1`, SQLite volume);
- checked-in JSON fixtures.

**Testing**:
- `pytest`: the fast tier, `-m temporal` for replay, capture and durability;
- `vitest`;
- `scripts/check_clauses.py`;
- `ruff` and `mypy`.

**Target Platform**: the Linux compose stack. The worker image is built
from the repo `Dockerfile`.

**Project Type**: a Temporal worker, a CLI, and a web dashboard (FastAPI
plus Vue).

**Performance Goals**: the fleet tick sends N fewer queries for N legacy
rows. Nothing else changes.

**Constraints**:
- no change to any GraphWorkflow command sequence: the goldens'
  `commands`, `close` and `trace` stay byte-identical;
- no wire field removed (FR-015);
- the gate queries are not run during planning;
- rollback is roll-forward only.

**Scale/Scope**:
- about 15 `src/` files edited, 1 deleted (`workflows/feature.py`, 571
  lines);
- 76 test `.py` files classified;
- 37 fixture `.json` files re-captured (19 histories, 18 goldens);
  `golden/assessment_discover_risk.json` and the 3 non-Feature histories
  stay unchanged;
- about 4 frontend files.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template, so it has no
ratified principles. As in rounds 017 to 019, the binding rules are
`AGENTS.md` (root), `S/workflows/AGENTS.md` and the stage `AGENTS.md` files.
The plan is checked against them:

| Rule (source) | How the plan complies | Status |
|---|---|---|
| Grace-edit rule while FeatureWorkflow is registered (`S/workflows/AGENTS.md`) | PR-1 changes no command sequence that FeatureWorkflow executes: fleet, transport, CLI and tests only. `T/replay/test_feature_replay.py` stays green through PR-1, and T019 checks it. The rule is removed only in PR-2 (T080), after gate run 1. | PASS |
| Goldens are never edited by hand (SG-3, `test_graph_golden.py`) | Goldens are written only by `write_fixtures`, through the capture-twice rule. `scripts/check_golden_rebaseline.py` (T042) rejects any hunk outside `workflow`/`source_commit`. | PASS |
| Histories are never re-recorded to make an edit pass (SG-2) | Re-capture is a provenance change: same scenarios, different starter. It runs **before** any PR-2 `src/` edit (T041 precedes T050), so it records pre-deletion behaviour. | PASS, justified |
| A stage behaviour change updates its clauses in the same diff, `<stage>.md` edited in the primary checkout (root `AGENTS.md`, Artifact Boundary) | T053 rewrites ARCH-1.x and PLAN-1.x in the same commit as T052, in the primary checkout. `check_clauses.py` runs in T059. | PASS |
| Single model egress, payload guard, `GUARD_PATCH_ID` (`S/workflows/AGENTS.md`) | Not touched. | PASS |
| Attribute-ownership table kept current (`S/workflows/AGENTS.md` rules 1 to 4) | T080 rewrites the table without FeatureWorkflow columns and rewords rule 4. | PASS |
| `agents/` is product data, not instructions (root `AGENTS.md`) | Not touched. | PASS |

**Post-design re-check**: no violations, and nothing goes in Complexity
Tracking.

## Phases

The task ids here are the plan's. `/speckit-tasks` expands them.

### Phase A: PR-1 (additive; FeatureWorkflow still registered; no gate)

- **T010, test classification (FR-012)**: finalise
  [test-inventory.md](test-inventory.md). Give each of the 76 files exactly
  one class:
  - `delete`, naming its GraphWorkflow counterpart test;
  - `migrate`;
  - `repoint`;
  - `comment-only`;
  - `keep`.

  A `delete` without a named counterpart is not allowed; that file is
  reclassified `migrate`. This task produces only the document, and PR-2
  executes it (T070).
- **T011, `replayer()` move**: move the helper from `test_feature_replay.py`
  into `T/replay/harness.py` with an explicit `workflows` argument. Its
  importers (`test_benchmark_replay`, `test_architect_research_usage_replay`,
  `test_research_retain_replay`) import it from there.
- **T012, helper repoints**: the six helper imports listed in
  test-inventory "Known special cases". Each target is checked to export
  the **target** name, which may differ from the old alias:
  - `_validate_task_graph` becomes `from sdlc.stages.plan.validation import validate_task_graph`;
  - `DEFAULT_LINT_CMD` comes from `sdlc.stages.merge.step` (`:66`).
- **T013, calibration pins on the live gate path (R-7, C2)**: written RED
  first against a fixture copy, then green on the current source. They pin
  `graph_nodes/gate.py` (C7: `judge_error` and `author_model`; SG-4:
  `calibration=`) and the `resolved_model` hand-off in `graph_nodes/precode.py`.
- **T014, pinned constants (R-5)**:
  - extract the `price_usage` tuples from the current
    `histories/greenfield_happy.json` into
    `T/durability/fixtures/priced_usage_pre_e74.json`;
  - pin the FeatureWorkflow memo_parity keys into a constant in
    `test_graph_golden.py`;
  - add assertions that the live values still equal the pinned ones, while
    FeatureWorkflow still exists to prove it.
- **T015, `LegacyRun` and `ClosedRef` in fleet (R-2)**: tests first:
  - N Feature rows give N legacy rows, zero handle calls and `errors == []`;
  - a mixed Graph and Feature window;
  - both query paths, ordered and unordered;
  - a `None` type is still queried;
  - the open-set dedupe;
  - `_PIPELINE_TYPES` still contains FeatureWorkflow, with the
    "never removed" comment.
- **T016, `GET /runs/{id}` and the fleet-summary note**: per the contract,
  §2 and §3.
- **T017, frontend**: `LegacyRun` type, `mapLegacy`, `Run.legacy`, the row
  component hiding mode and cost, a mock row, and `http.test.ts` cases.
- **T018, `LegacyRunError` (R-3)**: in `channels/transport.py`, mapped by
  dashboard `/answer` and `/decide` (410), the CLI (exit 1) and the operator
  tools. Tests use a fake handle whose query raises and whose describe
  reports `FeatureWorkflow`, plus a non-legacy failure that must propagate.
- **T019, PR-1 verification**:
  - quickstart §1;
  - the full fast tier;
  - `-m temporal tests/replay`, where `test_feature_replay` must still be
    green (the grace rule is still in force);
  - hand back: the orchestrator verifies the branch and fast-forwards
    `main` to it. The crew does not push.

### Phase B: gate run 1 (blocking)

- **T030, gate run 1 (FR-001), orchestrator-only**: run
  [contracts/gate-runbook.md](contracts/gate-runbook.md) against the store
  with `main` fast-forwarded to the PR-1 branch. Record every output in
  `verification.md` §Gate-1. **FAIL stops the round**: no Phase C task
  starts, and the gate is re-run after the drain.

### Phase C: PR-2, deletion (starts only on a gate run 1 PASS)

Order inside the phase is fixed. The re-capture comes first, so it records
pre-deletion behaviour.

- **T040, `test_capture_graph.py`**: a GraphWorkflow twin of
  `test_capture_feature.py`, behind `SDLC_CAPTURE_HISTORIES=1`, using the
  capture-twice rule with `GRAPH_STARTER`.
- **T041, re-capture**:
  - run T040 for all 18 `SCENARIOS` (`tests/replay/scenarios.py`);
  - re-capture `research_retain_grounded` with `GRAPH_STARTER`, changing its
    capture test's starter and the assertion `fixture["workflow"] == "GraphWorkflow"`;
  - commit with `src/` untouched since the gate run 1 commit.
- **T042, golden diff gate (FR-011, SC-003)**: write
  `scripts/check_golden_rebaseline.py`. It parses old and new goldens and
  fails if any key other than `workflow` or `source_commit` differs.
  - Save the `git diff` as `golden-rebaseline.diff` for the orchestrator's
    verification.
  - A non-empty `commands`, `close` or `trace` difference is a **STOP**:
    investigate, and do not merge.
- **T043, `test_graph_replay.py`**: replay every re-captured history with
  `[GraphWorkflow, DeploymentWorkflow, CrewTaskWorkflow]`, using
  `raise_on_replay_failure`.
  - Re-point `test_inflight_resume.py` and `test_priced_usage_parity.py`
    (the latter against the T014 constant).
  - Re-point `test_graph_golden_chaos.py`, removing its activity-skew filter.
  - Re-point `test_architect_research_usage_replay.py:172` and
    `review/test_review_step_shadowing_chaos.py`.
  - Update `test_fixtures_present.py` to expect `workflow == "GraphWorkflow"`.
- **T044, retire the Feature replay**:
  - delete `test_feature_replay.py`, `test_capture_feature.py` and
    `FEATURE_STARTER` and `_start_feature` in `harness.py`;
  - drop the memo_parity Feature leg, which now asserts against the T014
    constant.
- **T045, inbox open types (FR-005)**: `channels/inbox.py:91` and `:111`
  become GraphWorkflow (plus `CrewTaskWorkflow` in `fetch_inbox`). Update
  the docstring and the tests (`test_channel_inbox.py`, `test_inbox_query.py`).
- **T046, `deprecate_patch` (FR-009, R-1)**: in `pipeline_child.py`.
  Tests:
  - `test_benchmark_replay` passes unchanged;
  - a new stripped-marker replay of `benchmark_one_cell`;
  - `test_pipeline_child_upgrade.py` rewritten: a new parent starts a
    GraphWorkflow child, and the `StubFeature` stub is removed.
- **T050, delete FeatureWorkflow (FR-003)**:
  - delete `S/workflows/feature.py`;
  - in `S/worker.py`, remove the import (`:122`), the registration (`:286`)
    and the docstring mention;
  - update `T/test_worker_registration.py` to the new registered set.
- **T051, delete the dead `_run_handoff` source-grep**: in
  `T/review/test_adversary_workflow.py:151`, point the assertion at
  `stages/code/step.py` or remove it, per T010.
- **T052, arch/plan composites (FR-007, R-6, C5)**: delete `step()` in both
  stages. Delete `_StageModule`, `"step"` in `__all__` and the
  `__getattr__` branch. Update `prompts.py` and `core/context.py`
  docstrings.
- **T053, stage clauses**: rewrite `architecture.md` and `plan.md`
  (ARCH-1.x, PLAN-1.x) and the slice-contract and step-split tests against
  `prepare`/`produce`/`finish`, keeping the clause markers. This is done in
  the primary checkout, in the same commit as T052.
- **T054, `_revisable_stage` stays (FR-006)**: no code change. Add a
  comment at `role_host.py:327`: "no graph node calls this; kept per 020
  FR-006; see the follow-up card". File that card (see GATE 2 item 1).
- **T059, PR-2 code verification**:
  - the fast tier;
  - `-m temporal tests/replay tests/durability tests/graph_workflow`;
  - `check_clauses.py`, `ruff`, `mypy`, `vitest`;
  - a cold import of `sdlc.worker`.

### Phase D: PR-2, tests, docs and bookkeeping

- **T070, execute the T010 classification**: one commit per class bucket.
  Each `delete` cites its counterpart in the commit message. Coverage of
  shared behaviour must not drop (FR-012).
- **T080, `S/workflows/AGENTS.md` (FR-013)**:
  - remove the grace-edit section;
  - move the "intentional golden changes re-baseline from GraphWorkflow
    with the diff attached" sentence into the replay guidance (a new short
    `T/replay/AGENTS.md`);
  - rewrite the ownership table and rule 4.
- **T081, docs and comments (FR-014)**: work through the `src/`
  docstrings, the slice `*.md` files, ROADMAP FR-1203 and the E-74
  follow-up line, PRD OQ-10 and ARCHITECTURE. Historical E-74 "Landed"
  prose stays.
  - **The SC-002 allowed list** in `src/` after T081: `dashboard/fleet.py`
    (`_PIPELINE_TYPES` and the legacy partition), `channels/transport.py`
    (`LegacyRunError`), the `pipeline_child.py` docstring (marker history),
    and the `core/models.py` field comments for None-for-legacy fields
    (FR-015). Any other hit fails T081.
- **T082, card and register (FR-016)**:
  - close `.workspace/tasks/2026-09-17-featureworkflow-deletion-followup.md`;
  - file follow-up cards for `_revisable_stage` and `run_graph`
    non-graph `RunSource` caching;
  - E74-OQ-2, OQ-3 and OQ-5 stay registered;
  - update `ROADMAP.md` and its log (`docs/roadmap/`).
- **T089, PR-2 verification**: quickstart §3 in full, then hand back.
  The orchestrator verifies the branch (with `golden-rebaseline.diff` and
  the gate run 1 record) and fast-forwards `main` to it. The crew does not
  push. The fast-forward does not deploy.

### Phase E: deploy (blocking gate; orchestrator-only)

The executor stops before T090 and hands back.

- **T090, gate run 2 (FR-002), orchestrator-only**: the runbook, under 1 hour before T091,
  recorded in `verification.md` §Gate-2. A FAIL means no deploy.
- **T091, worker restart, orchestrator-only**: `docker compose pull worker && docker compose
  up -d worker`, or the local build. Run the quickstart §4 checks. Check
  the fleet: legacy rows show and `errors` is empty (SC-005).
- **T092, close-out**: record SC-001 to SC-007 evidence in
  `verification.md`.

## Worker-restart and replay-safety analysis (FR-008)

Every execution class that exists when the worker restarts is listed here.

| Execution class | On the new worker | Evidence or mitigation |
|---|---|---|
| Running FeatureWorkflow | **Would be stranded** (task fails: type not registered) | G1 = 0 at gate run 2. Recovery: terminate and resubmit (runbook). |
| Running TidyUp/Benchmark parent started before the cutover (its history has a FeatureWorkflow child) | Would hit a nondeterminism error at the child | G2 = 0, any start time (Q2 = A). |
| Running TidyUp/Benchmark started after the cutover | G2 = 0 means none exist. If one did, `deprecate_patch` would match its marker. | T046: `benchmark_one_cell` replay and the stripped-marker replay. |
| Closed FeatureWorkflow, fleet | Never queried; shown as a legacy row | T015, SC-005 |
| Closed FeatureWorkflow, reached by id (CLI, operator, `/answer`) | Query fails, giving `LegacyRunError` (410 / exit 1) | T018 |
| Closed FeatureWorkflow, `/runs/{id}/graph` and `/graph_state`, fleet summary | `describe()` is a server RPC with no worker needed; the non-graph `RunSource` path exists today | No change; caching deferred (R-3) |
| Closed pre-cutover Tidy/Benchmark parent, queried (`sdlc tidyup report`) | Nondeterminism error on replay (it has a Feature child and no marker) | **Accepted loss** (R-1). Recorded in the runbook. |
| Closed post-cutover parent, queried | Replays through `deprecate_patch` | T046 |
| GraphWorkflow (open or closed) | Unchanged command sequence | The goldens' commands, close and trace are byte-identical (T042), and `test_graph_replay` passes over the 18 scenario histories (T043). |
| Crew, Deployment, Assessment, Triage, Reflect | Not on any edited replay path. Their parents are FeatureWorkflow or GraphWorkflow, and TERMINATE is the parent-close policy. | Their existing replay tests pass (`assessment_discover_risk`, crew and deployment through `test_graph_replay`). A crew or deployment child of a Running FeatureWorkflow cannot exist when G1 = 0. |
| Schedules | Only `ReflectWorkflow` is managed. An unmanaged schedule could start a removed type. | G0 `schedule list` check (runbook) |

Edited modules on a live replay path:
- `pipeline_child.py`: BenchmarkWorkflow and TidyUpWorkflow;
- `stages/architecture/step.py`, `stages/plan/step.py` and their
  `__init__`: GraphWorkflow imports `prepare`/`produce`/`finish` only.
  Deleting `step()` and `_StageModule` changes no command, and T042/T043
  prove it.

Nothing else on any registered workflow's path is edited, apart from
docstrings.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/020-delete-featureworkflow/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
├── test-inventory.md          # T010 finalises it
├── contracts/{fleet-legacy-row.md, gate-runbook.md}
├── advisor-*-1.md  skeptic-*-1.md
├── verification.md            # T030, T090, T092
├── golden-rebaseline.diff     # T042
├── checklists/{requirements.md, plan.md}
└── tasks.md                   # /speckit-tasks
```

### Source code touched

```text
src/sdlc/
├── worker.py                       # T050
├── workflows/{feature.py ✗, pipeline_child.py, AGENTS.md, role_host.py(comment)}
├── stages/{architecture,plan}/{step.py, __init__.py, *.md}
├── channels/{inbox.py, transport.py}
├── dashboard/{fleet.py, api.py, fleet_summary.py(comment)}
├── operator/tools.py   cli.py
└── docstrings: core/context.py, core/models.py, prompts.py, benchmarks/workflow.py, workflows/{tidyup,build,gates,run_host,report_host,models,scanning,fanout,deployment,graph}.py
interfaces/dashboard/frontend/src/{api/types.ts, api/http.ts, api/http.test.ts, api/mock/index.ts, features/fleet/FleetTable.vue}
tests/replay/{harness.py, test_capture_graph.py (new), test_graph_replay.py (new), histories/, golden/, AGENTS.md (new)}
scripts/check_golden_rebaseline.py (new)
```

**Structure decision**: the existing layout. No new package.

## GATE 2 items for the orchestrator

1. **Delete `_revisable_stage` too?** The card originally listed it, and
   C2 shows it has no caller once T052 lands. FR-006 keeps it (ruled at
   GATE 1). The plan files a follow-up card. Deleting it here would add
   `RoleHost`, `StageServices` and `context.py` edits and retire three
   source-pin tests. **Recommendation**: keep FR-006 for this round and
   take the follow-up.
2. **The advisor D4 override** (re-capturing goldens rather than leaving
   them byte-identical): research R-4.
3. **Accepted loss**: a closed pre-cutover Tidy/Benchmark parent can no
   longer be queried after the deploy (R-1).

## Complexity Tracking

None.
