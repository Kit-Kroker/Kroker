# The Dashboard Backend — Live Fleet State over the Channel Contract — Design

| | |
|---|---|
| Date | 2026-08-18 |
| Work items | **E-10** (§9.2). Resolves E-10/E-75 duplicate tracking; see D0 |
| Requirements | FR-601, FR-1204, US-6, ADR-8 (second exception), OQ-11 (restated) |
| Scope input | `ROADMAP.md` §0 (P2), §9.2 (E-6…E-11), §14 (E-75), §15 item 7; `interfaces/dashboard/frontend/src/api/`; `src/sdlc/channels/`; `src/sdlc/board/api.py` |
| Status | Implemented 2026-08-18 (plan `docs/superpowers/plans/2026-08-18-dashboard-backend.md`) |

P2's summary line has read "brownfield mode and dashboard backend remain" since
the phase opened. Half of that is now stale — E-84 landed brownfield intake,
context and checked delta on 2026-08-15, and E-47a/b/c landed the
`CapabilityMap` that §15 item 3 named as the brownfield unblocker. The dashboard
backend is the last unbuilt half.

"No backend" overstates the work. `api/http.ts:3` rejects all eight methods with
*"Dashboard http provider not wired"*, and the dashboard runs entirely on
`api/mock` — but the hard halves were built deliberately in advance and are
waiting to be used. `channels/transport.py:6` names this item by number:
*"query, match, signal, verify — written once so every surface (CLI now; E-8
inbox, **E-10 dashboard**, E-11 MCP later) reuses it."* This increment is
mostly assembly.

It contains no LLM call.

---

## 1. What exists today

**Built and load-bearing:**

- **`pending.py`** — four `PendingDecision` variants that map **1:1** onto the
  frontend's four `InboxItem` variants: `ClarifyPending`→`ClarifyItem`,
  `StageGatePending`→`GateItem`, `MergeGatePending`→`OverrideItem` (checks and
  verdict included), `TaskEscalationPending`→`EscalationItem`. Pure pydantic, so
  it imports inside the Temporal sandbox.
- **`channels/contract.py`** — pure `render`/`translate`. All four variants
  collapse to the two FR-302 signals on reply, which is precisely the
  frontend's four write verbs. It documents its own extension point: *"a
  surface MAY override render for richer presentation"*, and `PushChannel`
  names "dashboard push" outright.
- **`channels/transport.py`** — `fetch_pending` / `resolve` / `submit`:
  query, match, signal, verify. Written surface-agnostically for this consumer.
- **`channels/inbox.py`** — `fetch_inbox(client)`: cross-run discovery via a
  server-side visibility filter, concurrent fetch, and per-run error isolation
  (`InboxError`) so one bad run cannot abort the page.
- **`board/api.py`** — a working FastAPI precedent in this codebase:
  `create_app(store_factory)`, injectable dependency, typed pydantic responses,
  and a documented reason to live under `src/` rather than `interfaces/`.
- **`observability/trace.py`** — E-32's `RunEvent` log. `STAGE_STARTED` gives
  the current stage; `GATE_DECIDED` gives decision history with timestamps.

**The gap, stated precisely.** It is not the inbox — that is nearly free. It is
`listRuns`/`getRun`. The frontend's `Run` needs cost, budget, decision history
and stage. All of that state is already in workflow memory —
`self._role_usage` (`feature.py:567`), `cfg.run_budget_usd`,
`self._gate_decisions` (`gates.py:51`), `self._trace` (`feature.py:560`) — and
**no query exposes any of it**. The only queries are `status()` (a bare
string), `pending_gate()`, `pending_decisions()`, and `run_summary()`, which is
`None` until the run terminates.

**A second, quieter defect.** `interfaces/dashboard/api/main.py` is named as the
dashboard's entrypoint and serves `sdlc.board.api` instead. The path has been
lying since E-78.

**A third: the frontend types are a view model, not a contract.** They were
designed against the mock, and several fields have no backend source at all —
`ClarifyItem.confidence` (`'0.82'`) does not exist on `OpenQuestion`
(`models.py:232`) or `ClarifyPending`; `stageNote` and `blocker` are hand-written
prose; `age: "2h 14m"` and `ts: "09:12"` are pre-formatted display strings. Any
design that promises to serve `types.ts` verbatim is promising to invent data.

