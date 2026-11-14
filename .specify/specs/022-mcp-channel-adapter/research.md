# Research — 022 MCP channel adapter (E-11)

Phase 0 output. Each entry: **Decision / Rationale / Alternatives**. Sources:
docs.rs `rmcp` 3.10.0 and `rmcp-macros` 3.10.0 (released 2026-11-12), the
`modelcontextprotocol/rust-sdk` README, `examples/servers/src/{elicitation_stdio,mrtr}.rs`,
`examples/servers/src/common/progress_demo.rs` and `crates/rmcp/Cargo.toml`, all
read 2026-11-14. Consult records: `advisor-*-1.md`, `skeptic-*-1.md`.

## R1 — What rmcp 3.10.0 supports today (GATE 1 mandate)

| Capability | Verified API | Consequence |
|---|---|---|
| stdio server | feature `transport-io`; `service.serve(stdio())`, `.waiting()` | FR-012 met. stdout belongs to MCP framing; tracing must go to stderr (the elicitation example's default `tracing_subscriber::fmt()` writes to stdout, which is the trap to avoid). |
| Tool schema generation | `#[tool]`, `#[tool_router]`, `#[tool_handler]` (features `macros`, `server`); input schema from `Parameters<T>` via `schemars` | Not used. A **manual `ServerHandler`** (`list_tools`, `call_tool -> Result<CallToolResponse, McpError>`) serves a dynamic tool list from the bridge (R3). |
| Tool annotations | `model::ToolAnnotations` (`#[non_exhaustive]`, builders `new().read_only(..).destructive(..).idempotent(..).open_world(..)`, fields `read_only_hint`, `destructive_hint`, `idempotent_hint`, `open_world_hint`, `title`); the docs call them **hints** that clients must not trust | FR-005's annotation half is met. They are advisory only, so annotations never replace the confirmation step. |
| Structured output | `Json<T>` wrapper; `outputSchema`/`structuredContent` (2026-07-28 allows any JSON Schema type / JSON value) | FR-003 met for `ArtifactRead`, `ChangeReport`, `ReplyReceipt`. |
| Progress | `Peer::notify_progress(ProgressNotificationParam)`; the token is read from `ctx.meta["progressToken"]` (`NumberOrString`) | FR-010 met. Progress is a notification, not a server-to-client request, so the 2026-07-28 restriction does not touch it. |
| Cancellation | `ServerHandler::on_cancelled(CancelledNotificationParam, ..)`; `Peer::notify_cancelled` | FR-010 met. The cancel is forwarded to the bridge (contracts/bridge-protocol.md §cancel). |
| Client identity | `Peer::peer_info() -> Option<Arc<InitializeRequestParams>>` (the handshake snapshot); `initialize` can be overridden and calls `negotiate_initialize` | FR-007 reads `clientInfo.name` from here. The **negotiated protocol version is captured in the `initialize` override** (the docs name no other accessor). |
| Elicitation, protocol < 2026-07-28 | feature `elicitation` (+ `schemars`): `Peer::elicit<T>` / `elicit_with_timeout`, `create_elicitation`, `supported_elicitation_modes() -> HashSet<ElicitationMode>`; `elicit_safe!(T)`; errors `ElicitationError::{UserDeclined, UserCancelled, ParseError, NoContent, Service, CapabilityNotSupported(url mode)}` | Path E1 (R4). |
| Elicitation, protocol ≥ 2026-07-28 | the docs for `elicit`, `create_elicitation` and their timeout variants say they *"Errors on protocol 2026-07-28 or later, which forbids server-to-client requests"*. Instead `call_tool` returns `CallToolResponse::InputRequired(InputRequiredResult::new(Some(InputRequests{"confirm": InputRequest::Elicitation(ElicitRequest)}), Some(sealed)))`, and the client retries with `request_state` + `input_responses`. `RequestStateCodec::try_new(key)`, `seal_json`, `open_json` need feature `request-state` (pulls `hmac`, `zeroize`, `base64`; `sha2 0.11` is always compiled) | Path E2 (R4). Without E2 the server would brick writes on every up-to-date client. |
| Streamable HTTP | `transport-streamable-http-server` (Tower service) | Available for FR-013 later; not built now. |

**Client reality (web, 2026-11-14, unverified against Anthropic docs):** the
Claude Code CLI advertises form-mode elicitation and renders a terminal
dialog. Open issues report form requests auto-declined ("print mode") in
some TUI/VS Code sessions, and Claude Code hooks can auto-answer
elicitations. Claude Desktop and claude.ai web reportedly do not support
elicitation. Under fail-closed (GATE 1 Q2), an auto-decline means *no
effect*, which is safe but annoying. An auto-accept configured by the
operator is a client policy that bypasses the human gate. This trust
boundary is documented in `interfaces/mcp/README.md` (skeptic L2.3) and
cannot be fixed server-side.

## R2 — Seam re-cost for all twelve verbs (GATE 1 mandate)

Twelve verbs: nine reads (`list_runs`, `get_run`, `inbox`, `follow`,
`list_projects`, `get_project`, `list_tasks`, `project_events`,
`read_artifact`) and three writes (`start_run`, `answer_question`,
`decide_gate`).

| | (a′) Rust shim → new dashboard `/api/operator/{verb}` routes | **(b) Rust + persistent Python verb bridge (chosen)** | (c) Rust native |
|---|---|---|---|
| Python one-time | generic dispatch route + describe route + preview route, mounted fail-soft; session table keyed by header for the follow streak | `src/sdlc/operator/bridge.py` (framing, describe, preview, dispatch) + `runtime.py` extraction | none |
| Rust one-time | generic `ServerHandler`, HTTP client, elicitation E1+E2, progress (no long-poll progress over plain HTTP without SSE work) | generic `ServerHandler`, child supervision, elicitation E1+E2, progress/cancel forwarding | 12 verb bodies; Temporal Rust client decoding `RunState`/`PendingDecision` JSON written by `pydantic_data_converter`; sqlite board reads + blob paging; `render.py`; `errors.py` vocabulary; follow fingerprint + brake; FR-302 resolve/submit/verify; B4 cap; `slug`; `build_run_input` (graph selection, registry, validation: **not portable**, since it loads the Python agent registry) |
| Per-verb-change cost, permanent | 0 Rust, 1 Python | **0 Rust, 1 Python** | 1 Python + 1 Rust, kept in lock-step by tests forever |
| New runtime prerequisite | dashboard up on :8500 | repo checkout + `.venv` (same as the CLI) | Temporal + board sqlite reachable from Rust |
| New attack surface | localhost unauthenticated **write** route family (amends OQ-11's footprint) | none: stdio pipes owned by the operator's user | none |
| New failure modes | dashboard down → every tool fails; header-keyed session table leaks; boot import into dashboard (FR-015/SC-006 risk) | child crash/orphan, stdout framing corruption, startup latency (mitigated in R5–R7) | silent drift between surfaces; JSON wire-shape drift on every pydantic model change |
| `start_run` feasibility | yes | yes | **no without re-architecting**: run-input building is Python-only |

**Decision:** (b). **Rationale:** it is the only Rust seam where a verb
change still lands once. It adds no network surface, and it doesn't need the
dashboard running. (c) cannot implement `start_run` without porting graph
selection and the registry, and it would double every verb forever. (a′)
runs the same Python as (b) but over a worse transport, with a new
unauthenticated write route. **Alternatives:** (a′), (c) as above. The
original (a), over the existing JSON routes, is dominated by (a′), because
it still lacks `follow` and paged `read_artifact` and re-implements
rendering. (d) was overruled at GATE 1.

## R3 — Generic, metadata-driven dispatch (skeptic S3)

**Decision:** "zero per-verb Rust *logic*". The bridge's `describe` returns,
per tool: `name`, `description` (the docstring), `input_schema` (the
signature minus `deps`, generated by pydantic), `output_schema` (or null for
text verbs), `read_only`, `confirm` (`none` | `pending` | `start`),
`progress` (bool). Rust branches only on those flags. The membership tuples
`READ_TOOLS`/`WRITE_TOOLS` **move from `agent.py` into `tools.py`**, so
chat, bridge and tests read one definition (FR-002 by construction);
`agent.py` re-imports them. **Alternatives:** the `#[tool]` macros per verb
(twelve Rust stubs to keep in sync, rejected); a membership list hard-coded
in the bridge (drift, rejected).

## R4 — Write confirmation: dual path, fail-closed, TOCTOU-safe (GATE 1 Q2; skeptic L2, S1, S2)

**Decision:**

1. For a `confirm != none` tool, Rust first sends the bridge `preview`. It is
   pure-read and **does not call `note_other_tool`**, so a declined write
   cannot reset the follow streak. It returns `{message, digest}`.
   - For `pending`, `message` is `default_render(pending)` (title, body,
     rows) plus the proposed outcome and text.
   - For `start`, `message` is the title, mode, repo, description and the
     current fleet-cap state.
   - `digest = sha256(canonical JSON of {tool, args, rendered decision})`.
   - Preview failures (stale key, wrong reply kind) come back as the verb's
     own `ToolError` wording, before the human is bothered.
2. **E1** (negotiated version < 2026-07-28 and the client advertised
   elicitation): `peer.elicit_with_timeout::<Confirm>(message, 300 s)`.
   `Confirm { confirm: bool }` is required and has **no default**, so a
   client that auto-fills `{}` fails validation and therefore fails closed.
3. **E2** (≥ 2026-07-28): return `InputRequired` with the same form. Its
   `requestState` is sealed with a per-process 256-bit CSPRNG key and holds
   `{jti, tool, args_sha256, digest, exp: now+300}`. On retry, Rust rejects
   the call if the state is missing or tampered, expired, for another
   tool/args, or a `jti` it already consumed. Rust keeps a bounded in-session
   set of consumed `jti`s.
4. Accept with `confirm=true` → bridge `call` with `expect_digest`. The bridge
   **re-resolves the pending item and recomputes the digest immediately
   before invoking the verb**. On a mismatch it refuses with *"the pending
   item changed while you were confirming; re-read the inbox and retry"* and
   sends no signal. The residual micro-window between the re-check and
   `submit` is FR-302's existing race, reported as `confirmed=false`.
5. Decline, cancel, timeout, a schema failure, or no elicitation support (no
   capability on E1, or E2 unavailable) → error result: *"this write needs a
   human confirmation that this MCP client did not provide; nothing was
   changed. Use the dashboard or `python -m sdlc.cli` instead."* Per GATE 1,
   writes stay refused in that session until the client supports it.

**Alternatives:** relying on the client's own tool-permission prompt
(rejected at GATE 1). Supporting only E1 (bricks every 2026-07-28 client).
Supporting only E2 (bricks older clients, including most deployed today).

## R5 — Bridge composition without booting the dashboard (skeptic S4; measured)

Measured 2026-11-14 with `uv run python -c "import X"`:

| Module | Time | Loads |
|---|---|---|
| `sdlc.dashboard.fleet` | 0.35 s | none of the four |
| `sdlc.channels.transport` | 0.25 s | none |
| `sdlc.board.store` | 0.29 s | none |
| `sdlc.graph.start` | 0.30 s | none |
| `sdlc.workflows.graph_catalog` | 0.76 s | `temporalio` |
| `sdlc.worker` | 3.01 s | `pydantic_ai`, `temporalio` |
| `sdlc.workflows.graph` | — | **fails** with `RegistryError: role 'research' declares provider: exa but EXA_API_KEY is not set` (it loads the agent registry at import) |

The "four" are `pydantic_ai`, `fastapi`, `starlette` and `temporalio`.

**Decision:** a new `src/sdlc/operator/runtime.py` holds `connect()`
(Temporal client with `pydantic_data_converter`), `build_poller()`,
`start_graph(idea, cfg, wf_id)`, and `operator_deps(actor)`.
- `start_graph` passes the workflow **by name** (`"GraphWorkflow"`;
  `start_graph_run`'s `run` parameter is duck-typed and forwarded to
  `client.start_workflow`) and the task queue from a constant.
- `TASK_QUEUE = "ai-sdlc"` moves to a leaf module (`src/sdlc/task_queue.py`),
  and `worker.py` re-exports it. This avoids the 3 s worker import and the
  registry-at-import failure.
- `build_run_input` keeps its lazy registry load inside `start_run` only, so
  reads never need provider keys.
- `interfaces/dashboard/api/main.py` switches to `runtime.start_graph`, so
  `_start` exists once.
- A test pins that `GraphWorkflow.run`'s registered name equals
  `"GraphWorkflow"`.

**Alternatives:** importing `interfaces.dashboard.api.main` (boots the
FastAPI app and `mount_chat`, rejected). Duplicating `_start` (forbidden by
the spec).

## R6 — Process hygiene (skeptic S6, S7; advisor risk 3)

**Decision:**
- **Bridge stdout:** before importing anything from `sdlc`, the bridge does
  `proto = os.fdopen(os.dup(1), "wb")`, then `os.dup2(2, 1)` and
  `sys.stdout = sys.stderr`. Only `proto` carries frames: one JSON object
  per line, flushed per frame under a write lock. stdin is read with
  `asyncio` `connect_read_pipe`. On EOF it cancels in-flight tasks, awaits
  `poller.aclose()` and exits 0.
- **Rust side:** `tokio::process::Command` with `kill_on_drop(true)`, piped
  stdin/stdout, inherited stderr. On Linux, `pre_exec` sets
  `prctl(PR_SET_PDEATHSIG, SIGTERM)` (`libc`, `cfg(target_os="linux")`).
  The max frame size is 4 MiB; an oversize or unparsable frame kills the
  bridge, and it is respawned on the next call with a stderr log line.
  `tracing` writes to stderr only.
- **Startup:** the bridge is spawned on the MCP `initialized` notification,
  so the actor is known. The `init` frame carries the actor and the reply is
  `describe`. `list_tools` before the bridge is ready awaits it, with a 20 s
  timeout → error.

**Alternatives:** spawning the bridge per call (loses the session-scoped
streak and pays startup each time, rejected). Using stderr for frames
(collides with logging, rejected).

## R7 — Interpreter and repo discovery

**Decision:** the binary takes `--repo <path>` (required; the env fallback
`SDLC_REPO_ROOT`). It spawns `<repo>/.venv/bin/python -m sdlc.operator.bridge`
(`Scripts\python.exe` on Windows) with `cwd=<repo>`, so `.env`
(`load_dotenv()` in the bridge, as `cli.py:469` does) and the relative
runs/board paths resolve exactly as they do for the CLI. Overrides:
`SDLC_MCP_PYTHON`, and `--bridge-cmd <argv…>` (used by tests to run a
fake-deps bridge, so production code never imports a module named by an env
var). **Alternatives:** `uv run` (adds about 0.3 s and requires `uv` on the
MCP client's PATH, rejected as the default; still possible via
`--bridge-cmd`).

## R8 — Actor identity (FR-007; skeptic L4)

**Decision:** `normalise(name)`: lowercase; every run of characters outside
`[a-z0-9]` becomes `-`; strip leading and trailing `-`; truncate to 40.
The result is `mcp:<that>`, or `mcp:local` if it is empty. `SDLC_MCP_ACTOR`
must match `^mcp:[a-z0-9-]{1,40}$`, or the binary exits at startup with a
message on stderr. The bridge re-validates the regex in `init`.
- **Gap found and accepted:** `ActorChannel.translate`
  (`channels/contract.py:182-186`) stamps `reviewer` only on gate decisions.
  `answer_question`'s FR-302 signal has no identity field, for chat as for
  MCP. Adding one is a workflow signal change (replay-sensitive), outside
  E-11.
- Instead, the bridge logs `actor`, run id and key for every write to stderr
  and the operator log. SC-005/FR-007 are scoped accordingly.

**Alternatives:** extending the clarify signal (out of scope, replay risk).

## R9 — Tests and gates (skeptic S8, S9, S10)

**Decision:**
- **Python, fast tier** (`tests/test_operator_bridge.py`): the frame
  protocol, `describe` output, preview/digest, the TOCTOU refusal, stdout
  hygiene, the `runtime` import probe (no fastapi/starlette/pydantic_ai/
  worker loaded), and membership plus the negative schema assertions
  (`deps`, `thaw_tests`, `budget_usd` absent).
- **Rust** (`cargo test`): an in-process rmcp client (feature `client`)
  against the server with a scripted fake bridge. It covers the E1/E2
  accept/decline/cancel/unsupported cases, `requestState` tamper, replay,
  expiry and args-swap, actor normalisation, and progress/cancel forwarding.
- **Real-binary parity** (`tests/test_operator_mcp_parity.py`, new marker
  `mcp`, excluded from the default `addopts`): spawns the release binary with
  `--bridge-cmd python tests/mcp_fake_bridge.py`. The scripted client is a
  small raw JSON-RPC client in `tests/mcp_stdio_client.py`, with no new
  Python dep. It asserts byte-identical text for the text verbs vs direct
  `tools.<verb>(deps, …)` on the same fakes, structured parity for the typed
  verbs, `isError` mapping, and the write paths. It is not tautological: it
  crosses the real Rust wire.
- **One gate**: `scripts/check_mcp.py` runs
  `cargo fmt --check` → `clippy -D warnings` → `cargo test` →
  `cargo build --release` → `pytest -m mcp`.
  - With no `cargo` it skips loudly and exits 0, unless `CI=true` (then it
    exits 1). That is the `check_ui.py` precedent.
  - It is wired as one `run:` line in a new `mcp` CI job (with
    `Swatinem/rust-cache`) and as `("mcp", [python, "scripts/check_mcp.py"])`
    in `scripts/verify.py`, which keeps `tests/test_verify.py` green.
- `"Cargo.lock"` is added to `EXEMPT_PATTERNS`.
- `interfaces/mcp/target/` goes in `.gitignore`.

**Alternatives:** pytest building cargo (breaks hosts without cargo,
rejected). Mocked-bridge-only parity (tautological, rejected).

## R10 — Dependency pins (FR-016)

**Decision:**
- Rust: `rmcp = { version = "~3.10", default-features = false, features = ["server", "transport-io", "elicitation", "schemars", "request-state"] }`
  (plus `client` under `[dev-dependencies]`), and `tokio` (`process`,
  `io-util`, `macros`, `rt-multi-thread`), `serde`, `serde_json`, `schemars`
  (rmcp's major), `sha2`, `getrandom`, `uuid`, `libc` (linux only),
  `tracing` and `tracing-subscriber`.
- **Every** crate, direct and dev, is written as a bounded minor
  `"~MAJOR.MINOR"` of the version cargo resolves at T030 (e.g.
  `tokio = "~1.N"`). No bare major (`"1"`, `"~1"`) and no `*`, which mirrors
  the `pyproject.toml` bounded-pin policy. `Cargo.lock` is committed and
  pins exact versions. An upgrade moves the bound, the lock and any
  adapted code in one PR.
- `rust-toolchain.toml` pins a specific stable, at or above rmcp's workspace
  `rust-version`; it is read from the workspace manifest at T-impl time
  (the crate manifest inherits it).
- Python: **no new dependency**. The bridge uses only stdlib and
  pydantic.
