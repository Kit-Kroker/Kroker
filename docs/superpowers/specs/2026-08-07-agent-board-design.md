# Agent Board — persistent artifact & task state with a query API

**Date:** 2026-08-07
**Status:** approved design, ready for planning

## Problem

The pipeline's typed stage artifacts — `ClarifiedRequirements`, `ArchitectureSpec`,
`ImplementationPlan`, `DevTask[]` — are never written to disk. Following `arch`
through `workflows/feature.py:2028` and `plan` through `feature.py:2071`, a stage
output reaches exactly five destinations:

| Destination | What survives |
|---|---|
| Temporal history | the full object (system of record, replayable) |
| Next stage | in-memory variable (`arch.model_dump_json()` → planner prompt) |
| Memoization cache | full JSON at `%TEMP%/sdlc/memo_cache/<sha256>.json`, keyed by content hash |
| Memory bank | one line: `f"architect: {arch.overview}"` (`feature.py:2043`) |
| `RunSummary` | a `StageOutcome` row — stage/role/outcome/duration/cost. No content. |

Answering "what design did the architect propose in run 019fb994?" therefore
requires replaying Temporal history or reverse-engineering a cache hash. There is
no `runs/<run_id>/architecture.json`.

Three things are missing, and only these three:

1. **Artifact content is unaddressable.** Nothing to link a score or a decision to.
2. **No entity with a lifecycle.** `BenchmarkRecord` (`benchmarks/models.py:108`) is
   append-only measurement emitted at stage end. There is no "task T03 is
   `in_progress` / `blocked`" that can be queried mid-flight.
3. **No query surface.** `evidence.py:53` scans `runs/*/summary.json` as an offline
   batch. There is no database anywhere in the repo, and `interfaces/dashboard`
   is frontend-only — `api/http.ts` implements the declared `DashboardApi` as
   `notWired`.

Measurement itself is *not* missing. `BenchmarkRecord` already carries `run_id`,
`stage`, `task_id`, `attempt`, `role`, `harness`, `model`, `quality`, `cost`,
`speed`, `waste`, `outcome`, `fix_attempts`, `error`, and `WasteBag` counts
`failed_commands`, `denials`, `escalations`, `rewrite_churn`, `file_rereads`.
`benchmarks/` is 3,327 lines of working rollup on top of it. This spec does not
touch any of that.

## Goals

- Persist project artifacts durably, versioned, with lineage across runs.
- Give tasks a real status lifecycle that is queryable while a run is in flight.
- Record every state change with actor and timestamp — the change log.
- Expose a read API for agents, the dashboard, and future correlation with
  `benchmarks/`.
- Let agents transition task status (claim, block, report error) safely under
  concurrency.

## Non-goals

- **Not rebuilding scoring.** Quality/cost/speed rollup stays in `benchmarks/`.
- **Not an LLM orchestrator.** Temporal remains the dispatcher (see "Deferred").
- **Not the operator control surface.** The unwired `DashboardApi`
  (`listRuns`, `answerClarify`, `decideGate`, …) is a different concern; the
  board API is additive and may share the FastAPI app in a later spec.
- **Not multi-tenant auth.** Single-operator deployment; API is unauthenticated
  on the internal network, consistent with the existing dashboard assumption.

## Decisions taken

| Decision | Choice | Consequence |
|---|---|---|
| First scope | persistence + query API together | one spec, one deliverable |
| Board scope | project-level, versioned | needs real project identity and artifact lineage |
| Write path | workflow writes content; agents write status | needs optimistic concurrency and a state machine |
| Backend | SQLite metadata + existing claim-check store for blobs | zero new infra; transactions from stdlib |

### Why SQLite

Agent status writes demand transactions and write serialization, which a
files-only board cannot provide. SQLite supplies both from the standard library
— no container, no volume beyond the `worker-runs` mount that already exists.
Rejected alternatives:

- **Git-backed board in the target repo.** Most Confluence-like (diffable,
  reviewable, free history), but concurrency becomes merge conflicts, every task
  claim is a commit, and cross-project statistics require cloning and scanning.
  Good fit for content, bad fit for state.
