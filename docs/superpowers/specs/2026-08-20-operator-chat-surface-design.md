# The Operator Chat Surface — A Pydantic AI Agent over the Channel Contract — Design

| | |
|---|---|
| Date | 2026-08-20 |
| Work items | **E-86** (new, §9.2). Amends **E-11** rather than replacing it |
| Requirements | US-7 (chat half), FR-303, FR-305, FR-601 (sibling), FR-604; ADR-6 (explicitly *not* extended); OQ-11 (restated and widened) |
| Scope input | `ROADMAP.md` §9.2 (E-6…E-11), §2 FR-600; `PRD.md` §5 US-7; `src/sdlc/channels/`; `src/sdlc/dashboard/`; `src/sdlc/board/`; `interfaces/dashboard/api/main.py`; `pydantic_ai` 2.21.0 (`pydantic_ai.ui._web`, `pydantic_ai.toolsets`) |
| Status | Designed. Not implemented |

§9.2 has one unbuilt line: **E-11**, *"MCP server as a channel adapter —
list/detail/inbox/answer/decide/start."* It has sat there since E-6 because MCP
needs a client we do not ship. This increment builds the same six verbs behind a
surface that needs no client at all — a first-party chat agent served by
`pydantic_ai.ui._web.create_web_app` — and factors the verbs into a module E-11
imports instead of reimplements.

The section's thesis is unchanged and load-bearing: *notifications, cross-run
inbox, dashboard backend, and MCP server are one primitive wearing four hats —
render the pending decision, deliver it, translate the reply into a signal.*
This is the fifth hat. `channels/transport.py:6` already names the pattern:
*"query, match, signal, verify — written once so every surface reuses it."*

Unlike E-10, **this increment does contain an LLM call**, and it is the first
surface where a model can start a run and approve a merge gate. §11 is about
that, and it is not an afterthought.

---

## 1. What exists today

**The verbs are built; only the mouth is missing.** `src/sdlc/dashboard/api.py`
serves `/runs`, `/runs/{id}`, `/inbox`, `/events` (SSE), `/runs/{id}/answer`,
`/runs/{id}/decide`, and `POST /runs`. `src/sdlc/board/api.py` serves
`/projects`, `/projects/{p}`, its artifacts and versions, `/tasks`, `/events`,
`/stats`. Both are composed into one uvicorn process by
`interfaces/dashboard/api/main.py`, whose docstring states the reason: *"so the
frontend has one origin and E-60 has one place to install identity."*

Underneath both sits the layer that actually matters here:

- `channels/contract.py` — pure `render`/`translate` over `pending_decisions()`.
  All four render variants (clarify / stage gate / task escalation / merge gate)
  collapse to **two** FR-302 signals on reply.
- `channels/transport.py` — `resolve_key`, `submit`, `NoMatch`. Derives the gate
  round from the pending item.
- `channels/inbox.py` — `fetch_inbox`, cross-run aggregation that degrades to
  `InboxError` per run rather than aborting.
- `dashboard/fleet.py` — `FleetPoller`, a lazy shared poller with `subscribe()`
  yielding `FleetSnapshot`s, and the change-fingerprinting the SSE route at
  `dashboard/api.py:113` already performs.
- `board/store.py` — `BoardStore` over SQLite; durable cross-run artifact, task,
  event and stats state.

**What is absent.** There is no operator-facing tool layer. Every verb exists
only as an HTTP route with a FastAPI signature, so a second consumer (MCP, chat)
can reach it only over the network or by copying logic.

**Two constraints discovered while surveying, both of which shape the design:**

1. **The agent registry is closed.** `agents/loader.py:_parse_role` rejects any
   directory not in `KNOWN_ROLES`: *"the directory name is the role name, so
   this is a typo, not an extension point."* Every folder under `agents/` is
   further validated at worker boot against ADR-6 anti-collusion model-family
   inequality. An operator chat agent is not a pipeline role and must not become
   one — see D5.
2. **Artifact reads are already capped.** `board/api.py:MAX_CONTENT_BYTES` is
   `512 * 1024`, byte-capped *"the way `load_session` is
   (`artifacts/read.py:18`) so one large artifact cannot blow a consumer's
   context."* That precedent is right and the cap is wrong for this consumer —
   see D7.

**Library facts, verified against the installed tree, not from memory**
(`pydantic_ai` 2.21.0, `starlette` 1.3.1, both already resolved by
`pydantic-ai-slim` in `pyproject.toml`):

