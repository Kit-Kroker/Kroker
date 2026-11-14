# kroker-mcp — the MCP channel adapter

A Rust MCP stdio server (E-11, FR-602) that exposes Kroker's operator
verbs to MCP clients. It serves whatever the Python verb bridge
(`src/sdlc/operator/bridge.py`, over `sdlc/operator/tools.py`)
publishes; per-session writes are human-confirmed through MCP
elicitation. The [contracts](../../.specify/specs/022-mcp-channel-adapter/contracts/mcp-tools.md)
are the binding surface; this README is the operator-facing summary.

## Prerequisites

- The Rust toolchain pinned by `rust-toolchain.toml` (rustup installs
  it automatically on the first cargo command from this directory).
- A Kroker checkout with its venv: `uv sync --frozen --extra dev` from
  the repo root (the bridge child runs that venv's Python).
- A Temporal server reachable at `TEMPORAL_HOST` (a
  `temporal server start-dev` is enough) — without it only the
  board/artifact reads work.
- `git` on PATH.

## Build

From the repo root:

```bash
cargo build --release --manifest-path interfaces/mcp/Cargo.toml
```

The binary lands at `interfaces/mcp/target/release/kroker-mcp`
(`.exe` on Windows). The one-entry check for everything Rust plus the
real-binary parity suite is `python scripts/check_mcp.py`.

## Client configuration

Claude Code:

```bash
claude mcp add kroker -- <repo>/interfaces/mcp/target/release/kroker-mcp --repo <repo>
```

Any client that reads an `mcpServers` block (goose's MCP extension,
IDEs, editors) — see [`client-config.example.json`](client-config.example.json):

```json
{ "mcpServers": { "kroker": {
    "command": "<repo>/interfaces/mcp/target/release/kroker-mcp",
    "args": ["--repo", "<repo>"] } } }
```

## Environment

| Variable | Meaning |
|---|---|
| `SDLC_REPO_ROOT` | Fallback for `--repo` (the bridge child's cwd and venv home). |
| `SDLC_MCP_PYTHON` | Override the interpreter used for the bridge child. |
| `SDLC_MCP_ACTOR` | Override the self-asserted actor (`mcp:<client-name>` by default; must match `^mcp:[a-z0-9-]{1,40}$`). |
| `TEMPORAL_HOST` | Read by the bridge, as everywhere else in Kroker. |

## The twelve tools

Order is load-bearing — `tools/list` publishes it and the membership
tests assert it. Confirm values: `none` (a read), `pending` (a reply
to something a human is owed), `start` (a new run). Details, schemas
and the fixed sentences: [contracts/mcp-tools.md](../../.specify/specs/022-mcp-channel-adapter/contracts/mcp-tools.md).

| # | Tool | Kind | Confirm | Progress |
|---|---|---|---|---|
| 1 | `list_runs` | read | none | |
| 2 | `get_run` | read | none | |
| 3 | `follow` | read | none | yes |
| 4 | `inbox` | read | none | |
| 5 | `list_projects` | read | none | |
| 6 | `get_project` | read | none | |
| 7 | `list_tasks` | read | none | |
| 8 | `project_events` | read | none | |
| 9 | `read_artifact` | read | none | |
| 10 | `start_run` | write | start | |
| 11 | `answer_question` | write | pending | |
| 12 | `decide_gate` | write | pending | |

## Confirmation and the trust boundary

Every write verb requires a human's boolean before anything is sent to
the factory. The mechanism depends on the protocol revision the client
speaks: below 2026-07-28 a form-mode `elicitation/create` (E1, 300 s
timeout); at 2026-07-28 and above an MRTR `input_required` round with a
sealed, single-use, args-bound `requestState` (E2). The preview the
human confirms is digest-verified at call time — if the pending item
changed in between, the call answers `changed` and nothing is sent.

There is no unconfirmed path, ever. What the server cannot control is
the client's side of the dialog (research R1):

- A client or hook that **auto-accepts** elicitation bypasses the human
  gate by client policy. The server did its job; the operator chose a
  client that answers for them.
- A client that **auto-declines** means nothing changes — every write
  is refused with a fixed sentence.
- A client **without an elicitation capability** cannot write at all:
  writes fail closed with a sentence pointing at the dashboard or
  `python -m sdlc.cli`.

## The follow brake

`follow` waits for change and reports it. Ten consecutive `follow`s in
one session are the cap: the eleventh is refused with a sentence
telling the model to report to the operator before waiting again. Any
other tool call resets the streak. A cancelled wait still counts (it
was a wait). The streak lives in the Python bridge child, so a bridge
respawn (child death) restarts it at zero — documented behaviour.

## Auth posture

FR-014, restating OQ-11 unchanged: this is a local, unauthenticated,
stdio server with a self-asserted actor. It is strictly narrower than
the HTTP surfaces because it has no socket — only a process the
operator's own user spawns can reach it. Do not expose it over a
transport without solving identity first (E-60/FR-1004 is where that
lands).