- **Extend Hindsight.** Already running and project-scoped via `project_bank`,
  but it is a semantic recall system: no state machine, no compare-and-swap, no
  relational queries. Wrong tool.

SQLite over a Docker volume is correct for one worker container. Multiple workers
would require Postgres — the same threshold at which `server start-dev`
(`docker-compose.yml:12`) must also be replaced. `BoardStore` is a class behind
which that swap happens without touching callers.

## Architecture

```
src/sdlc/board/
├── models.py      # Pydantic: Project, BoardArtifact, ArtifactVersion,
│                  #   BoardTask, TaskEvidence, BoardEvent
│                  #   + ArtifactStatus / TaskStatus / Authority enums
├── schema.py      # SQLite DDL, apply_schema(conn) — idempotent
├── store.py       # BoardStore: ALL SQL, transactions, state-machine
│                  #   enforcement, optimistic concurrency
└── activities.py  # thin @activity.defn wrappers

interfaces/dashboard/api/    # thin FastAPI app: routes -> BoardStore
```

`store.py` + `activities.py` follow the `RecordStore` idiom
(`benchmarks/recorder.py:55`): a plain class holding all I/O, plus a thin
`@activity.defn` wrapper, with non-deterministic I/O confined to activities.

**Two entry points, one enforcement point.** The workflow writes through
`board/activities.py` → `BoardStore` **in-process, no HTTP**, so the pipeline
never depends on a web service being up. Agents write through the FastAPI app →
the *same* `BoardStore`. Every transition from either direction is validated by
the state machine in `store.py`. Exactly one place can move a status.

**Storage splits on the mutable/immutable line:**

| | Where | Why |
|---|---|---|
| Artifact bodies | `LocalFileStore.put()` → `runs/<run_id>/artifacts/<key>-v<n>.json` | already sha256, immutable, claim-check seam exists |
| Graph, status, events | SQLite at `$SDLC_BOARD_DB`, default `runs/board.sqlite3` | needs transactions; inside `worker-runs` so it survives rebuilds |

`_SUBDIRS` (`artifacts/store.py:19`) already routes unknown kinds to their own
subdirectory, so this requires one table entry, not a new mechanism.

SQLite opens in WAL mode with `busy_timeout` set; writes use `BEGIN IMMEDIATE`.

### Project identity

The only project-scoped value today is `MemoryConfig.project_bank =
"project:default"` (`models.py:822`), which belongs to Hindsight. Add a distinct
`project_key: str` to `PipelineConfig`. The board and the memory bank are
different stores and must not share an identifier by accident.

## Data model

### Two classes of artifact

**Project artifacts** — versioned, long-lived: `requirements`
(`ClarifiedRequirements`), `architecture` (`ArchitectureSpec`), `plan`
(`ImplementationPlan`). Each run appends a version and moves the pointer.

**Task evidence** — per-run, immutable, attached to a task, never versioned at
project level: `QAReport`, `ReviewReport`, `DeepReviewReport` from `TaskResult`
(`models.py:354`). These are observations about one attempt, not evolving
documents.

### Schema

```sql
project(key PK, repo, created_at)

artifact(project, key, current_version, status, PK(project, key))
    -- key ∈ {requirements, architecture, plan}
    -- status: proposed → current → superseded | rejected

artifact_version(id PK, project, key, n, run_id, sha256, uri,
                 supersedes, created_at)
    -- uri points into the claim-check store; sha256 from LocalFileStore.put

task(project, plan_version, task_id, run_id,
     status, authoritative_status, row_version,
     fix_attempts, error, branch, updated_at,
     PK(project, plan_version, task_id))
    -- status:               pending → in_progress → done|failed|blocked|quarantined
    -- authoritative_status: same domain, workflow writes only

task_evidence(id PK, project, plan_version, task_id, run_id, kind, sha256, uri)
    -- kind ∈ {qa, review, deep_review}

event(id PK, project, subject, actor, authority,
      from_status, to_status, at, detail)     -- append-only, never updated
    -- subject: "artifact:<key>" | "task:<plan_version>:<task_id>"
```