---

## 2. Decisions

**D0 — E-10 and E-75 are one item tracked twice; this is E-10.** §9.2 frames the
backend as a channel adapter; §14 frames it as a consumer of `GraphWorkflow`'s
`graph_state()`/`graph()`. The interpreter (E-72/E-73/E-74) is unbuilt, and §15
item 7 already concedes *"E-75 can be lifted out and shipped on its own."* This
increment builds the FeatureWorkflow-shaped backend. **E-75 narrows to "add the
two graph queries to the existing backend if and when the interpreter lands"**
and stops being a duplicate of E-10.

**D1 — one new query, `run_state()`, exposing state that already exists.** No new
workflow bookkeeping: every field is read from state the run already holds. The
sole addition is stashing `self._idea` in `run()`, following the precedent three
lines away — `_cfg` is stashed for the identical reason (`feature.py:551`:
*"cfg is threaded as a parameter everywhere else; the gate hooks run inside
GateHost and cannot receive it, so run() stashes it here"*).

**D2 — two routers, one process.** `sdlc/board/api.py` and a new
`sdlc/dashboard/api.py` stay separate, independently testable factories; the
entrypoint composes both into one app on one port. One origin for the frontend,
one place for auth when E-60 lands, and the entrypoint's name becomes true.

**D3 — the backend serves domain models; `http.ts` adapts.** Python does not
format `"2h 14m"`. Fields with no source are dropped from `types.ts`, not
faked. This also keeps `stageIdx` out of the backend — E-76 already states that
`Run.stageIdx` *"is a linear index that cannot express graph position and
becomes `currentNodes: string[]`"*, so encoding it server-side would bake in
something the roadmap has already scheduled for replacement.

**D4 — localhost-bind, no auth, `X-Actor` → `GateDecision.reviewer`.** Matches the board
API's existing posture exactly rather than inventing a second half-measure
beside it. Recorded as a known gap under OQ-11, not silently inherited. E-60
(FR-1004) remains the single place identity gets solved for both surfaces.

**D5 — SSE with a shared background poller; REST for initial load.** A shared
poller is *cheaper* on Temporal than per-request fan-out, not more expensive:
per-request costs `N_clients × N_runs` because every tab fans out
independently, while one poller multiplexes at `N_runs` regardless of tab
count. US-6's one-screen fleet view and E-9's already-push-shaped gate
notifications both want a gate to appear when it opens, not up to a poll late.
REST serves the cold load so the store still renders if SSE fails or is blocked.

**D6 — the poller is lazy with a grace period, and REST never depends on it.**
Starts on the first subscriber or a cold read; stops `grace_s` after the last
unsubscribe, so an operator tool left open overnight stops querying Temporal
when nobody is watching. A REST read finding no snapshot — or one older than
`2 × interval` — fans out inline and stores the result.

**D7 — closed runs need no database either.** `fetch_inbox` filters
`ExecutionStatus='Running'` (`inbox.py:66`), so a naive port drops a run the
moment it finishes — yet the frontend's `Status` union has `done` and `failed`,
which such a fleet can never produce. Temporal keeps closed workflows queryable
for its retention period, and `run_summary()` returns a populated `RunSummary`
on exactly those. A second visibility query, capped at the 20 most recent,
renders closed runs from `run_summary()`. This **upholds** E-75's "live run
state needs no database" claim rather than bending it: Temporal is the store.
The bound is stated, not hidden — history reaches back only as far as
Temporal's configured retention.

`RunSummary` gains `title` and `repo_url`, because it carries neither today and
a closed run would otherwise render as a bare workflow id. The id is
`feature-{slug(title)}`, so a title is *lossily* recoverable from it — and
reconstructing it that way is how a fleet view ends up disagreeing with itself
about what a run was called. Additive, and it holds §4's rule that the two
models mirror each other where they overlap.

---

## 3. Module layout

```
src/sdlc/dashboard/__init__.py
src/sdlc/dashboard/api.py       # create_router() -> APIRouter
src/sdlc/dashboard/fleet.py     # fan-out, snapshot, poller (no FastAPI import)
src/sdlc/dashboard/channel.py   # DashboardChannel (Channel protocol impl)
interfaces/dashboard/api/main.py  # composes board + dashboard routers
```

Under `src/`, for the reason `board/api.py:5` already documents: *"pyproject's
packages.find is rooted at src — anything outside it is not importable by
tests."*

`fleet.py` imports no FastAPI, so the fan-out and the poller — where the
interesting failures live — are testable without an HTTP client, exactly as
`channels/transport.py` is testable without a CLI.

---

## 4. `RunState` — the live sibling of `RunSummary`

`RunState` goes in `models.py` directly beside `RunSummary` (`models.py:1169`),
because that is what it is: `RunSummary` is the terminal aggregate, `RunState`
is the same picture mid-flight. It **reuses `RunSummary`'s field names wherever
they overlap** — `mode`, `started_at`, `cost_usd_total`, `budget_usd`,
`budget_crossings`, `roles` — so the live fleet view and the retro report
cannot develop two vocabularies for one concept. `models.py` is already
imported inside the sandbox via `workflow.unsafe.imports_passed_through()`.

```python
class RunState(BaseModel):
    """Live counterpart to RunSummary: what a run looks like mid-flight.
    Field names mirror RunSummary where they overlap, deliberately."""
    run_id: str
    title: str
    repo_url: str | None
    mode: str
    status: str                    # GateHost._status verbatim
    current_stage: str | None      # last STAGE_STARTED in _trace
    started_at: datetime
    decisions: list[GateDecision]  # _gate_decisions, ordered
    roles: list[RoleUsage]
    cost_usd_total: float | None
    budget_usd: float | None
    budget_crossings: int
```

**`cost_usd_total` stays `float | None`.** `RoleUsage.cost_usd` documents that
None is load-bearing — *"tokens are facts from the run; dollars are a lookup
that can fail"* (`models.py:702`). Summing None to `0.0` would make a pricing
failure read as a free run, which is the FR-915 defect class this project keeps
closing. The frontend renders it as "—", never "$0.00".

**The query lives on `FeatureWorkflow`, not `GateHost`.** `GateHost` is shared
with `TriageWorkflow` and `TidyUpWorkflow`, which hold no `IdeaBrief` and no
role usage; defining it there would force them to answer a query about state
they do not have.

### 4.1 `opened_at` on the pending variants

No `PendingDecision` variant carries a timestamp, so inbox item age has no
source — and "this merge gate has been waiting four hours" is most of why an
operator opens the fleet view. `opened_at: datetime` is added to the four
variants, set at construction in `gate_pending()` and `clarify_pending()`.

Additive and cheap, and E-9 already proves both that the value exists at that
exact point and that it matters: `gates.py:118` passes `opened_at` into
`NotifyInput` today. Setting it from `workflow.now()` at construction is
replay-deterministic, since `_pending` is workflow state written once per item.

---

## 5. The read path

### 5.1 The fan-out

One `FleetSnapshot` is the unit everything derives from:

```python
class FleetSnapshot(BaseModel):
    at: datetime
    total_open_runs: int
    runs: list[RunState]
    closed: list[RunSummary]     # D7, 20 most recent
    inbox: list[RunInbox]        # reused from channels/inbox.py
    errors: list[InboxError]     # reused from channels/inbox.py
```

The inbox half needs **no new models**. `RunInbox` and `InboxError` already
exist (`inbox.py:16`, `:22`), and `InboxError`'s stated reason for existing —
one run's failed query must not abort the fetch — applies here unchanged.

The fan-out generalizes `inbox.py`'s `_fetch_one` to issue `run_state()` and
`pending_decisions()` concurrently per handle, preserving the
exception-into-value discipline `inbox.py:83` documents (*"Never raises: an
exception becomes the return value, so one run's failure can't take down
asyncio.gather for the rest"*). Closed runs are a second capped visibility
query answered from `run_summary()`.

`Inbox.total_open_runs` exists because "no runs listed" and "checked 3 runs,
none had anything pending" must stay distinguishable; `FleetSnapshot` keeps
that field for the same reason.

### 5.2 The poller

```python
class FleetPoller:
    def __init__(self, client_factory, interval=2.0, grace_s=30.0)
    async def snapshot(self) -> FleetSnapshot            # REST reads
    def subscribe(self) -> AsyncIterator[FleetSnapshot]  # SSE
```

- Subscribers are `asyncio.Queue`s in a set. The poll task starts on the first
  subscriber or a cold REST read, and stops `grace_s` after the last
  unsubscribe (D6).
- `snapshot()` returns the cached snapshot when younger than `2 × interval`,
  otherwise fans out inline and stores the result — so REST correctness never
  depends on the poller being up, which was the point of choosing lazy.
- `GET /events` emits `text/event-stream`, one whole `FleetSnapshot` per event.
  Deltas were rejected: full snapshots make reconnection a re-fetch with no
  server-side event buffer and no `Last-Event-ID` replay. It emits **only when
  the snapshot's content hash changes**, plus a comment-line heartbeat every
  15s so idle connections survive proxies and a dead poller is detectable.
- One Temporal client for the app lifetime via FastAPI `lifespan`, constructed
  with `pydantic_data_converter`. Non-negotiable, matching `cli.py:317` —
  without it `RunState` and `PendingDecision` do not round-trip.

---

## 6. The write path — three routes, not five

The frontend has four write verbs, but `pending.py:9` is explicit that *"all
four variants collapse to just two FR-302 signals on reply"*. The HTTP surface
mirrors the domain; `http.ts` maps its four verbs down (D3, applied
consistently).

| Route | Signal | Frontend verbs |
|---|---|---|
| `POST /runs/{id}/answer` | `answer_question` | `answerClarify` |
| `POST /runs/{id}/decide` | `submit_gate_decision` | `decideGate`, `overrideMerge`, `resolveEscalation` |
| `POST /runs` | — (`start_workflow`) | `startRun` |

Both decision routes take the pending item's **`key`** — the question id, or
`gate_key(gate, round)`. Because the key encodes the round,
`default_translate`'s existing guarantee holds for free: *"gate/round come from
the pending item, so a reply can never land on the wrong round"*
(`contract.py:81`).

**`match_key()` is added to `transport.py`, not to `dashboard/`.** The dashboard
operator clicked a specific item, so `Selector`'s name-and-ambiguity resolution
is a CLI concern that here would only add a way to hit the wrong item. But that
module's stated job is being written once for every surface
(`transport.py:6`), so the key-based lookup belongs beside `match()` rather
than forked.

**`X-Actor` reaches `GateDecision.reviewer` through `DashboardChannel`.**
`default_translate` hardcodes `decided_by="human"` (`contract.py:88`) and
leaves `reviewer` unset. **The identity goes in `reviewer`, not `decided_by`:**
`decided_by` is `Literal["human", "policy", "timeout"]` (`models.py:818`), and
that Literal is load-bearing — `ReadinessOverride.approved_by` carries it
verbatim so `"policy"` and `"timeout"` stay legible as non-human on the face of
the artifact. `reviewer` is already the established home for exactly this:
`triage.py:115` sets it with the comment *"self-asserted identity (FR-1004)"*.

Rather than adding a parameter to a pure function, the dashboard implements the
`Channel` protocol — delegating to `default_translate`, then stamping
`reviewer` — which is the extension point `contract.py:9` documents.
`submit()` is reused untouched.

**Double-submit is already safe.** FR-302 is first-decision-wins, and `submit()`
returns `SubmitResult.confirmed`. The route returns it verbatim and `http.ts`
renders `confirmed: false` as informational, not an error — `transport._message`
already explains why: *"the dominant cause is another surface winning the race,
which is FR-302 working as designed."*

`POST /runs` builds `IdeaBrief` + `PipelineConfig()` with id
`feature-{slug(title)}` per `cli.py:329`. An existing id raises
`WorkflowAlreadyStarted` → **409**, never a silent no-op.

---

## 7. Frontend changes

**`vite.config.ts` gains a dev proxy** (`/api` → `http://127.0.0.1:8500`) rather
than the backend growing CORS middleware. One origin was the point of D2; a
proxy honors it in dev instead of undoing it.

**`types.ts`** — `DashboardApi` gains `subscribe(cb): () => void` returning an
unsubscribe function; `StartRunInput` gains the `description` that `IdeaBrief`
requires. Per D3's drop-rather-than-fake rule, these are removed:

| Removed | Why |
|---|---|
| `Run.stageNote` | Hand-written prose; no source. |
| `Run.skipCtx` | No such field exists; the mock infers it from `mode`. |
| `ClarifyItem.confidence` | `OpenQuestion` has no confidence field. The mock's `'0.82'` is fiction. |

These survive, computed in `http.ts` from real data: `age` (from
`started_at`), `stageIdx` (`current_stage` indexed through `CANONICAL_STAGES`),
`blocker` (from `status` plus pending count), `Decision.ts` (from
`decided_at`). `cost` and `budget` become `number | null`, rendering "—" when
unpriced (§4).

**The mock implements `subscribe` with the timer it already has.**
`createMockApi` fakes liveness with `setInterval` + `tickCosts` every 4s
(`mock/index.ts:350`), so a push-shaped contract is *more* faithful to what the
mock already pretends to be than request/response was. Both providers finally
mean the same thing.

---

## 8. Testing

The interesting failures are in the fan-out and the mapping, so both are tested
without a server.

- **`fleet.py`** against a fake client (`list_workflows` +
  `get_workflow_handle`): aggregation; one raising run becomes an `errors[]`
  entry rather than a failed page; closed runs rendering via `run_summary()`;
  snapshot freshness triggering an inline fan-out; poller start and stop across
  the grace window.
- **Routes** via `TestClient` with an injected fake poller, generalizing the
  `create_app(store_factory)` seam (`board/api.py:60`). Covers 409 on duplicate
  id, `confirmed: false` passthrough, and `X-Actor` reaching
  `GateDecision.reviewer` while `decided_by` stays `"human"`.
- **SSE**: emits on content change, suppresses identical snapshots, heartbeats
  when idle.
- **`run_state()`**: a `pytest -m temporal` e2e that starts a real run and
  asserts cost, decisions and stage populate. The one part no fake can prove.
- **Contract drift guard.** D3 chose hand-written adaptation over codegen, so
  nothing structurally prevents the TS mapper drifting from the Python models.
  A script dumps JSON fixtures from `RunState`/`FleetSnapshot` via their
  pydantic schemas, and vitest feeds those exact fixtures to the mapper. Drift
  then breaks a test instead of a page.

---

## 9. Consequences to record

Part of this change, not follow-ups:

- **ROADMAP:94–95** — P2's "brownfield mode and dashboard backend remain" is
  stale on its first half. E-84 landed brownfield on 2026-08-15. Correct in
  place.
- **E-10 / E-75** — apply D0 to both §9.2 and §14.
- **ADR-8 (ROADMAP:331) takes a second documented exception**, alongside
  ADR-21's. The poller and subscriber set make this backend stateful
  in-process — not durable state, but not a stateless shell either.
  **`ARCHITECTURE.md` §8 needs the same amendment**, since it currently scopes
  the stateless-shells claim to operator surfaces and this is one.
- **OQ-11** — restate: a second unauthenticated surface now serves, and it can
  start runs and approve merge gates. E-60/FR-1004 remains the fix.
- **FR-601 and US-6** flip once this lands.

**This does not close P2 by itself.** P2's exit criterion is *"first brownfield
feature merged via PR"* — a demonstration, not a code state. This closes the
last unbuilt half; demonstrating the exit is a separate run.

---

## 10. Open questions

- **OQ-13 — closed-run history is bounded by Temporal retention.** D7 buys
  history without a database, but only as far back as the server's configured
  retention. If an operator ever needs older history, that is a store, and it
  is a new item — not a quiet widening of this one.
- **OQ-11 (existing, restated)** — two unauthenticated surfaces now, one of
  which spends money and merges code. Localhost-bind is the whole containment.