- `pydantic_ai.ui._web.create_web_app(agent, models=…, deps=…, instructions=…,
  html_source=…, sdk_version=…)` returns a `Starlette` app: the chat UI at `/`
  and `/{id}`, and `Mount('/api')` carrying `POST /chat`, `GET /configure`,
  `GET /health`.
- The UI HTML is fetched from `cdn.jsdelivr.net/npm/@pydantic/ai-chat-ui@2.0.0`
  and cached on disk (`LOCALAPPDATA` on Windows). `html_source` overrides this
  with a local path for offline or air-gapped use.
- `sdk_version` defaults to `7`; `app.py`'s own comment says v7 is what *"enables
  tool-approval streaming."*
- `pydantic_ai.toolsets.FunctionToolset` takes `requires_approval: bool` per
  tool; `ApprovalRequiredToolset` wraps a whole toolset. The protocol types are
  `DeferredToolRequests`, `DeferredToolResults`, `ToolApproved`, `ToolDenied`,
  and the `ApprovalRequired` exception.

Human-in-the-loop approval is therefore **wiring, not invention**.

---

## 2. Decisions

**D0 — E-86 is a new epic beside E-11, not a replacement for it.** MCP still
buys something chat does not: approving a gate from Claude, goose, or an IDE
without opening a browser. E-11 stays open and its ROADMAP line is amended to
say it re-exports `sdlc/operator/tools.py`. FR-602 stays open until MCP ships;
this increment closes only the chat half of US-7.

**D1 — The reusable artifact is a domain toolset, not an HTTP client.** Tools
call `channels/`, `dashboard/fleet.py`, and `board/store.py` directly. Calling
our own localhost routes from inside the same process would make E-11 inherit a
network hop to itself, re-parse typed models from JSON, and force every unit
test to boot a server.

**D2 — `src/sdlc/operator/`, under `src/`.** Same reason `board/api.py:5` and
`dashboard/api.py:3` both give: `packages.find` is rooted at `src`, so anything
outside it is not importable by tests. `interfaces/chat/` holds only assets and
the mount.

**D3 — `tools.py` never imports `pydantic_ai` or FastAPI.** `agent.py` is the
sole file that knows Pydantic AI exists. E-11 adds `mcp.py` as its sibling. This
is the whole point of D1 and is enforced by a test (§13).

**D4 — Every write requires human approval; no read does.** `start_run`,
`answer_question`, and `decide_gate` are `requires_approval=True`. The
confirmation card renders the pending item as `channels/contract.py` renders it,
so the operator approves against *what the workflow asked*, not the agent's
paraphrase of it. Rationale in §11.

**D5 — The chat agent is not a registry role.** Its prompt and model live in
`interfaces/chat/{instructions.md,agent.yaml}`, read by a small loader in
`operator/agent.py`. This keeps §9.1's *prompts as versioned assets* — the
prompt is a reviewable file, not a Python string — without adding a name to
`KNOWN_ROLES`, without subjecting an operator surface to worker-boot validation,
and without ADR-6 family inequality applying to an agent that decorrelates from
nothing.

**D6 — Mounted into the existing app, not a second process.** `create_web_app`
is mounted at `/chat` in `interfaces/dashboard/api/main.py`. One process, one
port, one origin; the chat shares the *same* `FleetPoller` instance the
dashboard drives, so `follow` costs no additional Temporal fan-out, and E-60
still has one place to install identity.

**D7 — `read_artifact` gets a 32 KB budget, not the HTTP surface's 512 KB.**
512 KB is roughly 130k tokens: one call ends the conversation. The board's HTTP
cap is correct for the Vue frontend and wrong for an LLM. Paging via `offset`,
and the agent may only read a key it received from `get_project`.

**D8 — Three write tools, not five.** `pending.py` already collapses four render
variants into two FR-302 signals, and `dashboard/api.py:14` made exactly this
call for the same reason. `GateOutcome` (`approve`/`reject`/`revise`) is a
parameter, not three verbs.

**D9 — The agent never types a gate round.** `transport.resolve_key` derives it
from the pending item. This is E-7's scar: a `--round` defaulting to `1` silently
deduped a post-REVISE approve *under a success message*. A model guessing rounds
would reproduce that bug at conversational speed.

**D10 — Shipped behind `SDLC_CHAT_ENABLED`, default off.** Matches E-85's
flag-off discipline and the `SDLC_*` env convention. Unset means `/chat` is not
mounted and the dashboard boots exactly as it does today.

---

## 3. Module layout