`plan_version` throughout is the `artifact_version.id` of the `plan` artifact —
a surrogate key, not the human-facing `n`. Tasks therefore bind to one exact
stored plan document, not to an ordinal that could be reinterpreted.

`rejected` exists on `artifact.status` because a gate can reject a stage —
`feature.py` returns `"rejected:architecture"`.

### Task identity is scoped to a plan version

`DevTask.id` (`models.py:295`) is planner-assigned per run, so `T01` in plan v2
is not necessarily `T01` in v1. Keying tasks by `(project, plan_version,
task_id)` keeps history queryable without asserting that two unrelated tasks are
the same task. The board's default view shows tasks of the current plan version;
earlier tasks stay queryable under their own plan version.

### The two-status split — the audit invariant

Letting agents write status makes the board a second source of truth. The split
contains that:

- `authoritative_status` — written **only** by workflow activities, from real
  stage outcomes.
- `status` — the live view; either writer may move it.
- Every write appends an `event` carrying `actor` (`workflow:<run_id>` or
  `agent:<name>`) and `authority` (`authoritative` | `observational`).

**Statistics and scoring read `authoritative_status` only.** An agent that
crashes mid-claim, double-claims, or reports optimistically corrupts the live
view and nothing else. Temporal replay still reconstructs the run, preserving
the invariant stated at `ARCHITECTURE.md:409`. Divergence between the two
columns is itself a signal worth surfacing in `/stats`.

### Concurrency

`row_version` on `task`, incremented per write. Agent writes send
`If-Match: <row_version>`; mismatch returns `409`. With WAL and `BEGIN
IMMEDIATE`, two agents racing to claim `T03` yield one winner and one `409`,
never two owners.

## API

### Agent writes — deliberately only these two

```
POST  /projects/{p}/tasks/{id}/claim      If-Match  → pending → in_progress
PATCH /projects/{p}/tasks/{id}            If-Match  → status + note
```

### Reads

```
GET /projects
GET /projects/{p}                                  → artifacts + task rollup
GET /projects/{p}/artifacts/{key}                  → version list w/ lineage
GET /projects/{p}/artifacts/{key}/versions/{n}     → metadata + content
GET /projects/{p}/tasks?status=&run_id=&plan=
GET /projects/{p}/tasks/{id}?plan=                 → + evidence refs
```

Task routes omitting `plan=` resolve against the project's **current** plan
version. Passing `plan=<artifact_version.id>` addresses a historical plan. The
same resolution applies to the two agent write routes, so an agent holding a
stale plan cannot silently claim a task on the current one.

```
GET /projects/{p}/events?since=&subject=           → the change log
GET /projects/{p}/stats                            → board-owned counters
```

### Workflow writes — activities, not HTTP

```python
publish_artifact_version(project, key, run_id, content_json) -> ArtifactRef
sync_plan_tasks(project, plan_version, tasks: list[DevTask]) -> int
set_task_authoritative(project, plan_version, task_id, status,
                       fix_attempts, error) -> None
attach_task_evidence(project, plan_version, task_id, run_id,
                     kind, content_json) -> ArtifactRef
```

`publish_artifact_version` is one transaction: `LocalFileStore.put()` the blob,
insert `artifact_version`, move `artifact.current_version`, mark the prior
version `superseded`, append an `event`.

### Content reads

`GET .../versions/{n}` resolves `uri` via `ref_to_path` and returns content
byte-capped, mirroring `DEEP_REVIEW_MAX_BYTES` (`artifacts/read.py:18`), with a
kind assertion in the manner of `load_session`.

**No scrub path, and that is defensible.** `read.py` scrubs transcripts because
harness sessions capture tool output. Proposer agents "emit schema-validated
artifacts and never touch tools" (`ARCHITECTURE.md:22`), so their output cannot
carry harness-captured secrets by construction.

## Boundary with `benchmarks/`

`/stats` exposes only what the board observes: transition counts, fix attempts,
error strings, time-in-status, current task distribution, and
`status`/`authoritative_status` divergence. Quality, cost, and speed rollup stays
in `benchmarks/`. The join key already exists — `BenchmarkRecord` carries
`run_id`, `stage`, and `task_id` — so a later spec can correlate the two.
Duplicating the rollup here would produce two scores that disagree.

