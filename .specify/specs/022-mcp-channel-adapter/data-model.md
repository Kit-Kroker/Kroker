# Data model — 022 MCP channel adapter

No persistent storage is added. Every entity is in-memory and per session,
or on the wire. Field names are normative for the contracts.

## ToolDescriptor (bridge → Rust, in `describe`)

| Field | Type | Rule |
|---|---|---|
| `name` | str | `fn.__name__` of a member of `tools.READ_TOOLS + tools.WRITE_TOOLS` |
| `description` | str | `inspect.getdoc(fn)` verbatim |
| `input_schema` | JSON Schema object | from the verb signature minus `deps`, via pydantic. MUST NOT contain `deps`; `decide_gate` MUST NOT contain `thaw_tests`; `start_run` MUST NOT contain `budget_usd` |
| `output_schema` | JSON Schema \| null | `Model.model_json_schema()` for `ArtifactRead`, `ChangeReport`, `ReplyReceipt`; null for `str`-returning verbs |
| `read_only` | bool | true iff in `READ_TOOLS` |
| `confirm` | `"none"` \| `"pending"` \| `"start"` | `none` for reads; `pending` for `answer_question`, `decide_gate`; `start` for `start_run`. Every write MUST have a non-`none` value (test-enforced) |
| `progress` | bool | true only for `follow` |

Rust maps the descriptor to `rmcp::model::Tool`. Annotations are
`read_only_hint=read_only`; for writes, `destructive_hint=true`,
`idempotent_hint=false`; `open_world_hint=false` for all.

## Session (Rust process, one per MCP client spawn)

| Field | Notes |
|---|---|
| `protocol_version` | captured in the `initialize` override |
| `elicitation` | `E1` if version < 2026-07-28 and the client capabilities include elicitation (form mode); `E2` if version ≥ 2026-07-28 and the client advertises elicitation via MRTR input requests; else `None` → writes fail closed |
| `actor` | `mcp:<normalised clientInfo.name>`, `mcp:local`, or a validated `SDLC_MCP_ACTOR` |
| `state_key` | 32 bytes from the OS CSPRNG at process start; never persisted or logged |
| `consumed_jti` | bounded map `jti → exp`, swept on insert; max 1024 entries, oldest evicted (an evicted entry is past `exp`, or the oldest live one: fail-closed on a full table) |
| `bridge` | child handle + pending-request map `id → oneshot` + progress sinks |

## Bridge state (Python child)

One `OperatorDeps` built by `runtime.operator_deps(actor)`. That gives the
follow streak scope = session (FR-009). In-flight tasks are keyed by request
`id`, for cancel.

## PreviewResult

| Field | Type | Rule |
|---|---|---|
| `message` | str | `pending`: `RenderedDecision.title`, `body`, `rows` (one `name: value` per line), then `Proposed: <outcome> — <text>`. `start`: title, mode, repo, description, and `fleet: <pending>/<cap>` when a cap is configured |
| `digest` | hex sha256 | of canonical JSON (`sort_keys`, no whitespace) `{tool, args, rendered}`, where `rendered` is `RenderedDecision.model_dump()` (pending) or `null` (start) |

## SealedState (E2 `requestState` payload; HMAC via `RequestStateCodec`)

| Field | Rule |
|---|---|
| `jti` | UUIDv4, single use |
| `tool` | must equal the retried call's tool name |
| `args_sha256` | sha256 of the canonical JSON of the retried call's arguments; must match |
| `digest` | the PreviewResult digest, forwarded as `expect_digest` |
| `exp` | unix seconds, issue + 300 |

The retry is rejected if the state is absent or tampered, `exp` has passed,
the tool or args mismatch, or `jti` was already consumed. The rejection is
an error result; nothing is executed.

## Confirm (elicitation form, E1 and E2)

`{ "confirm": boolean }`. Required, no default. Proceed only on action
`accept` with `confirm == true`.

## Actor string

`^mcp:[a-z0-9-]{1,40}$`. It reaches `GateDecision.reviewer` via
`ActorChannel`, never `decided_by`. It is logged for every write. Clarify
answers carry no identity on the FR-302 signal (research R8).

## Transitions — one write call

```
call(tool,args) ─► preview ──ToolError──► error result (no human prompt)
                     │ok
          E1 ─► elicit(message) ─accept∧confirm─┐
          E2 ─► InputRequired(sealed) … retry ──┤ verify seal/jti/args
        None ─► error "needs a human confirmation" (fail-closed)
                                                ▼
                       bridge call(expect_digest) ─digest mismatch─► error "pending item changed"
                                                │match
                                          verb runs → ReplyReceipt / run id / ToolError
decline | cancel | timeout | schema-fail ─► error "nothing was changed"
```
