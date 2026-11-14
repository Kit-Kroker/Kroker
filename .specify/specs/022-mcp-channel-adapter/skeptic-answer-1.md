# SKEPTIC Review — Feature 022 (E-11 MCP Channel Adapter)

**Role**: SKEPTIC (read-only adversarial review)  
**Target**: `.specify/specs/022-mcp-channel-adapter/spec.md` (GATE 1 rulings, spec defaults, and tentative seam `(b)`).

---

## 1. Executive Verdict

Tentative seam `(b)` (Rust `rmcp` 3.10.0 stdio server + persistent `python -m sdlc.operator.bridge` child + dynamic `describe` tool list) is **viable only if** several structural traps are closed in `plan.md` before implementation begins. As currently sketched, it carries **four BLOCKERs** and **ten MUST-FIX-IN-PLAN** flaws:

- **BLOCKER-1 (Client elicitation reality & fail-closed lock-out)**: MCP elicitation is an optional client capability that major target clients (Claude Code, goose, many IDE agents) either do not implement or auto-accept/reject. Locking fail-closed elicitation without verifying client support risks shipping a server where **all three write tools are permanently bricked** in the primary target clients, or where a client silently auto-accepts and defeats the human gate.
- **BLOCKER-2 (Bridge composition via `interfaces/dashboard/api/main.py`)**: Importing `_start` from `interfaces/dashboard/api/main.py` executes module-level FastAPI `create_app()`, `FleetPoller`, `mount_chat()`, and `configure_logfire()`, loading `fastapi`, `starlette`, and `pydantic_ai` into the MCP child and violating FR-015.
- **BLOCKER-3 (Stdout framing corruption)**: Any third-party print, `logging` default handler, `warnings.warn`, or `temporalio` / `sqlite` stdout output inside `python -m sdlc.operator.bridge` corrupts the JSON-lines stream on `stdout` and kills the MCP session mid-call.
- **BLOCKER-4 (`Cargo.lock` + `tests/test_verify.py` CI/ratchet break)**: `scripts/check_file_size.py` checks `interfaces/` and only exempts `uv.lock` and `*-lock.json` — an unexempted `interfaces/mcp/Cargo.lock` will fail `--full` immediately. Worse, `tests/test_verify.py` (`test_every_ci_gate_is_in_verify`) fails CI if `.github/workflows/ci.yml` adds `cargo fmt` / `cargo clippy` / `cargo test` without matching entries in `scripts/verify.py`, which in turn breaks local `verify.py` on dev hosts that lack `cargo`.

---

## 2. Pressure-Testing LOCKED Decisions (GATE 1 & Spec Defaults)

*(Locked rulings cannot be overturned, so each entry identifies the sharpest concrete failure mode and the minimal mitigation required inside the locked boundary.)*

### L1. Server in Rust on official `rmcp` 3.10.0 (GATE 1 Q1)
- **Severity**: **MUST-FIX-IN-PLAN**
- **Failure scenario**: `interfaces/mcp/` introduces a second language toolchain (`rustc`/`cargo`) into a Python/Node repo where `cargo` is not installed on the dev host (`cargo: command not found` in spec §Seam Decision) and `pyproject.toml` only packages `src/`. Without a documented build/distribution path and pinned `rust-toolchain.toml` + bounded `rmcp = "~3.10"` + `Cargo.lock`, operators copying `client-config.example.json` hit immediate binary-not-found or `rmcp` 0.x/3.x minor drift. Furthermore, `rmcp` 3.10.0's `Peer::elicit` / `create_elicitation` errors on protocol `2026-07-28+`, requiring dual-path handling (`InputRequiredResult` / MRTR).
- **Minimal mitigation**: Pin `interfaces/mcp/rust-toolchain.toml`, use bounded `rmcp = "~3.10"` in `interfaces/mcp/Cargo.toml`, commit `Cargo.lock`, and implement both elicitation paths (pre-`2026-07-28` `Peer::elicit` and `2026-07-28+` `InputRequiredResult` MRTR) in the Rust server, or explicitly fail-closed with the negotiated protocol version in the directing error.