```
src/sdlc/operator/
  __init__.py
  deps.py      OperatorDeps — poller, board store, starter, per-request limits
  tools.py     the twelve verb functions; no pydantic_ai, no fastapi
  render.py    models -> compact agent-facing text, incl. the orientation line
  errors.py    ToolError — typed, model-actionable, traceback-free
  agent.py     builds the Agent + FunctionToolset; loads the prompt asset

interfaces/chat/
  instructions.md   system prompt (versioned asset, §9.1)
  agent.yaml        model + model settings
```

`interfaces/dashboard/api/main.py` gains a conditional mount and nothing else.

---

## 4. `OperatorDeps`

```python
@dataclass
class OperatorDeps:
    poller: FleetPoller
    board: BoardStore
    starter: Callable[[IdeaBrief, PipelineConfig, str], Awaitable[str]]
    actor: str = "chat"
    max_artifact_bytes: int = 32 * 1024
    max_follow_calls: int = 10
    _follow_calls: int = 0          # reset per HTTP request
```

Passed to `create_web_app(deps=…)` and reached in tools through
`RunContext[OperatorDeps]`. `starter` is the closure `main.py` already defines
for the dashboard's `POST /runs`; it is injected rather than imported so tests
substitute a fake without a Temporal client.

`_follow_calls` is per-request state and is why `OperatorDeps` is constructed
per request rather than once at mount time. `poller` and `board` are the
long-lived shared instances.

---

## 5. The tool surface

Nine reads, three writes. Names are the operator's vocabulary, not the HTTP
routes'.

### 5.1 Reads

| Tool | Source | Returns |
|---|---|---|
| `list_runs(status="open"\|"closed"\|"all")` | `poller.snapshot()` | fleet view |
| `get_run(run_id)` | snapshot | `RunState` + rendered pending items; `RunSummary` when closed |
| `follow(run_id=None, timeout_s=60)` | `poller.subscribe()` | `ChangeReport` (§7) |
| `inbox()` | snapshot `.inbox` | cross-run pending decisions |
| `list_projects()` | `BoardStore.list_projects` | key + repo |
| `get_project(project)` | `BoardStore` | detail incl. artifacts and stats |
| `list_tasks(project, plan_version=None, status=None)` | `BoardStore.list_tasks` | board tasks |
| `project_events(project, since=0)` | `BoardStore.list_events` | durable timeline |
| `read_artifact(project, key, version_id=None, offset=0)` | `BoardStore` | capped body (§8) |

`inbox()` reads the snapshot's already-fanned-out `inbox` field rather than
calling `fetch_inbox` again — the poller has paid for it.

`list_artifacts` is deliberately absent: `get_project` already returns
`ProjectDetail.artifacts`, and a second tool would only give the model a way to
be wrong about which one to call.

### 5.2 Writes

```python
start_run(title, mode: ProjectMode, description="", repo=None) -> str
answer_question(run_id, key, text) -> ReplyReceipt
decide_gate(run_id, key, outcome: GateOutcome, text="") -> ReplyReceipt
```

`ReplyReceipt` carries `run_id`, `key`, `confirmed: bool`, and a human-readable
`detail` — the same three facts `transport.submit` already returns, named so the
agent can repeat them without inventing a summary.

All three are `requires_approval=True`. `mode` and `outcome` are the existing
`ProjectMode` and `GateOutcome` enums — the model picks from a closed set, and
an invalid value is a schema error before it is a semantic one.

### 5.3 Three rules that keep the model honest

1. **Keys are never invented.** `key` must come from a rendered pending item, so
   the agent has necessarily called `get_run` or `inbox` first. `transport`'s
   `NoMatch` becomes a `ToolError` reading *"key `<k>` is no longer pending on
   `<run>`; re-read the inbox and try again"* — a message the model can act on,
   not an exception that kills the turn. Board `NotFoundError` / `ConflictError`
   / `InvalidTransition` translate the same way.
2. **The round is derived, never supplied** (D9).
3. **`confirmed=False` is informational, never an error.** As
   `dashboard/api.py:_reply` documents, the dominant cause is another surface
   winning the race, which is FR-302 working as designed. The receipt says so in
   words the agent repeats to the operator.

### 5.4 `render.py` and the orientation line

`render.py` converts models to compact text — the agent should never see raw
JSON dumps of `RunState`. It also produces the per-turn orientation line, one
per open run, injected into instructions:

```
kroker-auth-2026-08-20 · 7/15 architecture · pending: merge gate (r2) · $4.12
```

This makes "what's running?" and "what's blocked?" cost zero tool calls. It is
capped at 20 runs, after which it degrades to a count and the model must call
`list_runs`.

---

## 6. The write path

