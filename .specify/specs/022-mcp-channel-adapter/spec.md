# Feature Specification: MCP server as a channel adapter (E-11)

**Feature Branch**: `022-mcp-channel-adapter` (spec directory only; no branch is created — shared tree)

**Created**: 2026-11-14

**Status**: GATE 1 ruled by owner 2026-11-14 (Q1 Rust held; Q2 elicitation fail-closed; Q3 twelve verbs) — seam (a)/(b)/(c) locked in plan

**Input**: User description: "E-11 — MCP server as a channel adapter (FR-602, US-7). Expose operator verbs over MCP: list/detail/inbox/answer/decide/start. Owner direction: Rust via official rmcp SDK; central tension = re-export Python verb layer (src/sdlc/operator/tools.py) vs Rust. Cost seams (a) Rust shim over dashboard HTTP API, (b) Rust + Python sidecar IPC, (c) Rust native reimplementation, (d) Python FastMCP sdlc/operator/mcp.py fallback. Settle transport, verb surface, actor identity, follow brake/paging mapping, location/packaging, auth posture."

**Requirements served**: FR-602 (closes it), US-7 (closes the MCP half; E-86 closed the chat half). OQ-11 restated, not resolved.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Ask an MCP client what is blocked (Priority: P1)

An operator working in an MCP-capable assistant (Claude Code, goose, an IDE
agent) asks "what's blocked in the factory?". The assistant calls the
factory's read tools and answers from live fleet state: the open runs, the
stage each sits in, and every decision each is waiting on — without the
operator opening a browser or the dashboard being up.

**Why this priority**: It is US-7's acceptance criterion ("MCP tools expose
inbox + decisions") and every write depends on keys the reads surface.

**Independent Test**: With a fake fleet (two open runs, one pending gate, one
pending clarify question), connect an in-process MCP client, list the tools,
call `inbox`, `list_runs`, `get_run`; the returned text is byte-identical to
what the chat surface's same verbs return for the same fleet.

**Acceptance Scenarios**:

1. **Given** two open runs with three pending decisions, **When** the client calls `inbox`, **Then** it receives every pending decision, each with its run id and exact key, rendered exactly as `operator/render.py` renders it for chat.
2. **Given** a run id that is neither open nor recently closed, **When** the client calls `get_run`, **Then** the call returns an error result whose text is the verb's own `ToolError` wording ("no run … call list_runs") and the session stays usable.
3. **Given** `status="bogus"`, **When** the client calls `list_runs`, **Then** the error result names the allowed values.

---

### User Story 2 — Approve a gate or answer a question conversationally (Priority: P1)

The operator tells the assistant "approve the plan gate on feature-x" or
"answer the clarify question: use Postgres". The assistant proposes the
write; the operator is shown the workflow's own pending text and confirms;
the decision reaches the run through the same FR-302 signal path every other
surface uses, and the audit trail records that it came over MCP.

