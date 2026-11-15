# Skeptic pressure-test — round 024

## L1 — "Routing off = byte-identical" and replay claim H6

- **Verdict:** `holds` (with a workflow-input serialization caveat)
- **Evidence:**
  - Verified empirically against installed `temporalio==1.31.0`: replaying a history recorded with no `task_queue` on `workflow.execute_activity(...)` against a modified workflow passing `task_queue="q2"` via `Replayer(..., raise_on_replay_failure=True)` succeeds with `replay_failure=None`. Temporal's `sdk-core` does not enforce `task_queue` equality during replay determinism matching.
  - `tests/replay/projection.py:24-38` (`command_projection`) records only `activity:<name>`, `child:<name>`, `timer`, and `cancel_requested`; it omits `task_queue` and serialized inputs.
  - `tests/replay/test_graph_golden.py:34-56` (`MEMO_PARITY_KEYS`) hashes `IdeaBrief`, not `PipelineConfig`, and `tests/replay/test_graph_replay.py:25-29` asserts `replay_failure is None`.
  - **Caveat:** Adding a new field (e.g. `harness_task_queue: str | None = None`) to `PipelineConfig` or `CrewTaskInput` (`src/sdlc/workflows/crew.py:66-95`) causes Pydantic's default `model_dump_json()` to emit `"harness_task_queue": null` in `WORKFLOW_EXECUTION_STARTED` and child-workflow inputs even when routing is off — so raw history JSON is not literally byte-identical unless `None` is excluded.
- **Smallest fix:** Keep the routing field optional with default `None` and omit it when `None` (`exclude_none=True` or only passing when routing is on), and state in P-FR-011 that "byte-identical" applies to golden projections and `Replayer` determinism.

## L2 — Shared session-store volume

- **Verdict:** `breaks` (for scaled/multi-container harness replicas sharing a session-store volume)
- **Evidence:**
  - `src/sdlc/harness/base.py:74` passes `HOME` into the harness subprocess environment.
  - `src/sdlc/harness/claude_code.py:5,73-74` resumes via `--resume <session_id>` (scoped to cwd/worktree under `$HOME/.claude/projects/...`, alongside shared `$HOME/.claude.json` and history state).
  - `src/sdlc/harness/opencode.py:6,63-64` resumes via `-s <session_id>` (stored under `$HOME/.local/share/opencode/`, SQLite/file store).
  - `docker-compose.override.example.yml:17,21-26` bind-mounts `~/.local/share/opencode/auth.json:/root/.local/share/opencode/auth.json:ro` and documents that `opencode` replaces `~/.cache/opencode/models.json` via write-tmp + rename (`EBUSY` on single-file bind mounts).
  - **Failures:** (1) Mounting a shared named volume at `/root/.local/share/opencode` collides with the nested `:ro` `auth.json` bind mount (`docker-compose.override.example.yml:17`), and sharing OpenCode's SQLite/file store across multiple containers risks `SQLITE_BUSY` or WAL corruption across container PID/mount namespaces; (2) sharing `/root/.claude` across concurrent `claude` processes in multiple containers exposes non-session-scoped files (`~/.claude.json`) to uncoordinated concurrent writes/corruption.
- **Smallest fix:** Forbid `replicas > 1` on the harness service until AP-2.6 (worker-specific queues) lands — scale concurrency via the in-container cap (`P-FR-004`) on a single harness container instead. If a volume is mounted for single-container restart persistence, mount `/root/.claude` and `/root/.local/share/opencode/storage` (not `/root/.local/share/opencode`, which shadows `auth.json`).

## L3 — Single-host shared-filesystem assumption

- **Verdict:** `breaks` (`worktree_janitor` dual-process race) / `risk` (git lock contention on shared `repo_url`)
- **Evidence:**
  - `src/sdlc/worker.py:313` unconditionally spawns `janitor = asyncio.create_task(worktree_janitor(client))` in `main()`.
  - `src/sdlc/vcs/janitor.py:34-70` (`sweep_once` -> `cleanup_run_dir` at line 62) scans `_worktrees_root()` (`src/sdlc/vcs/worktree.py:15-18`) and executes `git worktree remove -f` and `git worktree prune` (`src/sdlc/vcs/worktree.py:68-69,253-288`).
  - With `core` and `harness` both running `worker.main()`, **both** processes run `worktree_janitor`: `core` violates the capability split by mutating worktrees/git, and concurrent `core` + `harness` (or 2+ `harness`) janitors race on `cleanup_run_dir` and `.git/worktrees/` / `packed-refs.lock`.
  - Additionally, `measure_code_axis` (`src/sdlc/benchmarks/axis.py:222,236`) creates detached worktrees on `inp.repo_url` and deletes the directory via `shutil.rmtree` without running `git worktree prune`, leaking registrations that contend with concurrent `git worktree` calls on the same case repo.
- **Smallest fix:** Gate `worktree_janitor` in `src/sdlc/worker.py:313` to run only in `mode in ("all", "harness")` (never `core`), guard `sweep_once` (`src/sdlc/vcs/janitor.py:34`) with an advisory `flock` on `<worktrees_root>/.janitor.lock`, and add `git worktree prune` in `measure_code_axis`'s `finally` block (`src/sdlc/benchmarks/axis.py:235-236`).

