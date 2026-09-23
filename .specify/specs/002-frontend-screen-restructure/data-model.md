# Data model: Frontend restructure — by-screen features, design-system port, board screen

**Plan**: [plan.md](plan.md) · decisions cited as R-n are in [research.md](research.md).

Groups A and B introduce no data. This file covers the run-wire delta (G4) and the board screen's wire types, view models and state (group C).

## 1. Run wire delta (backend → SPA)

| Model | Field | Type | Source | Absent means |
|---|---|---|---|---|
| `RunState` (`core/models.py:510`) | `project_key` | `str \| None = None` | `RunHost._snapshot_run_state`: `self._cfg.project_key` | `_cfg` not yet set |
| `RunSummary` (`core/models.py:477`) | `project_key` | `str \| None = None` | `build_run_summary(project_key=cfg.project_key)` from `RunHost._retro` | summary built before the field existed and not re-derived |
| frontend `Run` (`api/types.ts:19`) | `projectKey` | `string \| null` (**required**) | `mapRun`/`mapClosed`: `s.project_key ?? null` | → Board banner "no board for this run" |

Validation: the frontend never substitutes `"default"` (FR-020a). `startRun`'s optimistic fallback literal (`api/http.ts:210-215`) sets `projectKey: null`.

## 2. Board wire types (`features/board/board.types.ts`)

Mirror of `src/sdlc/board/models.py` and `src/sdlc/board/api.py`, read-only subset. Datetimes arrive as ISO strings.

- **`TaskStatus`**: `'pending' | 'in_progress' | 'done' | 'failed' | 'blocked' | 'quarantined'`.
- **`BoardTaskWire`**: `project`, `plan_version: number`, `task_id`, `run_id`, `status: TaskStatus`, `authoritative_status: TaskStatus`, `row_version: number`, `fix_attempts: number`, `error: string | null`, `branch: string | null`, `updated_at: string`. (`diverged` is a Python `@property`, not serialized — computed client-side as `status !== authoritative_status`.)
- **`TaskEvidenceWire`**: `id`, `project`, `plan_version`, `task_id`, `run_id`, `kind: string` (`qa | review | deep_review`), `sha256`, `uri`, `created_at` (`models.py:75-84`).
- **`TaskDetailWire`**: `{ task: BoardTaskWire; evidence: TaskEvidenceWire[] }`.
- **`ArtifactVersionWire`**: `id: number`, `project`, `key`, `n: number`, `run_id`, `sha256`, `uri`, `supersedes: number | null`, `created_at` (`models.py:37-46`).
- **`BoardArtifactWire`**: `project`, `key`, `status`, `current_version: number | null`.
- **`ProjectDetailWire`**: `{ key, repo, artifacts: BoardArtifactWire[], stats: BoardStatsWire }`.
- **`BoardEventWire`**: `id`, `project`, `subject`, `actor`, `authority`, `from_status: string | null`, `to_status: string | null`, `at: string`, `detail: string`.

## 3. Board view models (`features/board/board.adapter.ts`, pure)

All outputs are display primitives — literals constructible without importing `dashboard/` (the cardinal rule holds because the adapter lives in the dashboard).