## Wiring into the workflow

| Stage | Call |
|---|---|
| after `clarify` approved | `publish_artifact_version("requirements", …)` |
| after `architecture` approved (`feature.py:2033`) | `publish_artifact_version("architecture", …)` |
| after `plan` approved (`feature.py:2076`) | `publish_artifact_version("plan", …)` then `sync_plan_tasks(...)` |
| task start / end (`run_one`, `feature.py:2104`) | `set_task_authoritative(...)` |
| after QA / review / deep_review | `attach_task_evidence(...)` |

On a rejected gate, the version is written with `status="rejected"` and the
pointer is not moved — a rejected design is history worth keeping.

## Error handling

**Board writes from the workflow are retryable activities that must succeed.**
This deliberately differs from `capture_session` (`artifacts/capture.py:29`),
which is fail-closed on storage but never blocks delivery because "an
observability bug must not block delivery". The board is not observability —
agents read tasks from it. A permanently failed board write fails the activity
and surfaces to the workflow. Temporal's `RetryPolicy` absorbs transient
failures.

| Failure | Behaviour |
|---|---|
| SQLite locked | `busy_timeout` + Temporal retry |
| Invalid transition (either writer) | reject; `422` over HTTP; **no** `event` row — the log records real changes only |
| `If-Match` mismatch | `409`, agent re-reads and retries |
| Blob missing (pruned `runs/`) | `410 Gone`; version metadata and sha256 still returned from SQLite |
| DB file absent or new | `apply_schema` is idempotent, run at store construction |
| Unknown project / artifact key | `404` |
| Content exceeds cap | truncated with `truncated: true`, as `load_session` does |

## Testing

Tests are flat in `tests/` with opt-in markers (`slow`, `temporal`, `live`,
`docker`); the default run excludes them.

**Unit (default run):**
- State-machine matrix: every valid and invalid transition for both
  `ArtifactStatus` and `TaskStatus`.
- Version numbering and `supersedes` lineage across repeated publishes.
- `BoardStore` against a `tmp_path` SQLite file — round-trip of every entity.
- Two-status split: an observational write must not move
  `authoritative_status`.
- Optimistic concurrency: stale `row_version` is rejected.
- Concurrency: two threads claiming one task → exactly one success, one
  conflict.
- API via FastAPI `TestClient` — status codes for each row of the error table.

**Workflow (`-m temporal`):**
- A run against the existing fake harness produces the expected board rows:
  three artifact versions, task rows matching the plan, evidence attached.
- A rejected architecture gate leaves `status="rejected"` and the pointer
  unmoved.

## Dependencies

`fastapi` and `uvicorn` are **not** currently in `pyproject.toml` and must be
added. SQLite needs nothing — `sqlite3` is stdlib.

## Deferred: the agent orchestrator

The original proposal included replacing the pipeline with proposers plus an
agent that reads state and dispatches to harnesses. That is deferred, not
rejected, for reasons worth recording:

- **Replay dies.** LLM-driven control flow means re-running history no longer
  reproduces decisions.
- **Gates are workflow constructs.** `GatePolicy`, human approval,
  `TimeoutAction`, and `_check_budget` at serial boundaries would all need
  reimplementing, less reliably.
- **Benchmarking gets noisy.** Scheduler variance would layer on top of
  stage-agent variance, and the calibration apparatus assumes the harness is
  the variable.

The genuine insight underneath it — that externalizing state decouples the
pipeline from one linear workflow — is delivered by this spec. Temporal reads
the board and dispatches, yielding dynamic task graphs, resume, and re-entry
without surrendering determinism. Once the board exists, the orchestrator can be
built and *measured* against the workflow rather than adopted on faith.

## Open questions

None blocking implementation. Two to revisit after the board is in use:

1. Whether `/stats` should join `BenchmarkRecord` directly or stay disjoint from
   `benchmarks/`. Deliberately disjoint for now.
2. Retention for board rows. `retention.py` prunes harness transcripts; artifact
   versions currently accumulate without bound. Not urgent at present volume.