Identical to the dashboard's, with one hop inserted:

```
tool call
  -> ApprovalRequired            (raised by the toolset, not by us)
  -> approval chunk on the v7 stream
  -> operator confirms in the UI
  -> ToolApproved on the next request
  -> transport.resolve_key(handle, key)   -- derives the round
  -> transport.submit(handle, pending, reply, channel=ChatChannel(actor))
  -> Temporal signal
```

`ChatChannel` is a third `Channel` implementation beside `DashboardChannel` and
the CLI's — a name for the surface, nothing more.

A `ToolDenied` result returns to the model as a plain fact: the operator
declined, no signal was sent. The agent reports that and does not retry.

FR-302's `(gate, round)` identity and first-decision-wins make a race between
chat, dashboard, and CLI safe by construction. No new concurrency control is
introduced, and none is needed.

---

## 7. `follow`

Fingerprints **the projection of one run**, not the whole snapshot. A
fleet-wide fingerprint changes whenever any run moves, so a run-scoped follow
against it would fire continuously; `dashboard/api.py:113` already strips `at`
before fingerprinting for the same reason, and this reuses that idea at a
narrower scope. With `run_id=None` the scope is the whole fleet and that is the
intended behaviour.

Returns immediately — before `timeout_s` — when the run reaches a **pending
decision** or a **terminal status**. Those are what the operator is waiting for;
returning on every intermediate stage change would spend a turn per stage.

`ChangeReport` names what moved: stage advanced, new pending decision, run
closed, or `timed_out=True`.

**Two brakes, both in the tool rather than the prompt** — a prompt instruction
is a suggestion, a counter is a limit:

- `timeout_s` clamps to `[5, 120]`.
- After `max_follow_calls` (10) consecutive calls in one HTTP request, the tool
  refuses with *"report to the operator before waiting again."*

The `HEARTBEAT_S = 15` idle-emit in the SSE route has no analogue here: a tool
call is not a proxied long-lived connection.

---

## 8. Artifact reads

```python
class ArtifactRead(BaseModel):
    project: str
    key: str
    version_id: int
    content: str
    total_bytes: int
    truncated: bool
    next_offset: int | None
```

Three independent brakes, because the operator explicitly chose the wide read
scope and one brake is not enough:

1. **32 KB per call** (`OperatorDeps.max_artifact_bytes`, D7), with `offset`
   paging and `next_offset` in the response.
2. **No fishing** — `key` must have come from `get_project`; an unknown key is a
   `ToolError`, not a store lookup.
3. **The prompt instructs summarize-then-quote**, never dump.

Truncation is on a character boundary with `truncated=True` set, so the model
knows it is looking at a fragment and can page rather than hallucinate the rest.

---

## 9. The agent

`interfaces/chat/agent.yaml`:

```yaml
model: anthropic:claude-sonnet-4-6
max_tokens: 64000
```

`claude-sonnet-4-6` is the repo's existing choice where tool-use quality
outranks throughput (`agents/adversary/agent.yaml`); the bulk roles run
`glm-5.2`, which is a cost choice for high-volume pipeline work this surface
does not do. ADR-6 does not constrain this value: the chat agent decorrelates
from nothing and is not in the registry (D5).

`interfaces/chat/instructions.md` is the system prompt. It states: the operator
is a human running a factory of long-lived Temporal workflows; keys come from
tool output only; summarize artifacts rather than quoting them whole; report
`confirmed=False` verbatim; never claim a signal was sent when approval was
denied.

`operator/agent.py` reads both, builds `Agent(model, instructions=…,
toolsets=[FunctionToolset(...)])`, and appends the orientation line through a
dynamic instructions function so it is recomputed per turn.

`create_web_app(models=…)` additionally exposes a model picker in the UI, so
switching mid-conversation needs no restart.

---

## 10. Composition

```python
# interfaces/dashboard/api/main.py
if os.environ.get("SDLC_CHAT_ENABLED") == "1":
    app.mount("/chat", create_web_app(build_chat_agent(), deps=...))
```

The existing `shutdown` hook already closes the poller; the chat surface owns no
resource that outlives a request.

**Fail soft, always.** A missing model API key, a missing `interfaces/chat/`
asset, or any error building the agent logs one line and skips the mount. The
operator dashboard must never fail to boot because the chat surface is
misconfigured. This is asymmetric on purpose: the dashboard is the surface
people depend on.

---

## 11. Safety and identity

The dashboard is localhost-bound and unauthenticated **by design** (spec D4,
OQ-11). This surface inherits that posture and adds something genuinely new: a
language model that can start runs and approve merge gates. OQ-11 is therefore
not merely restated here, it is widened, and this section records that honestly
rather than letting it be discovered later.

