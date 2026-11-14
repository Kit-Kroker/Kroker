# interfaces/mcp/ — AGENTS.md

The MCP channel adapter (E-11): a Rust rmcp stdio server fronting the
Python verb bridge. Local rules for anything editing this crate.

## The rules

- **No verb names in Rust.** None of the twelve tool names
  (`list_runs`, `get_run`, `follow`, `inbox`, `list_projects`,
  `get_project`, `list_tasks`, `project_events`, `read_artifact`,
  `start_run`, `answer_question`, `decide_gate`) may appear in any
  file under `src/`. The server branches on descriptor metadata only
  (confirm / progress); `tests/server.rs` has the grep test that
  enforces this. Python owns the verbs.
- **Python owns `bridge-protocol`.** The frame protocol
  (`contracts/bridge-protocol.md`) is versioned by
  `BRIDGE_PROTOCOL` on BOTH sides: `src/sdlc/operator/bridge.py` and
  this crate's handshake. Any protocol change bumps both in the same
  diff.
- **stdout is MCP-only.** The protocol owns fd 1; everything else
  (tracing, panics, debug output) goes to stderr. A stray print on
  stdout corrupts the frame stream — the Python bridge has
  `isolate_stdout()` for the same reason.
- **The gate is `python scripts/check_mcp.py`** from the repo root
  (fmt, clippy `-D warnings`, test, release build, then the parity
  suite against the fresh binary). CI runs exactly that line; so
  should you. Note the cargo steps run with cwd inside this crate —
  rustup resolves `rust-toolchain.toml` by working directory.
- **Files ≤ 1000 physical lines**, enforced by
  `scripts/check_file_size.py --full` across `interfaces/`. Test
  sections split into sibling files (`tests/progress.rs`,
  `tests/common/mod.rs`) when they grow.

## Where things live

| File | Role |
|---|---|
| `src/main.rs` | Arg/env parsing, tracing to stderr, the serve loop. |
| `src/server.rs` | The manual `ServerHandler`: tools/list, call routing, progress/cancel forwarding, the handshake watch. |
| `src/confirm.rs` | The write-confirmation gate: E1 elicitation, E2 MRTR + sealed state, the replay table. |
| `src/bridge.rs` | The Python child supervisor and frame client (pending map, progress sinks, respawn). |
| `src/actor.rs` | Client-name → `mcp:<actor>` normalisation. |
| `tests/server.rs` | list / supervisor / confirm sections. |
| `tests/progress.rs` | the progress/cancel section (raw JSON-RPC driver). |
| `tests/common/mod.rs` | the shared scripted client + harnesses. |
| `tests/fixtures/fake_bridge.py` | the scripted bridge for cargo test. |