**Why this priority**: This is the other half of US-7 and the reason MCP is
worth building beside chat (E-86 D0: approve "from Claude, goose, or an IDE
without opening a browser").

**Independent Test**: Against a fake Temporal handle, call `decide_gate`
with a current key; assert exactly one FR-302 signal was sent, the
`GateDecision.reviewer` equals the MCP actor string, and the result carries
`confirmed` and `detail` exactly as `ReplyReceipt` defines them.

**Acceptance Scenarios**:

1. **Given** a pending stage gate, **When** the client calls `decide_gate(outcome="approve")` and the human confirms, **Then** one `submit_gate_decision` signal is sent and the result reports `confirmed=true` with transport's detail text.
2. **Given** a clarify question key, **When** the client calls `decide_gate` on it, **Then** the error result says the key takes a text reply and names `answer_question`.
3. **Given** a key another surface already answered, **When** the client calls `answer_question`, **Then** the result is `confirmed=false` with transport's wording — informational, not an error (FR-302 race working as designed).
4. **Given** the human declines the confirmation, **When** any write is invoked, **Then** no signal is sent, no run is started, and the result says the operator declined.
5. **Given** a revise outcome, **Then** `text` is passed as guidance and there is no `thaw_tests` parameter on the tool (contract C2: no agent surface exposes it).

---

### User Story 3 — Start a run from the assistant (Priority: P2)

The operator asks the assistant to start a feature run from a title,
description, mode and (for brownfield) a repo URL. The run starts after
confirmation, under fleet back-pressure (B4), and the assistant reports the
run id Temporal assigned.

**Why this priority**: In FR-602's verb list but less frequent than
reading and deciding; the CLI and dashboard already cover it.

**Independent Test**: Fake starter; `start_run` with brownfield and no repo
→ error result naming the missing repo; with a full fleet cap → the
capacity refusal wording from `operator/errors.py`; happy path → the
starter's returned id.

**Acceptance Scenarios**:

1. **Given** the fleet is at its pending cap, **When** `start_run` is called, **Then** the error result is the B4 capacity wording and the starter is never invoked.
2. **Given** a title with no letters or digits, **Then** the error result asks for a descriptive title.
3. **Given** a run id that already exists, **Then** the error result says so and suggests `get_run`.

---

### User Story 4 — Follow a run and read its artifacts (Priority: P3)

The assistant waits on a run ("tell me when feature-x needs me") and reads
published artifacts (the plan, the architecture) in pages, summarising
rather than quoting.

**Why this priority**: Not in FR-602's six, but MCP clients are themselves
LLM agents — the same consumer these two verbs were shaped for in E-86.
Under the recommended seam they cost one list entry each (see Decision S2).

**Independent Test**: `follow(run_id, timeout_s=5)` on an unchanging fake
fleet returns `timed_out=true`; eleven consecutive `follow` calls in one
session → the eleventh is refused with the brake wording; a `list_runs`
in between resets the streak. `read_artifact` on a 100 KB blob returns
32 KB with `truncated=true, next_offset=32768`.

**Acceptance Scenarios**:

1. **Given** a pending decision appears mid-wait, **Then** `follow` returns early with `changed` naming it.
2. **Given** ten consecutive waits, **Then** the next is refused until any other tool runs.
3. **Given** an unknown artifact key, **Then** the error result says to call `get_project`.

---

### Edge Cases

- **Temporal unreachable**: reads return the type-only `ToolError` ("the factory raised …; check the server log") — no paths, no credentials (`errors.py` `translate` fallback). The MCP process stays up.
- **Dashboard not running**: irrelevant — under seam (b) the bridge holds its own lazy `FleetPoller`; the dashboard is neither required nor affected.
- **Bridge child dies mid-session**: in-flight calls fail with the type-only error; the next call respawns it (the follow streak restarts at zero; documented).
- **MCP server fails to start** (bad env, missing dep): only the spawning client sees it; the dashboard, worker and chat are separate processes and cannot be affected (fail-soft by construction; see FR-012).
- **Client cannot render a confirmation** (no elicitation support): behaviour is the subject of Q2.
- **Client disconnects mid-`follow`**: the poller subscription is released; no leaked queue.
- **Long `follow` vs client tool timeout**: `timeout_s` clamps to 5–120 s; the server emits progress notifications while waiting so clients with idle timeouts do not cut the call.
- **Legacy-workflow run id** (020 §5): `LegacyRunError` wording passes through verbatim.
- **Unsafe client name** in the MCP handshake (spaces, control characters, 500 chars): normalised before it reaches the audit trail (FR-007).
- **Two MCP sessions at once** (two assistant windows): each is its own process with its own follow streak; writes race through FR-302 and the loser gets `confirmed=false`.

---

## Seam Decision *(brief-mandated design record)*

**GATE 1 ruling (owner, 2026-11-14): the server is implemented in Rust on
the official `rmcp` SDK. Seam (d) is out.** The spec lead's recommendation of
(d) is preserved below as the documented minority recommendation, with its
evidence, so the decision can be reopened on evidence later. The choice
among (a), (b) and (c) is **locked in plan.md**, after re-costing each — for
all **twelve** verbs (Q3) — against the official rmcp documentation
(stdio server, tool schema/annotation generation, progress notifications,
server-initiated elicitation).

### Repo facts the costing rests on (verified 2026-11-14)

| Fact | Evidence |
|---|---|
| The twelve verbs are framework-free async functions, OperatorDeps-first, and name E-11 as their second consumer | `src/sdlc/operator/tools.py:1-12` |
| `mcp.py` is the documented sibling of `agent.py` | `src/sdlc/operator/agent.py:3-5`; E-86 design D3 |
| E-86 D1 **already rejected** the HTTP-client seam for E-11 by name: "Calling our own localhost routes … would make E-11 inherit a network hop to itself, re-parse typed models from JSON, and force every unit test to boot a server" | `docs/superpowers/specs/2026-08-20-operator-chat-surface-design.md` §2 D1 |
| ROADMAP and the filesystem-first epic both say E-11 re-exports `tools.py` | `ROADMAP.md:345`; `docs/roadmap/filesystem-first.md` E-11 line |
| No Rust exists in the repo: no `Cargo.toml` outside `.venv`, no Rust toolchain in `.github/workflows/{ci,docs,release}.yml` or the `Dockerfile`, none on the dev host (`cargo: command not found`) | `find`, `grep` over CI/Dockerfile |
| `pyproject.toml` packages only `src/` (`[tool.setuptools.packages.find] where=["src"]`); there is no console script — the CLI runs as `python -m sdlc.cli` and `src/sdlc/cli.py` is 908/1000 lines | `pyproject.toml:39`; `wc -l` |
| `mcp` (the official Python SDK) is not in `uv.lock` today | `grep uv.lock` |
| The `reply_kind` check, B4 cap, slug/run-id rules and `ToolError` wording live only in Python | `tools.py`, `errors.py`, `channels/contract.py` |

### Cost of each seam

| | (a) Rust shim → dashboard HTTP | (b) Rust → Python sidecar | (c) Rust native | (d) Python `mcp` SDK in `operator/mcp.py` |
|---|---|---|---|---|
| Verb logic | Python, but the **HTTP** rendering of it | Python `tools.py` | **Reimplemented in Rust** | Python `tools.py`, imported |
| New languages/toolchains | Rust + cargo in CI, release, dev | Rust + cargo **and** an IPC contract | Rust + cargo + Temporal Rust client + sqlite | none (one bounded Python dep) |
| Runtime prerequisite | dashboard must be up (`:8500`) | Python env on PATH for the sidecar | Temporal + board sqlite reachable from Rust | same env the CLI already needs |
| Contradicts recorded decision | E-86 D1 (by name) | ROADMAP "re-exports" in spirit; adds a hop D1 forbids | ROADMAP:345 and tools.py docstring | none — it is the recorded plan |
| Permanent duplicate surface | error wording, rendering, reply-kind message, `thaw_tests` filtering | the IPC schema for twelve verbs | **everything**, below | none |
| Test story | needs a booted dashboard or a recorded HTTP fake per verb | two-process tests + IPC contract tests | parallel Rust test suite mirroring Python's | in-process MCP client session over the existing fakes |

**(a) REST coverage inventory for the six FR-602 verbs.** Coverage is
complete *at the HTTP level* but not at the *operator-verb* level:

| Verb | Route | Gap vs `tools.py` |
|---|---|---|
| list | `GET /api/runs` | returns `RunState` JSON, not `render.runs_view`; no `status` filter (open/closed/all) — shim must refetch `/api/inbox` for closed and re-implement the filter |
| detail | `GET /api/runs/{id}` | JSON, no pending block (`render.pending_for`); 404 text differs from the ToolError ("call list_runs") |
| inbox | `GET /api/inbox` | full `FleetSnapshot` JSON; rendering re-implemented in Rust |
| answer | `POST /api/runs/{id}/answer` + `X-Actor` | kind-mismatch is a bare 404 "is not a question", not "use decide_gate"; error vocabulary is HTTP statuses |
| decide | `POST /api/runs/{id}/decide` + `X-Actor` | body accepts `thaw_tests`; the shim must strip it (contract C2: no agent surface may expose it) |
| start | `POST /api/runs` | exposes `budget_usd` (chat does not); 409/422/429/502 must be re-mapped to the ToolError sentences |
| follow / read_artifact | none / board `…/markdown` routes | no bounded-wait route; no 32 KB byte-offset paging — both would need new Python routes *for* the shim |

So (a) needs new Python routes for the LLM-shaped verbs, a Rust copy of the
renderer and the error vocabulary, and a running dashboard — a strict
superset of (d)'s work, plus the network hop D1 rejected.

**(b) Sidecar.** The cleanest IPC contract for "call twelve Python verbs
from another process over stdio JSON-RPC" *is MCP itself*. The Python side
would therefore be (d) in all but name, and the Rust process becomes a
byte-forwarding proxy for a protocol both ends already speak. Who owns the
contract: Python, necessarily (it owns the verbs) — so every verb change
lands in the sidecar schema and is re-verified across a process boundary.
Pure overhead.

**(c) Native Rust, the honest permanent cost.** Duplicated and kept in
lock-step forever: the `ToolError` vocabulary and `translate()` mapping
(`operator/errors.py`, 74 lines of carefully worded, tested sentences); the
follow streak brake and its reset semantics (`deps.py`); the follow
fingerprint `_projection` and `_describe_change` (whose docstring records a
shipped bug from fingerprinting too much); 32 KB seek-paged
`read_artifact` with the pruned-blob path; `render.py` formatting (which
chat tests pin byte-for-byte); the reply-kind check, `resolve_key`/`submit`
FR-302 transport and `ActorChannel.reviewer` stamping
(`channels/transport.py`, `channels/contract.py`); B4 `check_fleet_capacity`;
`slug()` and the `feature-` id rule; `IdeaBrief`/`PipelineConfig` wire
shapes over Temporal's pydantic data converter. **Every future verb change
lands twice**, and drift between them is silent until an operator sees two
surfaces disagree about the same run. It also brings a Rust Temporal client
and sqlite access into a repo that has neither.

**(d) Python — minority recommendation, overruled at GATE 1.** `src/sdlc/operator/mcp.py` adapts the twelve verbs exactly
as `agent.py` does for chat: strip `deps` from the schema, map `ToolError`
to an MCP error result, mark writes. Cost: one bounded dependency pin and
one updated layering test. Every verb change lands once and both surfaces
inherit it.

**What would make Rust the right call** (recorded so the question can be
reopened on evidence, not taste): a deployment target without Python (MCP
server shipped to operator machines that do not have the repo), or a
requirement for a single static binary distributed via `release.yml`. Neither
exists today; FR-604 ("stateless shells") and the localhost-only posture
both assume the operator runs from the checkout.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (seam)**: The MCP server MUST be a Rust program built on the official `rmcp` crate (GATE 1 Q1). The seam to the verb layer is **(b), locked in plan.md** (research R2): a persistent Python verb bridge per session, so verb logic stays single-sourced in Python. Whatever the seam, the server MUST preserve the observable behaviour of the verbs in `src/sdlc/operator/tools.py` — rendered text, `ToolError` wording, the follow brake, 32 KB paging, reply-kind checks — and that parity MUST be enforced by an automated test that fails when the Python verbs and the MCP tools disagree for the same fleet state. Where the seam permits, verb logic SHOULD stay single-sourced in Python.
- **FR-002 (verb surface)**: The server MUST expose the six FR-602 verbs under their existing names — list → `list_runs`, detail → `get_run`, inbox → `inbox`, answer → `answer_question`, decide → `decide_gate`, start → `start_run` — and SHOULD expose the remaining six reads (`follow`, `list_projects`, `get_project`, `list_tasks`, `project_events`, `read_artifact`), regardless of seam (GATE 1 Q3). A test MUST fail when the MCP tool list and `agent.py`'s `READ_TOOLS`/`WRITE_TOOLS` differ in membership. Tool names, parameters and descriptions come from the verb signatures and docstrings; `deps` never appears in a tool schema.
- **FR-003 (read results)**: Text-returning verbs MUST return their rendered text unchanged as the tool's text content. Typed verbs (`read_artifact` → `ArtifactRead`, `follow` → `ChangeReport`, writes → `ReplyReceipt`) MUST return the model as structured content with its JSON schema advertised, plus the same JSON as text for clients without structured-content support.
- **FR-004 (errors)**: A `ToolError` MUST become an MCP tool error result (`isError: true`) carrying `ToolError.message` verbatim; the session MUST remain usable. No other exception text may reach the client (the `guard` decorator already funnels everything through `translate`).
- **FR-005 (write approval)**: Every write (`start_run`, `answer_question`, `decide_gate`) MUST be confirmed by the human before it takes effect, against the workflow's own pending text (as `channels/contract.default_render` renders it), not the assistant's paraphrase (E-86 D4). Writes MUST carry MCP tool annotations marking them non-read-only and destructive; reads MUST be marked read-only. The mechanism is **MCP elicitation, fail-closed** (GATE 1 Q2): the server asks the human, through the client, to confirm a form whose message is the pending item's own rendered text (or, for `start_run`, the run that would be started); only an explicit accept proceeds. Decline, cancel, timeout, or a client that cannot elicit → no effect, and an error result directing the operator to the dashboard or CLI. rmcp offers two elicitation paths depending on the negotiated protocol version (verified against rmcp 3.10.0 docs: `Peer::elicit`/`create_elicitation` are server-to-client requests that error on protocol `2026-07-28`+, which instead requires returning an `InputRequiredResult` and reading the answer on the client's retry via sealed `requestState`); the plan MUST cover both or state which versions are refused. **Consequence recorded per GATE 1:** if a negotiated session supports neither path, writes return the directing-error result in that session until it does — there is no unconfirmed fallback.
- **FR-006 (single signal path)**: Answers and decisions MUST go through `channels.transport.resolve_key`/`submit` (one of the two FR-302 signals); `confirmed=false` MUST be reported as an ordinary result, never an error.
- **FR-007 (actor identity)**: Writes MUST stamp actor `mcp:<client>` where `<client>` is the MCP handshake's `clientInfo.name` normalised to `[a-z0-9-]`, at most 40 chars, falling back to `mcp:local` when absent or empty after normalisation. An operator override MAY be supplied via `SDLC_MCP_ACTOR` (must itself start with `mcp:`). The actor is self-asserted and reaches `GateDecision.reviewer` only — never `decided_by` — exactly as `chat:local` and `X-Actor` do today. Clarify answers carry no identity on their FR-302 signal (`ActorChannel.translate` stamps only gate decisions, for every surface); adding one is a replay-sensitive workflow change outside E-11, so every MCP write — answers included — is additionally logged with its actor by the bridge.
- **FR-008 (no new reply fields)**: `decide_gate` MUST NOT expose `thaw_tests` (contract C2); `start_run` MUST NOT expose `budget_usd` (parity with chat; the dashboard remains the place to set a budget).
- **FR-009 (follow brake)**: The consecutive-wait streak (`OperatorDeps.max_follow_calls = 10`) MUST be scoped to one MCP session; any non-`follow` tool call resets it (existing `note_other_tool`). There is no per-request reset — MCP has no turn boundary, and the session is the natural scope (this resolves E-86 OQ-C2 for MCP; chat is unchanged).
- **FR-010 (follow liveness)**: While `follow` waits, the server MUST send MCP progress notifications at most every 15 s when the client supplied a progress token, and MUST release its poller subscription if the client cancels or disconnects.
- **FR-011 (paging)**: `read_artifact` MUST keep the 32 KB page (`OperatorDeps.max_artifact_bytes`), byte offsets, and `truncated`/`next_offset` semantics unchanged.
- **FR-012 (transport, now)**: The server MUST support stdio, spawned by the client on the operator's machine. It opens no network listener.
- **FR-013 (transport, later — out of scope)**: Streamable HTTP (rmcp `transport-streamable-http-server`) is deferred. A Rust server cannot mount inside the Python ASGI app, so if added it is a separate localhost listener (or reverse-proxied beside `/chat`); it MUST be opt-in, MUST never be fatal to the dashboard boot (the `mount_chat` principle), and MUST validate `Origin` (DNS-rebinding defence) before any tool runs.
- **FR-014 (auth posture)**: The stdio server inherits OQ-11 unchanged — local, unauthenticated, self-asserted actor — and narrows exposure relative to HTTP surfaces because it has no socket: only a process the operator's own user spawns can reach it. This increment amends nothing in OQ-11/D4; E-60/FR-1004 remains where identity becomes real.
- **FR-015 (layering)**: `src/sdlc/operator/tools.py` MUST stay a framework leaf and `tests/test_operator_layering.py` MUST keep passing unmodified in its existing assertions. Any Python added for the seam (new HTTP routes under (a), a sidecar entrypoint under (b)) MUST live outside `operator/tools.py` and MUST NOT be imported at dashboard or worker boot unless it is an opt-in fail-soft mount per the `mount_chat` precedent.
- **FR-016 (dependency policy)**: `rmcp` and every Rust dependency MUST be pinned to a bounded minor (`rmcp = "~3.10"`-style, mirroring the `pyproject.toml` bounded-pin policy) with a committed `Cargo.lock`, introduced in the same change that uses them. Any new Python dependency the seam needs follows the existing `pyproject.toml` bounded-pin + `uv.lock` policy.
- **FR-017 (file size)**: No file may exceed 1000 physical lines per `scripts/check_file_size.py`; nothing is added to `src/sdlc/cli.py` (908 lines). The Rust crate MUST sit under a path that script already scopes (`IN_SCOPE_PREFIXES` covers `interfaces/`, not a top-level `crates/`), and the generated `Cargo.lock` MUST be exempted the way `uv.lock` is.
- **FR-018 (docs)**: `ROADMAP.md` FR-602 and E-11 lines, the US-7 line, `ARCHITECTURE.md` (the "no `interfaces/mcp/`" note), and the `agent.py` docstring MUST be updated to reflect what shipped, plus a client-config snippet operators paste into their MCP client.

