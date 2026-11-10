# Research: Delete FeatureWorkflow (020)

Base `d57c381d`. Consults:
- [advisor-answer-1.md](advisor-answer-1.md), on decisions D1 to D5 of
  [advisor-brief-1.md](advisor-brief-1.md);
- [skeptic-answer-1.md](skeptic-answer-1.md), on locked items L1 to L7 of
  [skeptic-brief-1.md](skeptic-brief-1.md).

Each decision below gives what was chosen, why, and what was rejected.

## R-1 Patch marker in `execute_pipeline_child` (FR-009)

- **Decision**: replace `if workflow.patched(f"e74-graph-child:{child_id}"):`
  with `workflow.deprecate_patch(f"e74-graph-child:{child_id}")`, then start
  GraphWorkflow unconditionally. Delete the else branch and the
  `from .feature import FeatureWorkflow` import. Keep the per-child id
  docstring: it explains the marker.
- **Rationale**: `benchmark_one_cell.json` carries the marker
  (`e74-graph-child:bench-replay-one-cell/...`), and closed Tidy/Benchmark
  parents are replayed whenever they are queried (`cli.py:753`,
  `TidyUpWorkflow.report`). `deprecate_patch` is Temporal's documented middle
  step: it accepts histories with or without the marker.
- **Proof**:
  1. `test_benchmark_replay.py` stays green on the unmodified history.
  2. A new test replays a copy of that history with the marker event
     stripped, on the new code.
  3. `test_pipeline_child_upgrade.py` is rewritten: a new parent starts a
     GraphWorkflow child, and replays with and without the marker.
- **Residual risk, accepted and recorded in the runbook**: a closed
  pre-cutover parent whose history started a *FeatureWorkflow* child has no
  marker. Querying it after the deploy (`sdlc tidyup report`, benchmark
  status) fails with a nondeterminism error: the child type differs. This is
  the same class of loss as Q1, so it is accepted.
- **Removal**: `deprecate_patch` stays as a standing item for as long as any
  parent history in the store may be queried. It gets no removal date.
- **Rejected**:
  - dropping the call outright: it relies on unverified SDK tolerance, and
    the skeptic predicts TMPRL1100 on `benchmark_one_cell`;
  - keeping `patched()` with a raising else branch: the raise is itself a
    command difference.

## R-2 Legacy closed rows (FR-004, Q1 = A)

- **Decision**: add a new field, `FleetSnapshot.closed_legacy: list[LegacyRun]`,
  with `LegacyRun(run_id, status, start_time, close_time)` taken from the
  visibility row. The steps:
  1. `_scan_closed` returns a `ClosedRef(id, type, status, start_time,
     close_time)` instead of `(id, type)`. It reads each field with
     `getattr(..., None)`, so test fakes keep working.
  2. `fetch_fleet` partitions on `type == "FeatureWorkflow"` **exactly**.
     Rows with type `None` (fakes, old servers) stay on the queried path.
  3. Legacy ids are taken out before the gather, so no handle is created
     and no query is sent. They never enter `graph_closed`.
  4. The open-id dedupe applies to legacy rows too.
- **Frontend** (`http.ts`):
  - `closed_legacy ?? []` keeps an older payload parsing;
  - the new `mapLegacy` maps a row to a `Run` with title
    "legacy run, summary unavailable";
  - status: `COMPLETED` maps to `done` and every other close status to
    `failed`;
  - the row has no cost, roles or marks.
- **`GET /runs/{id}`**: it also searches `closed_legacy`, so a legacy id
  returns its `LegacyRun` instead of a 404.
- **`/api/fleet/summary`**: legacy rows are left out on purpose. Its rows are
  graph facts, and `unreadable` means "tried and failed". A one-line comment
  in `fleet_summary.py` records this.
- **Rejected**:
  - synthesizing a `RunSummary`, the skeptic's L1 sketch: it fabricates cost,
    mode and outcome, and an outcome that does not start with `deployed:`
    renders as failed;
  - reusing `errors`: it breaks SC-005.

## R-3 Query paths that can reach a closed FeatureWorkflow by id (FR-008)

These are not on the fleet tick, but a stale tab, the operator or the CLI
can still reach them:
- `transport.fetch_pending` (`transport.py:156-167`), used by dashboard
  `/answer` and `/decide`, the operator's `_reply`, and CLI
  approve/reject/revise/answer;
- `cmd_status` (`cli.py:875`).

- **Decision**: on a query failure, check `describe().workflow_type`. When it
  is `FeatureWorkflow`, raise a typed `LegacyRunError`. Each surface maps it:
  - dashboard: HTTP **410 Gone** with
    "legacy FeatureWorkflow run; it can no longer be queried";
  - CLI: that message and exit 1;
  - operator: the same message as a tool error.

  Any other failure propagates as it does today.
- **Rationale**: the happy path costs no extra RPC. Without this, a legacy id
  produces an HTTP 500 or a traceback.
- **Rejected**: `describe()` before every query, since it adds an RPC to
  every reply.
- **Deferred**: caching non-graph `RunSource` in `run_graph._source`. The
  `describe()` call is a server RPC that needs no worker, so it is not
  broken, only repeated. It goes to a follow-up card.

## R-4 Histories and goldens (FR-010, FR-011)

- **Decision**: re-capture all 18 `SCENARIOS` with `GRAPH_STARTER`, through
  the existing capture-twice rule and `write_fixtures`. A new
  `tests/replay/test_capture_graph.py` runs behind the same
  `SDLC_CAPTURE_HISTORIES=1` switch. The capture writes both
  `histories/<name>.json` and `golden/<name>.json`.