### L2. Write confirmation by MCP elicitation, fail-closed (GATE 1 Q2)
- **Severity**: **BLOCKER**
- **Failure scenario A — Target clients lack elicitation**: An operator configures `interfaces/mcp` in Claude Code or goose, asks "approve the plan gate on feature-x", and the assistant calls `decide_gate`. Because the client did not advertise `capabilities.elicitation` in `initialize` (or rejects server->client `elicitation/create` with `-32601 Method not found` / unsupported), the Rust server fails closed and returns the directing error ("use dashboard or CLI"). **Every write verb (`decide_gate`, `answer_question`, `start_run`) is dead on arrival** in the exact clients named in US-2 / Assumption 1.
- **Failure scenario B — Client auto-accepts elicitations**: An MCP client or wrapper configured with `--dangerously-skip-permissions` / auto-approve mode intercepts `elicitation/create` and returns `action: "accept"` programmatically without rendering `default_render`'s pending text to a human. The server receives `accept` and fires the FR-302 signal (`submit_gate_decision`). Fail-closed only protects against *absence* of elicitation capability; it **cannot** distinguish a human clicking "Accept" from a client auto-accepting on the human's behalf.
- **Minimal mitigation**:
  1. **Verify real client support before locking `plan.md`**: Test `elicitation/create` (and `2026-07-28+` MRTR `InputRequiredResult` if negotiated) against the exact versions of Claude Code and goose in scope, and document the minimum client versions in `interfaces/mcp/README.md`.
  2. **Require explicit confirmation field in the elicitation schema**: Rather than an empty or boolean-defaulted form, require a non-defaulted confirmation field (e.g., `confirm: bool` with no default, or typing the gate/key name for destructive rejects) so naive auto-fillers that submit `{}` fail schema validation / fail closed.
  3. **State the trust boundary honestly in `spec.md` / `README.md`**: Elicitation delegates human presentation to the MCP client; a client configured to auto-accept bypasses human review by client policy, not server defect.

### L3. All twelve operator verbs exposed (GATE 1 Q3)
- **Severity**: **MUST-FIX-IN-PLAN**
- **Failure scenario**: `follow(deps, run_id=None, timeout_s=60)` blocks for up to 120 s. In `src/sdlc/operator/tools.py:416`, `deps.note_follow()` increments `follow_calls` *before* waiting, and `follow` has no progress callback. If a client with a 30 s tool-call timeout cancels `follow` at 30 s, (a) the bridge's `asyncio` task may keep running or leak its `poller.subscribe()` queue, (b) `follow_calls` was already incremented even though the wait was cancelled, and (c) without `notify_progress` every ≤15 s (FR-010), clients with idle tool timeouts kill `follow` before `timeout_s` expires.
- **Minimal mitigation**: Drive `follow`'s wait in the bridge with a cancellation token wired from Rust's `RequestHandlerExtra` / `CancellationToken` (cancelling the in-flight bridge request on MCP `notifications/cancelled`), emit periodic bridge->Rust heartbeat/progress events every ≤15 s so Rust calls `notify_progress` when `progressToken` is present, and ensure `async with deps.poller.subscribe()` exits cleanly on `CancelledError`.

### L4. Spec defaults
- **Stdio transport only now (FR-012)**: **ACCEPTABLE** — no network listener, inherits process-owner boundary.
- **Actor `mcp:<clientInfo.name normalised>` fallback `mcp:local`, `GateDecision.reviewer` only (FR-007)**: **MUST-FIX-IN-PLAN**
  - **Failure scenario A — Spoofing / collision**: A local client passes `clientInfo.name = "Claude Code!!!"` vs `"claude-code"` -> both normalise to `mcp:claude-code`; or passes `clientInfo.name = "../../admin"` -> must normalise strictly to `[a-z0-9-]` (collapsing/stripping anything else) and truncate to 40 chars. Worse, `SDLC_MCP_ACTOR` override allows any local process to stamp `mcp:trusted-ci` (mitigated only by OQ-11 single-operator posture).
  - **Failure scenario B — `answer_question` audit gap**: In `src/sdlc/channels/contract.py:107-108` and `182-186`, `ActorChannel.translate` only stamps `call.decision.reviewer = self.actor` when `call.decision is not None` (`submit_gate_decision`). For `ClarifyPending` (`answer_question`), `SignalCall` has only `question_id` and `answer` — `self.actor` is **dropped** and never reaches the workflow signal or audit trail, contradicting SC-005 ("100% of MCP-originated decisions carry an `mcp:` actor in the audit trail") unless SC-005 is scoped to gate decisions or `answer_question` logs/records actor separately.
  - **Minimal mitigation**: Enforce regex `^mcp:[a-z0-9-]{1,40}$` on both normalised `clientInfo.name` (collapsing runs of invalid chars to `-`, stripping leading/trailing `-`, falling back to `mcp:local` if empty) and `SDLC_MCP_ACTOR` (rejecting invalid overrides at startup). Clarify SC-005 / FR-007 that `GateDecision.reviewer` applies to gate decisions (`decide_gate`), while `answer_question` carries no `reviewer` field on FR-302's signal.
