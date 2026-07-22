# E-8 — Cross-run inbox

| | |
|---|---|
| Status | Design — approved, awaiting spec review |
| Date | 2026-07-22 |
| Roadmap item | `E-8` (§9.2) |
| Requirements served | FR-305 (cross-run decision inbox), FR-603 (CLI's missing verb) |
| Depends on (shipped) | `2026-07-18-channel-contract-over-fr302-design.md` (E-6), `2026-07-19-cli-refit-onto-channel-contract-design.md` (E-7) |
| Scope guard | Read-only listing across runs. No push delivery (E-9), no dashboard/MCP (E-10/E-11). Acting on an item still goes through the existing `--id`-scoped `approve`/`reject`/`revise`/`answer` verbs. |

## 1. Problem

E-7 refit the CLI onto the channel contract, but every verb is scoped to one
run (`--id` required). Nothing today answers "what, across every run, is
waiting on a human?" — the exact gap FR-305 names and E-6's own spec
predicted:

> E-8 cross-run inbox becomes a query over `pending_decisions()` across run
> handles.

and E-7's spec, more specifically:

> E-8 (cross-run inbox) becomes `resolve`'s sibling: the same `match` over
> `pending_decisions()` results gathered from many handles instead of one.

The substrate already exists — `pending_decisions()` (from E-6) and
`transport._fetch` (from E-7, the query+validate step of `resolve`). What's
missing is (a) a way to discover *which runs exist* without the operator
already knowing their ids, and (b) aggregation across N runs where any single
one can fail independently.

## 2. Non-goals

- No push delivery / notifications (E-9).
- No dashboard backend or MCP server (E-10/E-11) — this is a CLI verb only.
- No acting on an inbox item directly (e.g. `inbox --approve`). The operator
  reads the run id off the inbox, then uses the existing `--id`-scoped verbs.
- No listing of closed (completed/terminated/timed-out) runs — a closed run
  has nothing pending by construction. See §7 for the reasoning.

## 3. Architecture

```
cli.py `inbox` verb
  |
channels/inbox.py     (NEW)  list_open_run_ids / fetch_inbox / render_inbox
  |
channels/transport.py (existing) fetch_pending(handle) -> list[PendingDecision]
  |
pending.py + feature.py       (existing) pending_decisions() query
```

`channels/inbox.py` is `resolve`'s sibling: the same fetch, applied to many
handles discovered via Temporal visibility instead of one handle the caller
already named.

### 3.1 Run discovery is a server-side filter, not a client-side one

`list_open_run_ids(client)` calls:

```python
client.list_workflows(
    "WorkflowType='FeatureWorkflow' AND ExecutionStatus='Running'")
```

Filtering by `WorkflowType` server-side matters because the same task queue
carries `ReflectWorkflow` and `BenchmarkWorkflow` executions
(`workflows/reflect.py`, `benchmarks/workflow.py`) — neither exposes
`pending_decisions`, so probing them would only produce noise in `errors`.
Filtering by `ExecutionStatus='Running'` excludes closed runs at the source
rather than fetching and discarding them.

### 3.2 `transport.py` gets one rename, no behavior change

`transport._fetch` becomes `transport.fetch_pending` (public). `resolve` and
`submit` call the renamed function unchanged. This is the only edit to
`transport.py` — the query/validate logic (query by name, validate through
the `TypeAdapter`, per E-7 §10's resolved implementation risk) is exactly
right for inbox too and should not be reimplemented.

## 4. Data model — `src/sdlc/channels/inbox.py`

```python
from pydantic import BaseModel
from ..pending import PendingDecision

class RunInbox(BaseModel):
    run_id: str
    pending: list[PendingDecision]

class InboxError(BaseModel):
    run_id: str
    error: str

class Inbox(BaseModel):
    runs: list[RunInbox] = []      # only runs with >=1 pending item
    errors: list[InboxError] = []  # runs whose query raised
```

A run with an empty `pending_decisions()` result is dropped, not listed as
`RunInbox(pending=[])` — nothing is owed on it, so it is not inbox-worthy.

## 5. `fetch_inbox`

```python
async def list_open_run_ids(client) -> list[str]:
    return [wf.id async for wf in client.list_workflows(_OPEN_FEATURE_QUERY)]


async def fetch_inbox(client) -> Inbox:
    run_ids = await list_open_run_ids(client)
    results = await asyncio.gather(
        *(_fetch_one(client, rid) for rid in run_ids))
    inbox = Inbox()
    for rid, outcome in zip(run_ids, results):
        if isinstance(outcome, Exception):
            inbox.errors.append(InboxError(run_id=rid, error=str(outcome)))
        elif outcome:
            inbox.runs.append(RunInbox(run_id=rid, pending=outcome))
    return inbox


async def _fetch_one(client, run_id: str):
    try:
        handle = client.get_workflow_handle_for(FeatureWorkflow.run, run_id)
        return await fetch_pending(handle)
    except Exception as e:                     # noqa: BLE001 -- captured, not raised
        return e
```

`asyncio.gather` runs every run's query concurrently; a per-run exception is
caught inside `_fetch_one` (not left to `gather`'s exception propagation) so
one failing run can never take down the others. No concurrency cap: fleet
sizes in scope for this increment are small (tens of runs, not thousands),
and adding a semaphore now would be tuning a problem that doesn't exist yet.

## 6. CLI surface

New `inbox` verb, no arguments. Always live (same bucket as `status` and the
decision verbs — not `_local_only`, since it inherently needs the running
server's visibility store):

```
$ sdlc inbox
feature-add-sso:
  architecture (round 1)
feature-fix-bug:
  Q1: Use OIDC or SAML?
  merge (round 2)

1 run could not be queried:
  feature-stale-run: <error message>

$ sdlc inbox
nothing pending across 3 open runs

$ sdlc inbox
no open runs
```

Each item line reuses `transport.describe()` verbatim — the same rendering
already used for `Ambiguous`'s candidate listing in the single-run verbs, so
there is exactly one function that turns a `PendingDecision` into text.
`render_inbox(Inbox) -> str` in `channels/inbox.py` handles the three empty
states (no open runs / open runs but nothing pending / normal listing) plus
the trailing error block.

All output stays ASCII, per the existing CLI-wide constraint (E-7 §7).

## 7. Error handling

- Per-run query failure -> `InboxError`, listed separately; the command
  still exits 0 with whatever did resolve (per your direction: a single
  run's failure — closed between list and query, or an older worker version
  without `pending_decisions` — must not hide everything else that
  successfully answered).
- Zero open runs -> `"no open runs"`.
- Open runs, nothing pending in any -> `"nothing pending across N open runs"`.
- Closed runs are excluded by the visibility query itself (§3.1), not
  filtered client-side, and are out of scope for this increment: a closed
  run has nothing pending by definition, and surfacing "what a run was
  waiting on before it timed out" is a different, audit-shaped feature
  (retro/`RunSummary`, §1 item 13) than a live inbox.

## 8. Testing

- **Pure unit tests for `render_inbox`** given hand-built `Inbox` values:
  empty (no runs), nothing-pending, single run, multiple runs, with and
  without an `errors` block. No Temporal involved — same style as the
  existing `_message`/`_listing` tests in `transport.py`.
- **`fetch_inbox` against a stub client**, not a real Temporal server: a
  fake `list_workflows` returning a scripted async iterator of ids, and fake
  handles whose `query` either returns a scripted `pending_decisions` result
  or raises. This covers: all-success aggregation, one run erroring while
  others succeed, and an empty-results run being dropped rather than listed.
  Deliberately not run against `WorkflowEnvironment.start_time_skipping()`:
  whether that lightweight test server implements the visibility
  `list_workflows` query at all is untested territory, and gating this
  suite on it would make an unrelated infra gap block this feature's tests.
- `list_open_run_ids` is trusted by inspection (two lines, direct pass-through
  of a query string to `client.list_workflows`) rather than integration
  tested, consistent with how thin the rest of `transport.py`'s
  Temporal-touching functions are.
- CLI parsing/dispatch test for `inbox` (no args, calls `fetch_inbox` +
  `render_inbox`, prints the result), following the existing CLI test
  pattern (`tests/test_eval_cli.py`).

## 9. Files

| file | change |
|---|---|
| `src/sdlc/channels/inbox.py` | **new** — `RunInbox`, `InboxError`, `Inbox`, `list_open_run_ids`, `fetch_inbox`, `render_inbox` |
| `src/sdlc/channels/transport.py` | rename `_fetch` -> `fetch_pending` (public); no behavior change |
| `src/sdlc/cli.py` | new `inbox` subparser + dispatch |
| `tests/test_channel_inbox.py` | **new** — `render_inbox` unit tests, `fetch_inbox` against a stub client |
| `tests/test_channel_transport.py` | update references from `_fetch` to `fetch_pending` if directly exercised |

## 10. What this unblocks

E-10 (dashboard backend) and E-11 (MCP server) both need "what's pending
across the fleet" as their landing view — `fetch_inbox`/`Inbox` becomes the
data source both adapt into their own rendering, the same way `resolve`
already is for single-run surfaces.
