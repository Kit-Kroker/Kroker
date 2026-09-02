# Agent board — persistent artifact & task state (`E-78`) → FR-1300…FR-1303

**Landed 2026-08-07.** Spec: `docs/superpowers/specs/2026-08-07-agent-board-design.md`.
Contracts: `src/sdlc/board/`. ADR-21.

> ⚠️ **Numbering correction.** Code comments introduced with this work label it
> `E-40` (`feature.py` `BOARD_ACT`, `models.py` `PipelineConfig.project_key`).
> **E-40 is already `Measurement` + `RepoTriage` contracts** (§10). The board is
> **E-78**; those comments are stale and should be corrected in place.

**Problem it closed.** Typed stage artifacts (`ClarifiedRequirements`,
`ArchitectureSpec`, `ImplementationPlan`, `DevTask[]`) reached only five
destinations — Temporal history, the next stage's prompt, a hash-keyed
memoization file, a one-line memory summary, and a `StageOutcome` row carrying
no content. Answering *"what design did run 019fb994 propose?"* required a
replay, and no task had a status anything could query mid-flight.

- [x] **FR-1300 — project-level artifact versioning.** `requirements`,
  `architecture`, `plan` versioned per project with `supersedes` lineage across
  runs; bodies in the claim-check store (`board_artifact` kind), graph in
  SQLite. A gate-rejected artifact is recorded as history with
  `status="rejected"` and does not move the pointer.
- [x] **FR-1301 — task lifecycle.** `pending → in_progress →
  done|failed|blocked|quarantined`, one state-machine table
  (`board/transitions.py`) shared by both writers. Tasks key off
  `(project, plan_version, task_id)` because `DevTask.id` is planner-assigned
  per run — `T01` in plan v2 need not be `T01` in v1.
- [x] **FR-1302 — append-only change log + board counters.** Every accepted
  transition writes one `event` row with actor and authority; rejected writes
  write none. `/stats` exposes only board-owned counters (transition counts,
  fix attempts, errors, time-in-status, `status`/`authoritative_status`
  divergence). **Deliberately disjoint from `benchmarks/`** — quality/cost/speed
  rollup stays there; duplicating it would yield two scores that disagree. The
  join key (`run_id`, `stage`, `task_id` on `BenchmarkRecord`) exists for a
  later spec.
- [x] **FR-1303 — dual write path with optimistic concurrency.** Workflow
  writes content through Temporal activities in-process (no HTTP dependency);
  agents write status through FastAPI with `If-Match: <row_version>`. Both
  reach one `BoardStore`, so exactly one place can move a status.

**Known gaps (not blocking, recorded rather than fixed).**

- ⚠️ **Publish dedupe is broader than retry-safety needs.**
  `publish_artifact_version` dedupes on `(project, key, sha256)` with no
  `run_id`, while `attach_task_evidence` correctly scopes to `(…, run_id, kind,
  sha256)`. Because `_cached_stage` memoization returns byte-identical
  artifacts for identical inputs, a re-run of the same idea leaves **no trace**
  — no version, no event, `run_id` still the first run's. Temporal
  re-execution is always same-run, so scoping the dedupe by `run_id` restores
  cross-run fidelity without losing idempotency.
- ⚠️ **`X-Actor` is self-asserted** — see OQ-11, now live.
- `/tasks?status=` filters live `status` while `/stats` counts
  `authoritative_status`. Intentional (an agent wants the live view to avoid
  claimed tasks), undocumented at the API surface.
- `tests/test_board_workflow.py` is the only place a workflow runs against a
  real board; the rest of the temporal suite registers no-op `BOARD_FAKES`.
  That test's worker does not register `notify`, so a future timing shift
  surfaces as a confusing unregistered-activity error rather than an assertion.

**Deferred: the agent orchestrator.** The originating idea was to replace the
pipeline with proposers plus an agent that reads board state and dispatches to
harnesses. Deferred, not rejected — it would trade replay determinism, gate
semantics (`GatePolicy`, `TimeoutAction`, `_check_budget` at serial
boundaries), and benchmark signal-to-noise for flexibility the board already
delivers. Temporal reading the board and dispatching yields dynamic task
graphs, resume, and re-entry without that cost. Once the board is in use the
orchestrator can be **measured** against the workflow rather than adopted on
faith. See ADR-21.
