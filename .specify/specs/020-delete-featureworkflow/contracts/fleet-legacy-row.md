# Contract: legacy closed rows and legacy-run errors (FR-004, FR-008; Q1 = A)

## 1. `FleetSnapshot` (the `/api/inbox` body and every SSE event): an additive field

```text
closed_legacy: list[LegacyRun] = []      # new; default empty
LegacyRun:
  run_id:     str
  status:     str            # visibility close status, lower-case: completed|failed|terminated|canceled|timed_out|continued_as_new|unknown
  start_time: datetime|null
  close_time: datetime|null
```

Rules:

1. A closed row whose visibility `workflow_type == "FeatureWorkflow"` goes
   to `closed_legacy` and **never** to `closed`, `closed_marks` or `errors`.
   No workflow handle is created and no query is sent for it.
2. A row with type `None` stays on today's queried path.
3. A legacy id that is also in the open set is dropped, the same rule
   `closed` uses.
4. The closed-run query filter keeps `WorkflowType='FeatureWorkflow'`
   permanently, in both `_CLOSED_QUERY` and `_CLOSED_QUERY_UNORDERED`
   (`_PIPELINE_TYPES`), with the note "never removed: pre-cutover runs stay
   visible".
5. `CLOSED_LIMIT` counts legacy rows, because the scan is shared.
6. `open_errors` and the fleet cap are unchanged.
7. No existing field changes (FR-015).

## 2. `GET /api/runs/{run_id}`

The handler searches `runs`, then `closed`, then `closed_legacy`. A legacy
hit returns the `LegacyRun` JSON with HTTP 200.

## 3. `GET /api/fleet/summary`

Legacy rows are absent. This is intentional and noted in a comment at
`fleet_summary.py`.

## 4. Frontend (`interfaces/dashboard/frontend/src/api/http.ts`)

- `snap.closed_legacy ?? []` is mapped by `mapLegacy` into the same closed
  list, sorted with the other rows by close time.
- Each legacy row gets:
  - `title`: "legacy run, summary unavailable";
  - `status`: `done` when `status == "completed"`, otherwise `failed`;
  - `stageMarks: null`, `cost: null`, `budget: null`, `roles: []`,
    `decisions: []`, `repo: ''`, `projectKey: null`;
  - `age` taken from `start_time`.
- `Run` gains `legacy: boolean`, which is `false` on every other row.
  `mode` is required (`ProjectMode`) and a legacy row has none, so it
  carries `'greenfield'` as a placeholder. `features/fleet/FleetTable.vue` hides the mode
  badge and the cost cell when `legacy` is true. No mode value is invented
  for display.
- `types.ts` gains the `LegacyRun` wire type.
- `mock/index.ts` gains one legacy row, so the dev mock shows it.

## 5. Legacy-run errors on the reply and status paths

A **query failure** on a run is followed by `describe()`. When the
description's `workflow_type == "FeatureWorkflow"`, the code raises
`LegacyRunError(run_id)` (in `channels/transport.py`). Each surface maps it:

| Surface | Today | After |
|---|---|---|
| `POST /api/runs/{id}/answer`, `/decide` | HTTP 500 | HTTP **410** `{"detail": "legacy FeatureWorkflow run; it can no longer be queried"}` |
| CLI `approve/reject/revise/answer/status --id` | traceback | stderr message, exit 1 |
| operator `answer_question` / `decide_gate` | exception | tool error with the same message |

A non-legacy query failure propagates unchanged. The happy path adds no RPC.
