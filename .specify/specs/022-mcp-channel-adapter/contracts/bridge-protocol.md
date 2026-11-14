# Contract — Rust ⇄ Python verb bridge (JSON-lines over the child's stdin/stdout)

**Owner:** Python (`src/sdlc/operator/bridge.py`). The Rust side
(`interfaces/mcp/src/bridge.rs`) is a client of this contract and contains
no verb names. A change here bumps `BRIDGE_PROTOCOL` in both places. The
`init` handshake refuses a mismatch with a stderr message and exit code 2.

## Framing

- One JSON object per line, UTF-8, `\n`-terminated, at most 4 MiB.
- Python writes frames **only** to the duplicated original fd 1. fd 1 and
  `sys.stdout` are redirected to stderr before any `sdlc` import.
- Every request carries an `id` (string, unique per session). Every request
  gets exactly one terminal frame with the same `id`. A `follow` request may
  also get zero or more `progress` frames first.
- Requests may be concurrent. Python processes each in its own task and
  serialises writes with a lock.

## Frames

### Rust → Python

| `op` | Fields | Meaning |
|---|---|---|
| `init` | `protocol: 1`, `actor` | first frame; Python validates `actor` against `^mcp:[a-z0-9-]{1,40}$`, builds `OperatorDeps`, replies `describe` |
| `preview` | `id`, `tool`, `args` | pure read; never calls `note_other_tool` |
| `call` | `id`, `tool`, `args`, `expect_digest?` | runs the verb; `expect_digest` is required for `confirm != none` tools, and the bridge refuses without it |
| `cancel` | `id` | cancels that in-flight task; Python then sends its terminal frame with `error.code = "cancelled"` |

### Python → Rust

| `op` | Fields |
|---|---|
| `describe` | `protocol: 1`, `tools: [ToolDescriptor]` (data-model.md) |
| `result` | `id`, `ok: true`, `value` (str for text verbs; object for typed verbs and for `preview`: `{message, digest}`) |
| `result` | `id`, `ok: false`, `error: {code, message}` with `code ∈ {tool_error, changed, cancelled, bad_request, internal}`; `message` is `ToolError.message` verbatim for `tool_error`, and the fixed sentences below otherwise |
| `progress` | `id`, `elapsed_s`, `message` (`"waiting on <run_id or fleet> (<n>s)"`), emitted at most every 15 s while a `progress` tool runs |

Fixed sentences:
- `changed`: "the pending item changed while you were confirming; re-read the inbox and retry"
- `bad_request`: "unknown tool or bad arguments: <pydantic summary without values>"
- `internal`: "the factory raised <Type>; the operator should check the server log"

## Semantics

- `call` runs `await tools.<name>(deps, **args)`. Arguments are validated
  with the same pydantic schema `describe` published, and enums are coerced
  (`GateOutcome`, `ProjectMode`). `guard` already turns every exception into
  `ToolError`.
- `confirm = pending`: before the verb runs, the bridge re-runs the preview
  computation and compares it to `expect_digest`. On a mismatch it returns
  `changed`, and no signal is sent.
- `confirm = start`: the digest covers args only, so a mismatch means the
  arguments were swapped.
- Every write logs `mcp write actor=<a> tool=<t> run=<r> key=<k> confirmed=<c>`
  at INFO to stderr.
- On stdin EOF: cancel all tasks, `await deps.poller.aclose()`, exit 0.

## Rust-side obligations

- Spawn on `initialized`, with `kill_on_drop(true)`, `PR_SET_PDEATHSIG(SIGTERM)`
  on Linux, piped stdin/stdout and inherited stderr.
- Map `result.ok=false` to an MCP `CallToolResult` with `isError: true` and
  `error.message` as its text.
- Map typed `value` to `structuredContent` plus a JSON text block, and text
  `value` to one text block.
- `ReplyReceipt` with `confirmed=false` is `isError: false` (FR-006).
- Forward MCP `notifications/cancelled` → `cancel`, and `progress` frames →
  `notify_progress` when the request had a `progressToken`.
- If the child dies, fail in-flight calls with the `internal` sentence and
  respawn on the next call. The follow streak resets, which is documented.