- **Acceptance**:
  - in `git diff tests/replay/golden/`, only the `workflow` field
    (`FeatureWorkflow` to `GraphWorkflow`) and `source_commit` change;
  - `commands`, `close` and `trace` must be byte-identical, and any other
    hunk is a STOP;
  - the diff is saved as `golden-rebaseline.diff` in this directory and
    attached to the PR.
- **`research_retain_grounded`**: re-captured with `GRAPH_STARTER` behind
  its own `SDLC_CAPTURE_RESEARCH_RETAIN` switch. The test asserts
  `workflow == "GraphWorkflow"` and keeps all three page-file rows.
- **Replay test**: `test_feature_replay.py` becomes `test_graph_replay.py`.
  It replays every scenario history with GraphWorkflow, Deployment and Crew
  registered. `replayer()` moves to `harness.py` first.
- **Chaos skew**: `test_graph_golden_chaos.py:61-70` filters activities that
  the old histories lacked. With paired re-captures the filter becomes
  unnecessary, so it is removed and the test asserts equality outright.
- **Why not the advisor's "leave goldens byte-identical"**: the brief asks
  for a re-baseline "from GraphWorkflow with the diff attached". Without
  re-captured histories, GraphWorkflow would also keep only one replay
  history.
- **Rejected**: deleting histories, since eight test files would fail.

## R-5 Durability and parity tests that compare against Feature runs

- **`durability/test_inflight_resume.py`**: point it at the re-captured
  `greenfield_happy` and register GraphWorkflow.
- **`durability/test_priced_usage_parity.py`**: *before* the re-capture,
  extract the recorded `price_usage` tuples from the current FeatureWorkflow
  `greenfield_happy` into `tests/durability/fixtures/priced_usage_pre_e74.json`,
  and assert the GraphWorkflow capture against them. This keeps the
  cross-time guarantee: a same-tree comparison would be tautological.
- **`test_graph_golden.py:112` memo_parity**: before deletion, pin the
  FeatureWorkflow memo keys into a constant. Then assert the GraphWorkflow
  keys against the constant and drop the Feature leg.

## R-6 Architecture/plan `step()` removal (FR-007)

1. Delete `step()` in `stages/architecture/step.py:279` and
   `stages/plan/step.py:174`.
2. Delete `_StageModule`, `"step"` in `__all__` and the `__getattr__` branch
   in both stage `__init__.py`.
3. Rewrite `ARCH-1.x` / `PLAN-1.x` in `architecture.md` / `plan.md` in terms
   of `prepare`/`produce`/`finish` and the graph nodes, in the same diff.
   Per AGENTS.md, this is done in the primary checkout.
4. Rewrite `test_*_slice_contract.py` and `test_*_step_split.py` (the judge
   error case) against the split functions, keeping the clause markers.

- **Verification**: `scripts/check_clauses.py` passes.

## R-7 Calibration pins (C2)

- **Decision**: extend `test_gate_requires_calibration.py`,
  `test_soft_gate_auto_approval.py` and `tests/calibration/test_calibration_plumbing.py:188` to
  pin `graph_nodes/gate.py`, plus the `resolved_model` hand-off in
  `graph_nodes/precode.py`.
- **Order**: this lands **before** `step()` is deleted, so the live path is
  pinned before the old one goes.
- `_revisable_stage` is kept (FR-006). The proposal to delete it goes to
  GATE 2.

## R-8 Gate procedure (FR-001, FR-002, Q2 = A)

- **Decision**: [contracts/gate-runbook.md](contracts/gate-runbook.md). The
  queries carry explicit `--address` and `--namespace` values (from the
  worker's `TEMPORAL_HOST` in `docker-compose.yml`). Recorded alongside them,
  so an empty or wrong store cannot pass:
  - `temporal workflow count` on the namespace;
  - `temporal schedule list`.

  Any schedule that targets `FeatureWorkflow`, `TidyUpWorkflow` or
  `BenchmarkWorkflow` blocks the gate like a Running row does.
- **Placement**:
  - **Gate run 1** is a blocking task before the first deletion commit.
  - **Gate run 2** is immediately before the worker restart
    (`docker compose pull worker && docker compose up -d worker`), and
    before pushing any `v*` tag: `release.yml` publishes the image on tags,
    and compose defaults `KROKER_IMAGE_TAG` to `latest`.
  - No deploy happens on merge (checked: `ci.yml` and `docs.yml` do not
    deploy).
- **Not done during planning**: per the orchestrator, the queries are
  recorded as tasks only.

## R-9 PR split (D5)

**PR-1** is additive and safe while FeatureWorkflow is registered. It needs
no gate:
- R-2 legacy rows and the frontend change;
- R-3 legacy errors;
- R-7 pins;
- `replayer()` move;
- the six helper-import repoints;
- R-5 pinned constants (memo keys, priced tuples).

PR-1 changes closed Feature rows from "summary shown" to "legacy row" while
the type is still registered. This is accepted under Q1 = A and stated in
the PR.

**PR-2** starts only after gate run 1 is empty:
- the inbox open-type removal (advisor: removing it earlier hides pending
  gates on runs still draining);
- R-1;
- R-4 re-captures;
- deleting `feature.py`, the worker registration and the composites (R-6);
- the test classification, executed;
- AGENTS.md and docs;
- closing the card.

**Deploy** happens only after gate run 2.

- **Rejected**: one PR. The fleet and fixture work is worth reviewing on its
  own, and splitting keeps the deletion diff mechanical.

## R-10 Roll-forward recovery (L7)

Recorded in the runbook:
- a nondeterminism error in a Tidy/Benchmark parent: roll forward a fix to
  the `deprecate_patch` path;
- a FeatureWorkflow found Running after the restart:
  `temporal workflow terminate --workflow-id <id> --reason "020 post-cutover cleanup"`,
  then re-submit through `sdlc start`.

No path brings FeatureWorkflow back.
