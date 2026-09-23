# Contract: board client (SPA → existing board routes) and run wire

**Consumer**: `interfaces/dashboard/frontend/src/features/board/board.api.ts` · **Provider**: `src/sdlc/board/api.py` (unchanged) and `src/sdlc/dashboard` run wire (one additive field).

## Run wire (the only backend change, G4)

`FleetSnapshot.runs[]` (`RunState`) and `FleetSnapshot.closed[]` (`RunSummary`), served by `GET /api/inbox` and the `/api/events` SSE:

```json
{ "run_id": "feature-x", "title": "…", "project_key": "kroker" }
```

- `project_key`: string, or `null`/absent. Additive; no existing field changes.
- SPA mapping: `Run.projectKey = s.project_key ?? null`. `null` → Board tab banner; the SPA never guesses `"default"`.

## Board routes consumed (read-only; all exist on main)

Base path: `''` (same origin; dev server proxies `/projects` → `127.0.0.1:8500`). `{p}` = `Run.projectKey`, URL-encoded.

| Step | Request | Response | Used for |
|---|---|---|---|
| 1 | `GET /projects/{p}` | `ProjectDetail { key, repo, artifacts[], stats }` | artifact keys (G5d) |
| 2 | `GET /projects/{p}/artifacts/plan` | `ArtifactVersion[]` | plan version pin (FR-021a): newest `id` whose `run_id` = run |
| 3 | `GET /projects/{p}/tasks?run_id={run}[&plan={id}]` | `BoardTask[]` | task list + counters (G5a, G5c); polled |
| 4 | `GET /projects/{p}/artifacts/{key}` per key | `ArtifactVersion[]` | versions where `run_id` = run (G5d) |
| 5 | `GET /projects/{p}/tasks/{task_id}[?plan={id}]` | `TaskDetail { task, evidence[] }` | detail pane + evidence (G5e); on select |
| 6 | `GET /projects/{p}/events?subject=task:{task.plan_version}:{task_id}` | `BoardEvent[]` | task timeline (G5b); on select |

Step 2 answering 404 (project has no `plan` artifact) is **not** a permanent failure by itself: omit `plan` and let step 3 decide (it 404s with "no current plan" — permanent).

## Error contract

| Condition | Classification | UI |
|---|---|---|
| `Run.projectKey === null` | permanent (`no_project`) | banner, no request made |
| HTTP 404 on step 1 or 3 | permanent (`not_found`) | banner |
| HTTP 404 on step 2 | not permanent | omit `plan`; step 3 decides |
| HTTP 404 on step 4 | skip that key (it vanished) | key omitted |
| HTTP 404 on step 5 or 6 | the selected task vanished | selection cleared |
| any other status, network error, proxy 5xx — during the initial load or a poll | transient | "connection lost — retrying", keep rendered data, retry via `startPoll` (the initial load runs inside the poll loop until it first succeeds) |
| 200 with `[]` tasks | success, empty | explicit empty state, zeroed counters |

Branch on `isNotFound(e)` from `api/errors.ts`, never on message text.

## Mock contract (`createMockBoardApi`)

Selected when the SPA's API mode is mock (`VITE_API=mock`, the app Playwright tier). Fixtures in `features/board/__fixtures__/` must cover:

- a project with a plan published by a mock run, tasks in every `TaskStatus`, one diverged task, one task with `error`, evidence of each kind, events for at least one task, and artifact versions from this run and from another run (so the G5d filter is observable);
- a mock run whose `projectKey` is `null` (banner);
- a mock run whose project answers 404 (banner);
- a mock run with a reachable project and zero tasks for it (empty state).

## Non-goals

No writes (claim/status routes are agent routes, FR-024); no `/stats` (G5c derives counters); no markdown content routes.