## L4 — Harness class rule A.1(a–c)

- **Verdict:** `breaks` (misclassifies `measure_code_axis` and leaves live-worktree readers on `core`)
- **Evidence:**
  - Rule A.1(a–c) (`spec.md:22`) includes activities that (a) spawn a coding CLI, (b) execute target repo code, or (c) create, mutate, or remove a run's worktree or branches.
  - **Misclassified / missed:**
    1. `measure_code_axis` (`src/sdlc/benchmarks/axis.py:198-236`) runs `git worktree add --detach` and `shutil.rmtree` — it **must** be harness-class under A.1(c), not treated as core reporting.
    2. `check_test_drift` (`src/sdlc/vcs/git.py:180`, called at `src/sdlc/stages/code/step.py:711`) mutates git index bits (`skip-worktree`/`assume-unchanged`) and is not even registered in `src/sdlc/worker.py`.
    3. `worktree_janitor` (`src/sdlc/worker.py:313`) mutates worktrees outside `@activity.defn`, bypassing the rule.
    4. Live-worktree readers — `get_task_diff` (`src/sdlc/vcs/git.py:97`), `paths_exist` (`src/sdlc/validators/activities.py:18`), and `TemporalDurability` agents with read-only repo tools (`spec.md:147`) — are classified as **core** by A.1(a–c).
  - **What fails concurrently:** A `core` activity reading a live worktree during a `harness` turn hits torn file reads, `.git/index.lock` failures on `git diff`, or `FileNotFoundError` if `core` does not share the exact worktree mount path.
- **Smallest fix:** Expand A.1(c) to "creates, mutates, removes, **or reads a run's live worktree**" (routing `get_task_diff`, `paths_exist`, `measure_code_axis`, and `check_test_drift` to the harness queue, and registering `check_test_drift` in `worker.py`), leaving only commit-pinned `read_committed_bytes` (`src/sdlc/vcs/git.py:253`) on `core`.

## L5 — SC-003 / SC-004 evidence on fakes

- **Verdict:** `breaks` (proof is hollow on `src/sdlc/demo/fakes.py`)
- **Evidence:**
  - `src/sdlc/demo/fakes.py:154-165` (`run_coding_task`) is an `async def` returning a static `HarnessRunResult` with zero `await asyncio.sleep(...)`, zero subprocesses, and zero blocking (`src/sdlc/demo/fakes.py:5`: *"None of them opens a file, spawns a process or reaches the network"*).
  - Because fake turns complete in < 1 ms, 5 concurrent runs may never hold `cap=2` saturated simultaneously, and even an uncapped **single-pool** worker would trivially pass SC-004's `< 5s` p95 schedule-to-start latency.
- **Smallest fix:** In the SC-003/SC-004 temporal load test (under `tests/`), use a scripted fake `run_coding_task` / `run_crew_turn` with an `asyncio.Event` barrier that holds 2 harness slots open for >= 1.0 s while turns 3–5 are queued, schedule a core model-call activity while those 2 slots are held, and assert from history timestamps that `max_concurrent == 2`, `queued_harness_wait > 0.5s`, and `core_schedule_to_start < 1.0s`.

## L6 — Other single-host bottlenecks for 5 concurrent benchmark runs

- **Verdict:** `risk`
- **Evidence:**
  1. **Crew wall-clock vs `cap < 5` (Q3):** `src/sdlc/stages/code/step.py:305` sets `execution_timeout = wall_clock_s + 600`; with 5 runs and `cap=2`, runs 3–5 burn their `5400s` budget in the queue and risk `EXIT_DEADLINE` on real runs.
  2. **Temporal dev-server SQLite:** `docker-compose.yml:18` uses `temporal server start-dev --db-filename /tmp/state/temporal.db` (SQLite), risking write-lock contention across 5 `BenchmarkWorkflow`s + children + heartbeats + `worktree_janitor` `list_workflows`.
  3. **Hindsight & provider rate limits:** `docker-compose.yml:23-36` runs one Hindsight instance (`8888`) on `.pg0`; 5 concurrent `retain`/`reflect`/`recall_snapshot` loops (`src/sdlc/memory/activities.py`) plus 5 core proposers + `cap` harness CLIs share one set of provider RPM/TPM quotas.
  4. **Hardcoded ports / board SQLite:** Concurrent same-case `run_test_suite` / `grade_oracle` / `smoke_check` runs bind-colliding on fixed localhost ports will fail (`Address already in use`); `runs/board.sqlite3` (`src/sdlc/board/schema.py:154,171-172`) uses WAL + 5s `busy_timeout` but still serializes all board writes.
- **Smallest fix:** Document in R025's runbook: size `cap >= concurrent_crew_runs` for paid runs, use Postgres-backed Temporal instead of `start-dev` SQLite for 5+ real runs, stagger starts/bound provider RPM, and randomize localhost ports in case test/oracle suites.
