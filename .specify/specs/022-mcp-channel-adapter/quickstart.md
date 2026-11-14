# Quickstart — validating 022

## Prerequisites

- The repo checkout with `uv sync --frozen --extra dev` done (`.venv/`
  present).
- `rustup`. `interfaces/mcp/rust-toolchain.toml` selects the toolchain
  automatically.
- For the manual scenario only: a running Temporal (`TEMPORAL_HOST`) and an
  MCP client with form elicitation (e.g. the Claude Code CLI). No step
  spends model tokens.

## Automated (what CI runs)

```bash
python scripts/check_mcp.py      # fmt → clippy → cargo test → build --release → pytest -m mcp
uv run pytest tests/test_operator_bridge.py tests/test_operator_layering.py tests/test_task_queue.py -q
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/check_file_size.py --full
uv run pytest -q                 # diff FAILED ids vs .specify/specs/021-recall-snapshot-artifact/baseline-failures.txt
```

Expected:
- `check_mcp.py` ends `mcp gate: ok`. Without `cargo` and with `CI` unset,
  it prints `mcp gate: SKIPPED (cargo not found)` and exits 0.
- The fast tier introduces no FAILED id outside the baseline file.

## Manual end-to-end (operator machine)

1. `cargo build --release --manifest-path interfaces/mcp/Cargo.toml`
2. Add the client config from `contracts/mcp-tools.md` §Launch to the
   client. In Claude Code: `claude mcp add kroker -- <repo>/interfaces/mcp/target/release/kroker-mcp --repo <repo>`.
3. Ask "what's blocked in the factory?". Expect an `inbox` call; the text
   matches `python -m sdlc.cli inbox` for the same fleet.
4. Ask it to approve a pending gate. Expect a confirmation dialog showing the
   gate's own title/body/rows. Decline it: nothing changes (`get_run` still
   lists the key). Repeat and accept: the run advances, and the board/run
   history shows `reviewer=mcp:claude-code`.
5. Kill the client with `kill -9`. Expect no `sdlc.operator.bridge` process
   left (`pgrep -f sdlc.operator.bridge` is empty within 2 s).

Contracts: `contracts/mcp-tools.md`, `contracts/bridge-protocol.md`. Entities:
`data-model.md`.