### Placement *(brief-mandated; seam-specific rows locked in plan.md)*

Fixed regardless of seam:

| Path | Role |
|---|---|
| `interfaces/mcp/` | the Rust crate (`Cargo.toml`, committed `Cargo.lock`, `src/`), so `scripts/check_file_size.py`'s existing `interfaces/` prefix scopes every `.rs` file; `interfaces/mcp/README.md` + `interfaces/mcp/client-config.example.json` tell operators how to point Claude Code / goose at the built binary |
| `src/sdlc/operator/tools.py`, `errors.py`, `render.py`, `deps.py` | unchanged as the behavioural source of truth the parity test (FR-001) is measured against |
| `tests/test_operator_mcp_parity.py` | the Python-side parity/membership test (FR-001, FR-002); how it drives the Rust binary (spawned over stdio, or against recorded fixtures) is a plan decision |
| `scripts/check_file_size.py` | `Cargo.lock` exemption added beside `uv.lock` (FR-017) |
| `.github/workflows/ci.yml` | a Rust job: `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test`, pinned toolchain |

Seam (b), locked: `src/sdlc/operator/bridge.py` (owns the IPC contract), `src/sdlc/operator/runtime.py` (framework-free composition), `src/sdlc/task_queue.py`; full list in plan.md §Source code touched. Still settled in plan: whether the `Dockerfile`
or `release.yml` must build the binary (stdio clients spawn it on the
operator's machine, so neither is required for local use); how
`OperatorDeps` composition (`FleetPoller`, `BoardStore`, the graph starter
`_start` in `interfaces/dashboard/api/main.py`) is reached without
duplicating `_start`.

### Test commands *(brief-mandated; final list in plan.md)*

```bash
cargo fmt --manifest-path interfaces/mcp/Cargo.toml --check
cargo clippy --manifest-path interfaces/mcp/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path interfaces/mcp/Cargo.toml
uv run pytest tests/test_operator_bridge.py tests/test_operator_layering.py tests/test_task_queue.py -q
SDLC_MCP_BIN=interfaces/mcp/target/release/kroker-mcp uv run pytest -m mcp tests/test_operator_mcp_parity.py -q
python scripts/check_mcp.py   # runs all cargo steps + the mcp-marker parity test
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_file_size.py --full
uv run pytest -q   # fast tier; diff FAILED ids against
                   # .specify/specs/021-recall-snapshot-artifact/baseline-failures.txt
```

No test spends tokens or needs a live Temporal: verb-layer dependencies are
faked as chat's tests already fake them; the Rust side is tested against an
in-process rmcp client and fakes of whatever the seam talks to.

### Key Entities

- **MCP tool**: one operator verb as an MCP client sees it — name, description (the verb docstring), input schema (signature minus `deps`), annotations (read-only vs destructive), output schema for typed verbs.
- **MCP session**: one client-spawned server process; owns one follow streak and one actor string.
- **Actor string**: `mcp:<client>`; self-asserted provenance written to `GateDecision.reviewer` and board events.
- **Write confirmation**: the human's yes/no on a write, shown against the pending item's rendered text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator in an MCP-capable assistant can go from "what's blocked?" to an approved gate in at most three tool calls (inbox → decide_gate → confirm), without opening a browser.
- **SC-002**: For the same fleet state, each read tool's text over MCP is byte-identical to the chat surface's output for the same verb (asserted by test for all text-returning verbs).
- **SC-003**: Every `ToolError` sentence a verb can raise reaches the MCP client verbatim; zero raw exception messages or file paths reach it.
- **SC-004**: A change to any verb's behaviour or wording that is not mirrored on the MCP side is caught by an automated check before merge (100% of the twelve verbs covered by the parity test); the plan states, per seam, how many places such a change must be edited.
- **SC-005**: Zero writes take effect without a human confirmation; 100% of MCP-originated gate decisions carry an `mcp:` reviewer in the audit trail, and 100% of MCP writes (answers included) appear in the bridge's write log with their actor.
- **SC-006**: Dashboard, worker and chat boot and behave identically whether the MCP server is installed, running, misconfigured, or absent.

## Assumptions

- MCP clients in scope are local assistants that spawn stdio servers (Claude Code, goose, IDE agents); remote/hosted clients wait for FR-013.
- The operator runs the MCP server from the repo checkout with the same environment the CLI uses (`TEMPORAL_HOST`, board sqlite path); no new configuration surface beyond `SDLC_MCP_ACTOR`.
- One operator per machine (the E-86 localhost single-operator assumption); two concurrent sessions are tolerated, not coordinated.
- The fakes used by `tests/test_operator_*.py` are sufficient to drive the adapter; no live-tier test is added (owner rule: no paid runs).
- The operator has (or the plan provides) a way to build the Rust binary locally; a pinned toolchain is declared in `interfaces/mcp/rust-toolchain.toml`.

## GATE 1 Rulings (owner, 2026-11-14)

- **Q1 — Seam / language: Rust held.** The server is Rust on `rmcp`. The spec lead's (d) recommendation is overruled and kept above as the documented minority recommendation. Mandated for plan: re-cost (a)/(b)/(c) for all twelve verbs against the official rmcp documentation before locking the seam.
- **Q2 — Write confirmation: MCP elicitation, fail-closed.** If rmcp (or a negotiated session) lacks elicitation, writes return the directing-error result until it does (FR-005).
- **Q3 — Verb surface: all twelve** (six MUST + six SHOULD), regardless of seam (FR-002).