- **OQ-11 localhost/unauthenticated posture (FR-014)**: **ACCEPTABLE** — stdio has no socket, strictly narrower than `:8500`.
- **Follow streak scoped per MCP session (FR-009)**: **ACCEPTABLE** — one child `OperatorDeps` per stdio session naturally isolates the streak, provided `preview` calls do **not** call `deps.note_other_tool()` (see S1 below).
- **32 KB paging unchanged (FR-011)**: **ACCEPTABLE** — `read_artifact` returns `ArtifactRead` directly.
- **No `thaw_tests` / `budget_usd` exposure (FR-008)**: **MUST-FIX-IN-PLAN** — In `tools.py`, `decide_gate` already omits `thaw_tests` and `start_run` already omits `budget_usd`, so dynamic schema generation from `tools.py` preserves this. However, **explicitly assert their absence** in `tests/test_operator_mcp_parity.py` so a future `tools.py` edit cannot silently expose them over MCP.

---

## 3. Pressure-Testing Tentative Seam `(b)` (Rust `rmcp` + Persistent Python Bridge)

### S1. TOCTOU between `preview` and write (`decide_gate` / `answer_question` / `start_run`)
- **Severity**: **BLOCKER**
- **Failure scenario**:
  1. At `T0`, client calls `decide_gate(run_id="feature-x", key="plan:1", outcome="approve")`. Rust asks bridge for `preview(run_id, key)`. Bridge calls `resolve_key(handle, "plan:1")` and returns `default_render(pending)` ("Gate: plan (round 1)").
  2. Rust sends MCP elicitation to the human and blocks for 45 seconds.
  3. At `T1`, another operator on the dashboard clicks **Reject** (or **Revise**, advancing to round 2; or answers the clarify question).
  4. At `T2`, the MCP operator clicks **Accept**. Rust now calls bridge `decide_gate(run_id="feature-x", key="plan:1", outcome="approve")`.
  - For `StageGatePending` / `MergeGatePending`: `d.key` embeds `round` (`gate_key(gate, round)`), so `resolve_key` raises `NoMatch` -> `ToolError` (safe, *except* the user just confirmed a stale preview and gets an error instead of `confirmed=false`, and if the round hadn't changed—e.g., `TaskEscalationPending` or a `ClarifyPending` whose `question`/`why_it_matters` changed—the key could still match different content).
  - For `start_run`: at `T0` `preview` checks `fleet_pending_cap()` and sees 4/5 pending; at `T2` another run starts (5/5) or `feature-x` already exists; `start_run` then fails after human confirmation.
  - **Subtle streak bug**: If `preview` touches `tools.py` or calls `note_other_tool()`, then calling `decide_gate` and **declining** elicitation silently resets `deps.follow_calls` to `0` even though no tool executed!
- **Minimal mitigation**:
  - `preview` must be **purely read-only** and MUST NOT call `note_other_tool()` (only actual verb execution calls it).
  - Compute a SHA-256 digest of the `preview` payload (`rendered_text` + `key` + `round`/`attempts` if present) in `preview`, and pass `expected_preview_hash` into the post-elicitation write call. In the bridge, re-fetch `pending = await resolve_key(handle, key)` immediately before `submit(...)` and verify the digest still matches; if it changed, abort without signalling and return a clear `ToolError` ("pending item changed while waiting for confirmation; re-read inbox and retry").

### S2. MRTR `requestState` forgery, replay, and binding (Protocol `2026-07-28+`)
- **Severity**: **BLOCKER**
- **Failure scenario**: On MCP protocol `2026-07-28+`, `Peer::elicit` errors because server-to-client requests are forbidden; the server returns `InputRequiredResult` (MRTR) with an HMAC-sealed `requestState`, and the client retries `tools/call` with `input_responses` + `requestState`.
  1. **Replay**: Client retries the same `requestState` + `input_responses` twice (e.g., network/client retry or malicious LLM replaying a previously-approved `requestState` token). Without single-use tracking, the server re-executes `decide_gate` or `start_run` a second time!
  2. **Cross-tool / cross-argument substitution**: If `requestState` only seals `{confirmed: true}` or `{nonce}` without binding the exact `tool_name`, canonical `arguments` (`run_id`, `key`, `outcome`, `text` / `title`, `mode`, `repo`), and `preview_hash`, an LLM client can take a `requestState` issued for `decide_gate(outcome="revise")` or `start_run(title="safe")` and attach it to a retry of `decide_gate(outcome="approve")` or `start_run(title="other")`.
  3. **Cross-session / key persistence**: If the HMAC key is static or predictable, tokens forge across sessions; if it's ephemeral per process, that's good for stdio, *provided* it's CSPRNG (`getrandom` / `os.urandom`) per process startup.
- **Minimal mitigation**:
  - Generate a 256-bit CSPRNG HMAC key once per Rust process startup (`rmcp` stdio session).
  - Seal inside `requestState`: `{jti (uuid/nonce), tool_name, canonical_args_sha256, preview_sha256, exp (unix_ts + 300)}`.
  - Maintain a bounded `HashSet<jti>` (or `HashMap<jti, exp>`) of **consumed/outstanding** nonces in the Rust session state: reject missing, expired, signature-invalid, argument-mismatched, or already-consumed `jti`s (single-use, fail-closed).

### S3. Does `(b)` truly leave "zero per-verb Rust"?
- **Severity**: **MUST-FIX-IN-PLAN**
- **Failure scenario**: The claim "no per-verb Rust code" breaks down in **four** concrete places:
  1. **`follow` progress + cancellation**: `follow` is the only long-polling verb (up to 120 s) requiring `notify_progress` every ≤15 s (FR-010) and cancellation propagation.
  2. **Write `preview` + elicitation**: Only the 3 write verbs (`start_run`, `answer_question`, `decide_gate`) trigger the `preview` -> elicit -> execute flow; reads must skip it. (Can be data-driven via a `requires_confirmation: bool` flag in `describe`, *except* `preview` error handling and `ToolAnnotations` still branch on it.)
  3. **`ToolAnnotations`**: `readOnlyHint: true` for the 9 reads vs `readOnlyHint: false, destructiveHint: true` for the 3 writes (FR-005).
  4. **Typed structured output (`FR-003`)**: `ArtifactRead`, `ChangeReport`, and `ReplyReceipt` must advertise `outputSchema` in `tools/list` and return `structuredContent` + JSON text in `tools/call`, whereas the 9 text verbs return plain `TextContent` without `outputSchema`.
  5. **`confirmed=false` vs `isError`**: `ReplyReceipt(confirmed=false)` MUST be `isError: false` (FR-006), whereas `ToolError` MUST be `isError: true` (FR-004).
- **Minimal mitigation**: Make `describe` return explicit per-tool metadata (`name`, `description`, `input_schema`, `output_schema: Option<Schema>`, `read_only: bool`, `requires_confirmation: bool`, `supports_progress: bool`) and have Rust's generic dispatcher branch on those **metadata flags**, not hardcoded verb names. Update `plan.md` to state honestly: "zero per-verb Rust *logic*, with generic metadata-driven handling for confirmation, `outputSchema`, `ToolAnnotations`, and progress streaming."

### S4. Bridge composition needing `_start` from `interfaces/dashboard/api/main.py`
- **Severity**: **BLOCKER**
- **Failure scenario**: `interfaces/dashboard/api/main.py` has top-level side effects on import:
  - Line 42: `app = create_app()` (boots SQLite board FastAPI app)
  - Line 53: `poller = FleetPoller(_connect)`
  - Line 65: `app.include_router(create_router(...))`
  - Line 102: `mount_chat(app, poller)` (if `SDLC_CHAT_ENABLED=1`, calls `configure_logfire()`, builds `pydantic_ai` agent, mounts `/chat`)
  - Top-level imports: `fastapi`/`starlette` (via `board.api`, `dashboard.api`) and `pydantic_ai` (via `sdlc.operator.agent`).
  If `bridge.py` imports `_start` from `interfaces.dashboard.api.main`, every MCP session boots the dashboard ASGI app and chat agent inside the MCP child, violating FR-015 ("MUST NOT be imported at dashboard or worker boot" / framework isolation) and failing if `SDLC_CHAT_ENABLED=1` and chat assets are missing or slow.
- **Minimal mitigation**: Extract `_connect` and `_start` (or a `build_operator_runtime()` factory returning `(poller, BoardStore, starter)`) into a tiny framework-free module (e.g., `src/sdlc/workflows/runtime.py` or `src/sdlc/operator/runtime.py` — outside `tools.py`!) that imports only `temporalio`, `sdlc.dashboard.fleet`, `sdlc.graph.start`, `sdlc.workflows.graph`, `sdlc.workflows.graph_catalog`, and `sdlc.worker`. Have `interfaces/dashboard/api/main.py` and `bridge.py` both import it from there.

### S5. `temporalio` in the bridge vs `tests/test_operator_layering.py`
- **Severity**: **ACCEPTABLE** (with care)
- **Analysis**: `tests/test_operator_layering.py` checks two things:
  1. `test_only_agent_py_may_name_a_framework` scans `src/sdlc/operator/*.py` (except `agent.py`) for `FORBIDDEN = ("pydantic_ai", "fastapi", "starlette")` — `temporalio` is **not** in `FORBIDDEN`.
  2. `test_importing_tools_does_not_load_a_framework_transitively` runs `import sdlc.operator.tools` in a fresh Python subprocess and asserts `pydantic_ai`, `fastapi`, `starlette`, and `temporalio` are **not** in `sys.modules`.
  As long as `tools.py` never imports `bridge.py` (or `runtime.py`), `test_operator_layering.py` passes unmodified.
- **Minimal mitigation**: Keep `bridge.py` as a leaf consumer of `tools.py` (never imported by `tools.py` or `__init__.py`), and ensure `bridge.py` never imports `interfaces.dashboard.api.main`, `fastapi`, `starlette`, or `pydantic_ai`.

### S6. Stdout framing corruption (JSON-lines over child `stdout`)
- **Severity**: **BLOCKER**
- **Failure scenario**: The Rust server speaks JSON-lines (`{id, verb, args, actor}\n` -> `{id, ok, result|error_message}\n`) over the Python child's `stdin`/`stdout`. Any stray `print(...)`, `logging` output (if `StreamHandler` defaults to `stderr`, good, *unless* a library writes to `sys.stdout`), `warnings.warn`, `temporalio` native/SDK log, or `click`/`rich` output writing to `sys.stdout` injects non-JSON bytes into the framing pipe. Rust's `serde_json::from_str` fails on the line, desynchronizes or aborts the bridge, and breaks the MCP session.
- **Minimal mitigation**: At the very top of `bridge.py` (before importing `sdlc.*` or `temporalio`), save `proto_out = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")`, redirect fd `1` to fd `2` (`os.dup2(2, 1)`) and rebind `sys.stdout = sys.stderr`, so **nothing** in Python or C extensions can ever write to the protocol pipe except explicit writes to `proto_out`. (Do the exact same `fd 0` hygiene if anything reads stdin.) Also enforce a newline-delimited protocol with `flush()` after every JSON line and a max-line-size cap in Rust.

### S7. Orphan Python child processes
- **Severity**: **MUST-FIX-IN-PLAN**
- **Failure scenario**: When the MCP client (Claude Code, goose) crashes, exits abruptly, or kills the Rust MCP server with `SIGKILL`, the Rust process cannot run `Drop` to kill the Python child. If `bridge.py` only exits on `stdin` EOF *while* `asyncio` is blocked or `FleetPoller` has background tasks running, the Python child can linger as an orphan holding open Temporal gRPC connections and SQLite handles. On Linux, even closing `stdin` might not wake a blocked thread if the event loop isn't reading `stdin` asynchronously.
- **Minimal mitigation**:
  - In `bridge.py`, read `stdin` via `asyncio` (`loop.connect_read_pipe`) and on EOF **immediately** cancel all in-flight tasks, call `await poller.aclose()`, and exit.
  - On Linux, also set `PR_SET_PDEATHSIG` (`prctl(PR_SET_PDEATHSIG, SIGTERM)`) in the Rust `Command::pre_exec` (or Python startup) so the kernel delivers `SIGTERM` to the child immediately if the Rust parent dies for any reason (including `SIGKILL`).
  - In Rust, configure `kill_on_drop(true)` on `tokio::process::Command`.

### S8. Parity test honesty (`tests/test_operator_mcp_parity.py`)
- **Severity**: **MUST-FIX-IN-PLAN**
- **Failure scenario**: Under seam `(b)` with a dynamic `describe` tool list, if `test_operator_mcp_parity.py` mocks the bridge or only tests Python `tools.py` directly, it becomes **tautological** — it proves Python matches Python while leaving Rust's `rmcp` tool registration, JSON Schema forwarding, `isError` mapping, `structuredContent` serialization, `ToolAnnotations`, and elicitation fail-closed path completely untested. Conversely, if `test_operator_mcp_parity.py` requires `cargo build` at pytest time on dev hosts without `cargo` (`cargo: command not found`), it breaks `uv run pytest -q`.
- **Minimal mitigation**:
  - Test the **real compiled Rust binary** over stdio (`mcp` JSON-RPC `initialize` -> `tools/list` -> `tools/call`) with a **fake-deps bridge mode** (e.g., `SDLC_MCP_BRIDGE_MODULE` or test harness wrapper injecting fake `FleetPoller` / in-memory `BoardStore` / fake `starter`), asserting:
    1. `tools/list` membership == `agent.READ_TOOLS + agent.WRITE_TOOLS` (12 tools), `deps` absent from every `inputSchema`, `thaw_tests` absent from `decide_gate`, `budget_usd` absent from `start_run`.
    2. Byte-identical text output for all 9 text-returning verbs vs calling `tools.<verb>(deps, ...)` directly.
    3. `structuredContent` + `outputSchema` parity for `ArtifactRead`, `ChangeReport`, `ReplyReceipt`.
    4. `ToolError` -> `isError: true` verbatim, and `confirmed=false` -> `isError: false`.
    5. Write without elicitation -> `isError: true` directing error and **zero** signals/starts.
  - Gate the Rust-binary-spawning test cleanly (e.g., `pytest.mark.mcp` or skip/fail explicitly per CI vs local `cargo` availability—see S10).

### S9. `Cargo.lock` size vs `scripts/check_file_size.py` 1000-line ceiling
- **Severity**: **BLOCKER** (already flagged in spec FR-017, must not be missed)
- **Failure scenario**: `interfaces/mcp/Cargo.lock` for `rmcp` + `tokio` + `serde` + `schemars` + `hmac`/`sha2` will easily exceed 1,000 lines (typically 1,500–3,000+ lines). `scripts/check_file_size.py:37` scopes `interfaces/` and `EXEMPT_PATTERNS` (lines 47–59) only exempts `uv.lock` and `*-lock.json` — **not** `Cargo.lock`. Running `scripts/check_file_size.py --full` will fail CI immediately.
- **Minimal mitigation**: Add `"Cargo.lock"` (or `"interfaces/mcp/Cargo.lock"`) to `EXEMPT_PATTERNS` in `scripts/check_file_size.py` in the same commit that introduces `Cargo.lock`.

### S10. CI cost of a Rust job & `tests/test_verify.py` coupling
- **Severity**: **BLOCKER**
- **Failure scenario**:
  1. `tests/test_verify.py` (`test_every_ci_gate_is_in_verify`) parses every `run:` line in `.github/workflows/ci.yml` (except `pip install` / `uv sync`) and **fails `pytest`** if `scripts/verify.py` doesn't have a matching gate! Adding `cargo fmt`, `cargo clippy`, and `cargo test` directly as `run:` steps in `ci.yml` will break `tests/test_verify.py` unless `scripts/verify.py` also includes them.
  2. If `scripts/verify.py` includes `cargo` gates unconditionally, developers on machines without `cargo` (`cargo: command not found`) cannot pass `scripts/verify.py`.
  3. A cold `cargo clippy` + `cargo test` of `rmcp` + `tokio` on `ubuntu-latest` adds ~2–5 minutes of build time per PR unless `Swatinem/rust-cache` (or `actions/cache` on `~/.cargo` and `interfaces/mcp/target`) is configured.
- **Minimal mitigation**:
  - Follow the `ui` job pattern in `.github/workflows/ci.yml:74-78`: put Rust CI checks behind a single wrapper script `python scripts/check_mcp.py` (one `run:` line in `ci.yml`, one matching gate in `scripts/verify.py`), and use `Swatinem/rust-cache` in the `mcp` CI job.
  - Decide explicitly in `plan.md` whether `cargo` is a required local dev prerequisite or if `check_mcp.py` skips with a clear message when `cargo` is absent locally (while failing if `CI=true`).

---

## 4. Summary Matrix

| ID | Area | Severity | Concrete Failure | Minimal Mitigation |
|---|---|---|---|---|
| L1 | Rust + `rmcp` 3.10.0 | MUST-FIX-IN-PLAN | Missing local toolchain, `0.x`/`3.x` drift, `2026-07-28+` `elicit` error | `rust-toolchain.toml`, `rmcp = "~3.10"`, `Cargo.lock`, dual elicitation/MRTR path |
| L2 | Fail-closed elicitation | BLOCKER | Claude Code/goose lack elicitation -> all writes bricked; or auto-accept bypasses gate | Verify client support pre-plan; non-defaulted confirmation field; document client trust boundary |
| L3 | All 12 verbs (`follow`) | MUST-FIX-IN-PLAN | Client timeout kills `follow` without progress; cancelled wait leaks queue & burns streak | Bridge->Rust progress heartbeat (≤15 s) + `notifications/cancelled` propagation |
| L4 | Actor & `answer_question` | MUST-FIX-IN-PLAN | `clientInfo.name` collisions/bad chars; `answer_question` drops `actor` on `SignalCall` | Strict `^mcp:[a-z0-9-]{1,40}$` normalisation; scope SC-005 or log `answer_question` actor |
| L4b | `thaw_tests` / `budget_usd` | MUST-FIX-IN-PLAN | Future `tools.py` edit could silently expose forbidden fields via dynamic `describe` | Explicit negative assertion in `test_operator_mcp_parity.py` |
| S1 | Preview->Write TOCTOU | BLOCKER | Pending item changes/closes during elicitation; declined `preview` resets `follow` streak | Pure read-only `preview` (no `note_other_tool`); pass `preview_hash` and verify before `submit` |
| S2 | MRTR `requestState` | BLOCKER | Replay executes write twice; unsealed args allow tool/arg swap after confirm | Per-process CSPRNG HMAC sealing `{jti, tool, args_hash, preview_hash, exp}` + single-use `jti` set |
| S3 | "Zero per-verb Rust" | MUST-FIX-IN-PLAN | Progress, confirmation, `ToolAnnotations`, `outputSchema`, `isError` vs `confirmed=false` | Metadata flags from `describe` driving generic Rust dispatch; update claim in `plan.md` |
| S4 | Importing `_start` from `main.py` | BLOCKER | Importing `main.py` boots FastAPI, `FleetPoller`, `mount_chat`, `pydantic_ai` in bridge | Extract `_connect`/`_start` to framework-free `runtime.py`; both `main.py` and `bridge.py` import it |
| S5 | `temporalio` vs layering test | ACCEPTABLE | `tools.py` must not transitively import `temporalio` or frameworks | Keep `bridge.py` as leaf consumer of `tools.py`; never imported by `tools.py` |
| S6 | Stdout framing | BLOCKER | Any library `print`/stdout write corrupts JSON-lines and kills MCP session | `dup2(2, 1)` + `sys.stdout = sys.stderr` before imports; dedicated fd for JSON-lines |
| S7 | Orphan Python children | MUST-FIX-IN-PLAN | `SIGKILL` on Rust leaves Python child + Temporal `FleetPoller` running | `PR_SET_PDEATHSIG(SIGTERM)` + `kill_on_drop(true)` + async stdin EOF cleanup |
| S8 | Parity test honesty | MUST-FIX-IN-PLAN | Testing mocked bridge is tautological; misses Rust `rmcp` wire behavior | Spawn real Rust binary over stdio against fake-deps bridge in `test_operator_mcp_parity.py` |
| S9 | `Cargo.lock` vs 1000-line ceiling | BLOCKER | `check_file_size.py --full` rejects `interfaces/mcp/Cargo.lock` (>1000 lines) | Add `"Cargo.lock"` to `EXEMPT_PATTERNS` in `scripts/check_file_size.py` |
| S10 | CI Rust job & `test_verify.py` | BLOCKER | New `ci.yml` `run:` lines fail `test_every_ci_gate_is_in_verify`; cold builds slow | Single `python scripts/check_mcp.py` gate in `ci.yml` + `verify.py` + `rust-cache` |
