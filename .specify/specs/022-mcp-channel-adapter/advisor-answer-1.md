# 022 advisor consult: seam choice and open decisions

**Recommendation: (b), with a persistent child process, a dynamic tool list, and a small Python preview step.** The ranking is (b), then (a′), then (c). I read `spec.md`, `operator/{tools,deps,errors,agent}.py`, `channels/contract.py`, `interfaces/dashboard/api/main.py`, `scripts/check_file_size.py` and the layering test. I took the rmcp 3.10 facts from your brief and did not re-check docs.rs.

## Why (b)

- **Rust carries no per-verb code.** The bridge answers a `describe` request by generating, from the verb signatures and docstrings, each tool's name, description, input schema, output schema and read-only or destructive flag.
- **Rust is a generic `ServerHandler`.** It implements `list_tools` and `call_tool` by forwarding to the bridge, so a changed verb signature, docstring or `ToolError` sentence needs no Rust edit.
- **FR-002 membership falls out of the design.** A Python test compares `describe` against `agent.py`'s `READ_TOOLS`/`WRITE_TOOLS`.
- **The follow brake needs no Rust.** One MCP session is one bridge process, so `OperatorDeps.follow_calls` is already session-scoped (FR-009). `note_other_tool` already handles the reset.
- **Why not (a′).**
  - A `/api/operator/{verb}` family in the dashboard router is imported at dashboard boot. That breaks the intent of FR-015 and SC-006.
  - It needs the dashboard running.
  - It adds a localhost write route.
  - Session scoping has to ride on a header.
  - It runs the same Python as (b) over a worse transport.
- **Why not (c).** The spec's own inventory already settles it

---

**Recovery note (spec lead, 2026-11-14):** the advisor seat answered in full once, but every later turn (asked to write the answer to file) failed with an API `reasoning_extraction` error and the terminal scrollback no longer holds the first answer. The text above is the 1608-byte partial file write. Also recovered from the visible terminal tail before it was lost: risk 3 = child-process hygiene (stray stdout writes corrupt framing: reserve the real stdout fd for frames and redirect sys.stdout to stderr; orphaned children after client kill -9; uv + Python import startup latency; Rust side keeps stdout MCP-only with tracing on stderr). Ranking recorded: (b) > (a') > (c). Risks 1-2 and the per-decision answers were not recoverable; the plan resolves those decisions itself and the skeptic review covers the same ground adversarially.