Containment until E-60 lands identity (FR-1004):

- `SDLC_CHAT_ENABLED` defaults to off (D10).
- Localhost bind, unchanged.
- **Every** write is approval-gated (D4) — the model proposes, the human
  disposes. The model cannot move the factory unattended.
- The approval card renders the workflow's own pending text, so the operator is
  never approving a paraphrase.
- `ChatChannel(actor=…)` is self-asserted and reaches `GateDecision.reviewer`
  only — **never** `decided_by`, exactly as `X-Actor` does today
  (`dashboard/api.py:13`). E-60/FR-1004 is where that stops being acceptable for
  every surface at once.

**Errors return typed messages, never tracebacks.** A traceback in a chat UI
leaks filesystem paths into a transcript the model then echoes. `errors.py`
exists to make that structural rather than a review habit.

---

## 12. Observability and cost

Logfire (`pyproject`'s `[logfire]` extra) instruments the agent run and each
tool call, giving per-conversation traces beside the pipeline's.

**A limitation to record rather than hide:** tokens spent here are outside
`RunSummary` accounting. This surface has no run to attribute cost to, so
FR-701's run-level budgets do not see it and cannot cap it. Logfire makes the
spend visible; enforcement is deferred and listed in §15.

---

## 13. Testing

**`tests/test_operator_tools.py` — the bulk, and it needs no LLM, no server, and
no browser.** A fake poller (a canned `FleetSnapshot` and a driveable
`subscribe()`) plus an in-memory `BoardStore`:

- stale key → `ToolError` with re-read guidance, for both write verbs
- round derivation from the pending item; a post-REVISE approve is **not**
  deduped (the E-7 regression, pinned here)
- `confirmed=False` surfaces as informational, not as an error
- `read_artifact`: 32 KB cap, `truncated`, `offset` paging to completion, and an
  unknown key refused without a store lookup
- `follow`: change detected, timeout, `timeout_s` clamping, and refusal after
  `max_follow_calls`
- board error translation (`NotFoundError` / `ConflictError` /
  `InvalidTransition`)

**`tests/test_operator_agent.py`** — `TestModel` / `FunctionModel`:

- the toolset exposes exactly twelve tools
- the three writes are `requires_approval=True` and the nine reads are not
- a `ToolDenied` result produces a report of non-action, not a retry
- the orientation line renders and caps at 20 runs

**`tests/test_operator_layering.py`** — asserts D3 by inspecting
`sdlc.operator.tools`' module imports: no `pydantic_ai`, no `fastapi`. Cheap,
and it is the test that keeps E-11 able to reuse this module.

**One `temporal`-marked test** proves `decide_gate` really signals a workflow,
reusing the existing ephemeral-server fixtures.

**No browser or UI tests.** The bundled chat UI is a CDN artifact we do not own
and do not vendor.

---

## 14. Consequences to record

- ROADMAP §9.2 gains **E-86**; **E-11**'s line is amended to state that it
  re-exports `sdlc/operator/tools.py` rather than reimplementing the verbs.
- FR-602 stays open (MCP unbuilt). US-7 is half-closed: gates are now
  approvable conversationally, but not from a third-party client.
- OQ-11 is widened, not resolved (§11).
- A new outbound egress exists: the chat agent's model provider, plus the
  `cdn.jsdelivr.net` fetch for the UI HTML on first run. Both belong in FR-703's
  ledger. `html_source` pointing at a vendored file removes the CDN dependency
  for an air-gapped deployment, and this spec names it as the supported escape
  hatch rather than promising to vendor now.

---

## 15. Open questions

- **OQ-C1 — Cost containment.** Chat spend is invisible to FR-701. Does the chat
  surface need its own budget ceiling, and should crossing it disable the mount
  or merely warn?
- **OQ-C2 — Should approval survive a page reload?** The bundled UI holds
  conversation state client-side; a reload mid-approval loses the pending
  request. Acceptable for a localhost operator tool; a server-side conversation
  store is the fix if it proves annoying.
- **OQ-C3 — Is `claude-sonnet-4-6` the right default?** Chosen on the reasoning
  in §9, not measured. The UI's model picker makes this cheap to revisit against
  real conversations, and changing it is one line in `agent.yaml`.
- **OQ-C4 — Flag default.** Shipped off (D10). Flipping it on by default is a
  separate decision to make after the surface has been used, mirroring E-85's
  discipline of shipping the flag off and deciding later.