| Function | In | Out (ported component props) |
|---|---|---|
| `toTaskRow(task)` | `BoardTaskWire` | `{ key: task_id, label: task_id (G5a), status: { kind: status, pulsing: status === 'in_progress' || status === 'blocked' } (STATUS_PIP-2 as adopted in B2: "the `running` and `blocked` states are the only marks that pulse", and the same doc's kind list pairs `running`/`in_progress` and `blocked`/`waiting` as one state each — so `in_progress` and `blocked` pulse, nothing else), fixAttempts, hasError: error !== null, diverged }` → ListRow slots + StatusTag props |
| `toTaskDetail(detail)` | `TaskDetailWire` | `DetailPane` props `{ eyebrow: 'Task', title: task_id, fields: DetailField[] }` (status, authoritative status, fix attempts, branch, error, updated) + evidence section items (G5e) |
| `toTimeline(events)` | `BoardEventWire[]` | `TimelineItem[]`: `{ id, to: to_status ?? '—', from: from_status ?? undefined, kind: to_status ?? undefined, detail, at, actor }`, oldest first |
| `toVersionRows(versions, runId)` | `ArtifactVersionWire[]` per key | rows for versions with `run_id === runId` only (G5d), newest first |
| `toCounters(tasks)` | `BoardTaskWire[]` | `Stat` props list, labelled "this run" (G5c): count per `TaskStatus`, total fix attempts, tasks with error, diverged tasks |
| `pickPlanVersion(planVersions, runId)` | `ArtifactVersionWire[]` for key `plan` | newest `id` with `run_id === runId`, else `undefined` (FR-021a) |

Absent values render as the ported components' em dash (DETAIL_PANE-2, Stat) — the adapter passes `null`, never a placeholder string.

## 4. Board state (`features/board/board.store.ts`)

State:

- `phase`: `'idle' | 'loading' | 'ready' | 'empty' | 'unavailable'`
- `reason`: `'no_project' | 'not_found' | null` (only when `unavailable`)
- `connectionLost: boolean` (transient failures, FR-023a)
- `tasks`, `versions`, `planVersion: number | undefined`
- `selectedTaskId: string | null`, `selectedDetail`, `selectedEvents`

Transitions:

```text
idle --start(run)--> run.projectKey null ----------------------> unavailable(no_project)
idle --start(run)--> loading
loading --404 on step 1 (project) or step 3 (no current plan)---> unavailable(not_found)
loading --404 on step 2 (no plan artifact)-----------------------> continue: planVersion = undefined, go to step 3
loading --404 on step 4 for one key------------------------------> continue: skip that key
loading --non-404 failure on any step----------------------------> loading, connectionLost = true; the whole load retries on the poll cadence
loading --ok, tasks.length === 0---------------------------------> empty          (edge case: empty-but-reachable)
loading --ok, tasks.length > 0-----------------------------------> ready
ready|empty --poll failure (non-404)-----------------------------> same phase, connectionLost = true (data kept)
ready|empty --poll 404 on step 3---------------------------------> unavailable(not_found)
ready|empty --poll ok--------------------------------------------> ready|empty by count, connectionLost = false
any --stop()------------------------------------------------------> idle (poll stopped, selection cleared)
ready --select(taskId)--> fetch detail + events (404: selection cleared; non-404: connectionLost, keep prior selection data)
ready --poll ok, selected task's row_version changed-------------> re-fetch selected detail + events in the background
```

The initial load (steps 1–4) runs inside the same `startPoll` loop as the task poll until it first succeeds, so a transient failure during `loading` retries with the poll's backoff instead of leaving an unhandled rejection. After the first success, only step 3 polls (plus the selected-task refresh above).

Invariants: `stop()` is called from the Board panel's `onBeforeUnmount` (FR-023); a 404 is the only permanent failure (R-3); the store never writes to the board (FR-024).

## 5. Run-page tab state (`features/run/RunView.vue`)

- Tabs: `graph` (default), `board` (disabled when no `#board` slot is supplied — R-13), `gates` (disabled, G7), `cost` (disabled, G7) — `TabItem[]` for the ported TabBar.
- Board slot props: `{ runId: string; projectKey: string | null }`, rendered only once the run is loaded (R-13 rule 2).
- Run not found: when the fleet store has fetched at least once (`lastFetched !== null`) and `getOrLoad(id)` is still `undefined`, the Board panel shows a "run not found" banner instead of "loading run…" (a bad or pruned link must not hang).
- Active tab = `tab` route prop if it names an enabled tab, else `graph` (R-4). Selecting Graph clears `?tab`.
- Header (title + StageDots) renders above the TabBar on every tab (FR-018 as amended).
