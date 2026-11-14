# Implementation Plan: MCP server as a channel adapter (E-11)

**Branch**: none (shared tree; spec dir `022-mcp-channel-adapter`) | **Date**: 2026-11-14 | **Spec**: [spec.md](spec.md)

**Input**: `.specify/specs/022-mcp-channel-adapter/spec.md` (GATE 1 ruled 2026-11-14)

`S/` = `src/sdlc/`. `M/` = `interfaces/mcp/`.

## Summary

The MCP server is a Rust stdio server on `rmcp ~3.10`, per the owner's
GATE 1 ruling. **Locked seam: (b).** The server spawns one persistent Python
**verb bridge** (`python -m sdlc.operator.bridge`) per MCP session and talks
to it over JSON-lines on the child's stdin/stdout (contracts/bridge-protocol.md).
- **Tools:** the bridge's `describe` publishes all twelve verbs
  (names, docstrings, pydantic schemas, flags). Rust serves them through one
  generic, metadata-driven `ServerHandler`, so it holds zero per-verb logic
  (research R2, R3).
- **Writes:** confirmed by MCP elicitation, fail-closed, on both protocol
  paths. E1 is server-to-client `elicit` (< 2026-07-28); E2 is MRTR
  `InputRequiredResult` with an HMAC-sealed, single-use `requestState`
  (≥ 2026-07-28).
- **Stale-confirmation guard:** a preview digest is re-checked by the bridge
  just before the verb runs (research R4).
- **Composition:** it moves out of `interfaces/dashboard/api/main.py` into a
  framework-free `S/operator/runtime.py`. That module starts
  `"GraphWorkflow"` by name so it never imports the worker or the registry
  (research R5).
- **Parity:** proven by spawning the real binary against a fake-deps bridge
  (research R9).

Advisor ranked (b) > (a′) > (c). Skeptic's 4 BLOCKERs and 10 MUST-FIX items
are each dispositioned in §Skeptic disposition.

## Technical Context

**Language/Version**: Rust (stable, pinned in `M/rust-toolchain.toml` at ≥ rmcp's workspace `rust-version`; edition 2024) + Python 3.13 (existing)

**Primary Dependencies**:
- `rmcp ~3.10` with features `server`, `transport-io`, `elicitation`,
  `schemars` and `request-state` (dev: `client`).
- `tokio ~1`, `serde`/`serde_json ~1`, `schemars` (rmcp's major), `sha2`,
  `getrandom`, `uuid`, `tracing`/`tracing-subscriber`, `libc` (linux).
- Python: none new (stdlib + pydantic).

**Storage**: none. Board sqlite and artifact blobs are read through the existing verbs.

**Testing**:
- `cargo test`: in-process rmcp client + scripted fake bridge.
- pytest fast tier: `tests/test_operator_bridge.py`, `tests/test_task_queue.py`.
- pytest marker `mcp`: real-binary parity, `tests/test_operator_mcp_parity.py`.
- All of it runs through `scripts/check_mcp.py`.

**Target Platform**: operator workstation; Linux and macOS first-class. Windows supported for the bridge path (`Scripts\python.exe`); PDEATHSIG is Linux-only, and elsewhere `kill_on_drop` plus stdin-EOF is the guarantee.

**Project Type**: CLI-spawned stdio server (Rust binary) + Python subprocess adapter.

**Performance Goals**:
- `tools/list` < 3 s after spawn (bridge import ≈ 0.3–0.8 s measured).
- Read tools add < 50 ms over the verb itself.
- `follow` emits progress every ≤ 15 s.

**Constraints**:
- 1000-line file ceiling.
- `tools.py` stays a framework leaf (layering test unchanged).
- No dashboard or worker boot import.
- Fail-closed writes.
- No paid model runs.
- Shared working tree: never `git add -A`.

**Scale/Scope**: one operator, a handful of concurrent client sessions, twelve tools.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template. The binding rules are root `AGENTS.md`, `interfaces/AGENTS.md` and the brief's repo constraints.

| Rule (source) | How the plan complies | Status |
|---|---|---|
| 1000 physical lines per file (`scripts/check_file_size.py`) | Rust split into `main.rs`, `server.rs`, `bridge.rs`, `confirm.rs`, `actor.rs`, each < 400 lines; `bridge.py` < 400, `runtime.py` < 120; `M/` is under the `interfaces/` scope prefix; `Cargo.lock` exempted like `uv.lock` (T012) | PASS |
| Cross-stage call ban (root `AGENTS.md`) | No stage touched; `runtime.py` composes client-side start only | PASS |
| `tools.py` framework-free; layering test is the authority | `tools.py` gains only the two membership tuples (pure references, T013) and the `_check_kind` helper factored out of `_reply` (T022, framework-free); `bridge.py`/`runtime.py` never imported by `tools.py`; existing assertions untouched; a new probe asserts `import sdlc.operator.bridge` loads no fastapi/starlette/pydantic_ai (T024) | PASS |
| Writes approval-gated | Elicitation fail-closed on E1/E2; no unconfirmed path (research R4) | PASS |
| Optional surfaces fail-soft beside the dashboard (`mount_chat` precedent) | The MCP server is a separate client-spawned process; the dashboard's only change is calling `runtime.start_graph` (T011); nothing MCP is imported at dashboard boot | PASS |
| Bounded pins + lock files | `~3.10`-style Rust pins + committed `Cargo.lock`; no new Python dep | PASS |
| CI gate parity (`tests/test_verify.py`) | One `run: python scripts/check_mcp.py` line, mirrored in `scripts/verify.py` (T051) | PASS |
| No paid runs (owner) | No test uses a model; the manual scenario uses a real client but no tokens on the factory side | PASS |

**Post-design re-check**: PASS. One justified complexity item is in Complexity Tracking.

## Phases

### Phase A — Python seams (no Rust yet; each step lands green on the fast tier)

- **T010** `S/task_queue.py` (new, about 5 lines): `TASK_QUEUE = "ai-sdlc"`. In `S/worker.py:128`, replace the literal with `from .task_queue import TASK_QUEUE` (the re-export keeps `cli.py:481`, `benchmarks/cli.py:333` and `schedules/apply.py:42` working unchanged). Add `tests/test_task_queue.py`, which asserts identity with `worker.TASK_QUEUE` and that importing `sdlc.task_queue` loads neither `temporalio` nor `sdlc.agents`.
- **T011** `S/operator/runtime.py` (new). It holds:
  - `connect()`: `Client.connect(TEMPORAL_HOST, data_converter=pydantic_data_converter)`.
  - `build_poller() -> FleetPoller`.
  - `async start_graph(poller, idea, cfg, wf_id) -> str`: calls `build_run_input` (lazy), then `start_graph_run(client, "GraphWorkflow", run_input, id=wf_id, task_queue=TASK_QUEUE)`, returning `handle.id`.
  - `operator_deps(poller, actor) -> OperatorDeps`: with `board=BoardStore` (the class) and `starter=functools.partial(start_graph, poller)`.

  `interfaces/dashboard/api/main.py` then replaces `_connect`/`_start` with `runtime.connect`/`runtime.start_graph`, and `mount_chat` builds its deps via `runtime.operator_deps(poller, "chat:local")`. Behaviour is unchanged: the existing dashboard and chat tests pass as they are. A test pins `GraphWorkflow`'s `workflow.defn` name to `"GraphWorkflow"` (via temporalio's workflow-definition introspection). That test runs under the dummy keys `tests/conftest.py` sets.
- **T012** `scripts/check_file_size.py`: add `"Cargo.lock"` and `"*/Cargo.lock"` to `EXEMPT_PATTERNS`. `.gitignore`: add `interfaces/mcp/target/`.
- **T013** `S/operator/tools.py`: append `READ_TOOLS` and `WRITE_TOOLS`, moved verbatim from `agent.py:85-96`. `agent.py` then imports them from `tools`. The layering test still passes, since these are pure references.

### Phase B — the verb bridge (`S/operator/bridge.py`, Python owns the contract)

- **T020** Framing and lifecycle: `BRIDGE_PROTOCOL = 1`.
  - **fd hygiene first:** `isolate_stdout() -> BinaryIO` does `_proto = os.fdopen(os.dup(1), "wb", buffering=0)`; then `os.dup2(2, 1)`; then `sys.stdout = sys.stderr`, and returns `_proto`. `main()` calls it before importing `tools`/`runtime`, so `python -m sdlc.operator.bridge` is safe. The `serve()` entry is importable by tests and accepts injected deps.
  - Reads stdin via `asyncio` `connect_read_pipe`; caps lines at 4 MiB.
  - Runs one task per request, with a write lock.
  - On EOF: cancel tasks, `await deps.poller.aclose()` (if it has one), exit 0.
  - `load_dotenv()` before building the runtime.
- **T021** `describe`: builds a `ToolDescriptor` per `READ_TOOLS + WRITE_TOOLS` member.
  - `input_schema` comes from `pydantic.create_model` over the signature params minus `deps`. Annotations are resolved with `typing.get_type_hints(fn)`; `tools.py` uses `from __future__ import annotations`.
  - `output_schema` comes from the return annotation if it is a `BaseModel`.
  - `CONFIRM = {"start_run": "start", "answer_question": "pending", "decide_gate": "pending"}`; `PROGRESS = {"follow"}`.
  - `init` validates the actor regex and builds deps via `runtime.operator_deps`.
- **T022** `preview`:
  - **`pending`:** `handle` → `resolve_key` → check `reply_kind` against the tool. A mismatch raises the same `ToolError` sentence `_reply` uses; to keep that wording single-sourced, factor a `_check_kind(pending, want)` helper out of `tools._reply` (`tools.py`) and have `_reply` call it. Then `default_render` → message + digest.
  - **`start`:** builds the message from the args and `fleet_pending_cap()` / `snapshot`. It must not call `note_other_tool`.
  - Errors are `translate`d.
- **T023** `call`: validates the args with the descriptor's model. For confirm tools it requires `expect_digest`, recomputes the preview digest and returns `changed` on a mismatch; then it awaits the verb. It serialises `str` → `value: str`, and a `BaseModel` → `model_dump(mode="json")`. It logs every write with the actor. For `PROGRESS` tools it runs the verb as a task and emits `progress` frames every 15 s until the task is done. `cancel` cancels the task.
- **T024** `tests/test_operator_bridge.py` (fast tier, fakes from the existing `tests/test_operator_*` helpers). It drives `serve()` over in-memory pipes and covers:
  - the `init`/`describe` shape;
  - membership == `READ_TOOLS + WRITE_TOOLS`;
  - absence of `deps`, `thaw_tests` and `budget_usd` from the schemas;
  - every write having a non-`none` confirm;
  - byte-identical text vs direct verb calls for all text verbs;
  - the `ToolError` passthrough;
  - preview not resetting the follow streak (ten follows, a preview, then the eleventh follow is still refused);
  - the digest mismatch → `changed` with zero signals sent;
  - a missing `expect_digest` → refused;
  - progress frames during a fake 31 s follow (with an injected clock);
  - cancel → `cancelled` and the poller subscription released;
  - a stray `print()` inside a verb never reaching the frame stream (a subprocess run of `tests/mcp_fake_bridge.py`, which calls the same `bridge.isolate_stdout()` that `main()` calls, with a fake verb that prints);
  - the import probe: `import sdlc.operator.bridge` loads none of `fastapi`, `starlette`, `pydantic_ai`.

### Phase C — the Rust server (`M/`)

- **T030** `M/Cargo.toml`: package `kroker-mcp`, bin `kroker-mcp`, with the pins from research R10. Also add `M/rust-toolchain.toml`, a `Cargo.lock` (committed) and `M/.cargo` (none).
- **T031** `M/src/main.rs`:
  - Parses args (`--repo`, `--bridge-cmd …`), with env fallbacks `SDLC_REPO_ROOT`, `SDLC_MCP_PYTHON`, `SDLC_MCP_ACTOR`.
  - Validates `SDLC_MCP_ACTOR` and exits 2 on an invalid value.
  - Sends tracing to stderr only.
  - Runs `Server::new(..).serve(stdio()).await?.waiting()`.
- **T032** `M/src/actor.rs`: `normalise(&str) -> String` per research R8, plus unit tests (collisions, `../../admin`, control chars, 500 chars, empty → `mcp:local`).
- **T033** `M/src/bridge.rs`: the child supervisor and the protocol client.
  - Spawns with `kill_on_drop(true)` and, on Linux, `pre_exec` PDEATHSIG; piped stdin/stdout, inherited stderr.
  - Uses a reader task and a pending map `id → oneshot`, with progress senders.
  - Sends `init` and awaits `describe` with a 20 s timeout.
  - On child death it fails the in-flight calls and lazily respawns.
  - It contains no verb names; a grep test in `cargo test` asserts that none of the twelve names appears in `M/src/`.
- **T034** `M/src/server.rs`: a manual `ServerHandler`.
  - `initialize` override: records the negotiated `protocol_version` and the client elicitation capability, then calls `negotiate_initialize`.
  - `on_initialized`: computes the actor from `peer_info()` and spawns the bridge.
  - `list_tools`: maps descriptors to `Tool` with annotations and `output_schema`.
  - `call_tool`: if `confirm == none`, it calls the bridge directly; otherwise it goes to `confirm.rs`.
  - It maps results per contracts/mcp-tools.md.
  - `on_cancelled` forwards `cancel`.
  - Progress frames go to `notify_progress` when `ctx.meta["progressToken"]` is set.
- **T035** `M/src/confirm.rs`:
  - The `Confirm { confirm: bool }` form (`JsonSchema`, `elicit_safe!`).
  - **E1:** `elicit_with_timeout` (300 s).
  - **E2:** `InputRequired` with `RequestStateCodec`, keyed by a 32-byte `getrandom` key made at startup. It seals `SealedState`, opens it on retry, and checks tool, args hash, expiry and the `consumed_jti` map (bounded to 1024 entries, fail-closed when full of live entries).
  - **None:** the fail-closed sentence.
  - All refusal sentences come verbatim from contracts/mcp-tools.md.
- **T036** `cargo test` (`M/tests/server.rs`): an in-process rmcp client against the server, with `--bridge-cmd` pointing at a scripted fake bridge (a tiny Rust test binary or a Python script under `M/tests/fixtures/`). It covers:
  - `tools/list` from `describe`;
  - text and structured mapping;
  - `isError` mapping;
  - E1 accept, decline, cancel and timeout;
  - E1 with no capability (fail-closed);
  - E2 accept, tampered state, replayed `jti`, args swap and expiry;
  - progress forwarding;
  - cancel forwarding;
  - child death → error, then respawn;
  - and runs `cargo clippy -D warnings`.

### Phase D — real-binary parity and gates

- **T040** `tests/mcp_stdio_client.py`: a minimal raw JSON-RPC 2.0 stdio client, test-only, with no new dependency. It covers `initialize` (with a selectable `protocolVersion` and capabilities), `tools/list`, `tools/call`, answering `elicitation/create` per the script, and E2 retry with `inputResponses`. Alongside it, `tests/mcp_fake_bridge.py` calls `bridge.serve()` with the fake poller/board/starter/handle from the operator test helpers.
- **T041** `tests/test_operator_mcp_parity.py` (marker `mcp`; skips unless `SDLC_MCP_BIN` points at a built binary): spawns `SDLC_MCP_BIN --repo . --bridge-cmd python tests/mcp_fake_bridge.py`. It asserts:
  - the twelve tool names == `tools.READ_TOOLS + WRITE_TOOLS`;
  - for every text verb, the MCP text is byte-identical to `await tools.<verb>(fake_deps, …)` on an identical fake fleet;
  - typed verbs' `structuredContent` == `model_dump(mode="json")`, with an `outputSchema` present;
  - the `ToolError` wording is verbatim;
  - `decide_gate` E1 accept → exactly one gate signal with `reviewer == "mcp:parity-client"`;
  - decline → zero signals;
  - no elicitation capability → fail-closed sentence, zero signals;
  - E2 accept → one signal, and a replay of the same `requestState` → refused, still one signal;
  - `confirmed=false` → `isError` false;
  - the absence of `thaw_tests`/`budget_usd` from the published schemas.
- **T042** `pyproject.toml`: add the marker `"mcp: spawns the built kroker-mcp binary (scripts/check_mcp.py builds it)"` and append `and not mcp` to `addopts`.
- **T050** `scripts/check_mcp.py`, modelled on `check_ui.py`.
  - It locates `cargo` via `shutil.which`. If cargo is absent: when `CI` is unset it prints `mcp gate: SKIPPED (cargo not found)` and exits 0; otherwise it exits 1.
  - It runs `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test` and `cargo build --release` (all with `--manifest-path interfaces/mcp/Cargo.toml`), then `python -m pytest -m mcp tests/test_operator_mcp_parity.py -q` with `SDLC_MCP_BIN` set.
  - It prints `mcp gate: ok`.
- **T051** `.github/workflows/ci.yml`: a new job `mcp`. Steps: checkout, setup-python 3.13, `uv sync --frozen --extra dev` (the setup line is exempt from parity), `Swatinem/rust-cache` with `workspaces: interfaces/mcp`, then one `run: python scripts/check_mcp.py`. `scripts/verify.py` `GATES` gets `("mcp", [sys.executable, "scripts/check_mcp.py"])` after `ui`. `tests/test_verify.py` stays green.

### Phase E — docs and bookkeeping

- **T060** `M/README.md`: build, the client config for Claude Code and goose, the env vars, and the elicitation requirement with its trust boundary (clients or hooks that auto-accept bypass the human gate by client policy; auto-decline means nothing happens). Add `M/client-config.example.json`. Add `M/AGENTS.md` (local rules: no verb names in Rust, the bridge contract is owned by Python, stdout is MCP-only, the gate command). Add an `interfaces/AGENTS.md` router line for `mcp/`.
- **T061** Update the `S/operator/agent.py` docstring (MCP is a Rust server over `bridge.py`, not `mcp.py`) and the `S/operator/tools.py` docstring (consumers: `agent.py` and `bridge.py`).
- **T062** `ROADMAP.md`:
  - The FR-602 line (`:345`) becomes [x] with a pointer to this spec.
  - The E-11 line is amended: "Rust `rmcp` server over a Python verb bridge that re-exports `tools.py`."
  - The US-7 line closes the MCP half.
  - The Last-verified cell is updated, with the full entry prepended to `docs/roadmap/last-verified-log.md` per root `AGENTS.md`.

  `ARCHITECTURE.md:886` gets the "no `interfaces/mcp/`" note fixed. `docs/roadmap/filesystem-first.md` gets the E-11 line.
- **T070** Full battery: `ruff check .`, `ruff format --check .`, `mypy`, `scripts/check_file_size.py --full`, `pytest -q` (diff the FAILED ids against `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`), `python scripts/check_mcp.py`.

## Skeptic disposition (skeptic-answer-1.md)

| ID | Severity | Disposition |
|---|---|---|
| L1 toolchain/drift/E2 | MUST-FIX | T030 pins + toolchain; E2 in T035 |
| L2 client elicitation reality / auto-accept | BLOCKER | Researched (R1): Claude Code CLI advertises form elicitation, so writes are not bricked there. Auto-decline bugs fail safe. The required no-default `confirm` field (T035) defeats `{}` auto-fill. The auto-accept trust boundary is documented (T060) and cannot be fixed server-side. Claude Desktop/web: writes refused by design (GATE 1) |
| L3 follow timeout/cancel/streak | MUST-FIX | T023 progress + cancel; a cancelled follow still counts toward the streak (it was a wait), documented in T060 |
| L4 actor normalisation, answer gap | MUST-FIX | T032 regex; answer gap scoped in spec FR-007/SC-005, with a stderr write log (T023) |
| L4b thaw_tests/budget_usd | MUST-FIX | negative assertions T024, T041 |
| S1 TOCTOU, preview streak reset | BLOCKER | digest re-check (T023), preview does not touch the streak (T022, T024) |
| S2 MRTR replay/forgery | BLOCKER | sealed `{jti, tool, args_sha256, digest, exp}`, per-process CSPRNG key, single-use jti (T035, T036, T041) |
| S3 "zero per-verb Rust" honesty | MUST-FIX | metadata flags (R3), the grep test in T033, the claim worded as "zero per-verb logic" |
| S4 importing main.py | BLOCKER | `runtime.py` (T011), workflow started by name, `task_queue.py` (T010) |
| S5 temporalio vs layering | ACCEPTABLE | the bridge is a leaf, plus the new import probe (T024) |
| S6 stdout framing | BLOCKER | fd dup/redirect before imports (T020), and a test with a stray `print` (T024) |
| S7 orphans | MUST-FIX | `kill_on_drop`, PDEATHSIG, EOF cleanup (T020, T033), the quickstart kill -9 check |
| S8 parity honesty | MUST-FIX | the real binary over stdio (T041) |
| S9 Cargo.lock | BLOCKER | T012 |
| S10 CI/verify parity | BLOCKER | the single gate script (T050, T051) |

## Project Structure

### Documentation (this feature)

```text
.specify/specs/022-mcp-channel-adapter/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/{bridge-protocol.md, mcp-tools.md}
├── advisor-{brief,answer}-1.md, skeptic-{brief,answer}-1.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source code touched

```text
src/sdlc/task_queue.py                 new
src/sdlc/worker.py                     TASK_QUEUE re-export
src/sdlc/operator/runtime.py           new — framework-free composition
src/sdlc/operator/bridge.py            new — verb bridge (owns the contract)
src/sdlc/operator/tools.py             + READ_TOOLS/WRITE_TOOLS, _check_kind helper, docstring
src/sdlc/operator/agent.py             import tuples from tools; docstring
interfaces/dashboard/api/main.py       use runtime.connect/start_graph/operator_deps
interfaces/mcp/{Cargo.toml,Cargo.lock,rust-toolchain.toml,README.md,AGENTS.md,client-config.example.json}
interfaces/mcp/src/{main,server,bridge,confirm,actor}.rs
interfaces/mcp/tests/server.rs (+ fixtures/)
interfaces/AGENTS.md                   router line
scripts/check_mcp.py                   new gate
scripts/check_file_size.py             Cargo.lock exemption
scripts/verify.py                      mcp gate
.github/workflows/ci.yml               mcp job
.gitignore                             interfaces/mcp/target/
pyproject.toml                         mcp marker + addopts
tests/test_task_queue.py, tests/test_operator_bridge.py, tests/test_operator_mcp_parity.py,
tests/mcp_stdio_client.py, tests/mcp_fake_bridge.py   new
ROADMAP.md, ARCHITECTURE.md, docs/roadmap/filesystem-first.md, docs/roadmap/last-verified-log.md
```

**Structure Decision**: the Rust crate lives at `interfaces/mcp/`. It is a thin launcher surface per the E-6 ruling, already inside the file-size scope, and next to `interfaces/chat/`. All verb-facing Python stays under `src/sdlc/operator/`, so it is importable by tests (`packages.find` is rooted at `src`).

## Traceability

| Spec item | Tasks |
|---|---|
| FR-001 Rust + parity | T030–T036, T041 |
| FR-002 twelve verbs, membership | T013, T021, T024, T041 |
| FR-003 result shapes | T023, T034, T041 |
| FR-004 errors | T023, T034, T024, T041 |
| FR-005 elicitation fail-closed | T022, T023, T035, T036, T041 |
| FR-006 confirmed=false | T034, T041 |
| FR-007 actor | T021, T032, T034, T041 |
| FR-008 no thaw_tests/budget_usd | T024, T041 |
| FR-009 per-session streak | T020 (one child per session), T024 |
| FR-010 progress/cancel | T023, T034, T036 |
| FR-011 paging | unchanged verb; T041 structured parity |
| FR-012 stdio | T031 |
| FR-013 HTTP later | not built |
| FR-014 auth posture | no listener; T060 README |
| FR-015 layering | T013, T024 probe, existing test |
| FR-016 pins | T030 |
| FR-017 file size | T012, T070 |
| FR-018 docs | T060–T062 |
| SC-001 three-call path (inbox → decide_gate → confirm) | T041 (decide_gate E1 accept), quickstart manual steps 3–4 |
| SC-002 byte-identical | T024, T041 |
| SC-003 error wording verbatim, no raw exceptions | T024 (`ToolError` passthrough), T041 (verbatim wording), contracts/bridge-protocol.md `internal` sentence |
| SC-004 drift caught before merge | T041 (all twelve verbs over the real binary, in the CI `mcp` job via T050/T051); research R2 per-verb-change cost row (0 Rust, 1 Python) |
| SC-005 confirmation + actor | T035, T041 |
| SC-006 dashboard unaffected | T011 (behaviour-preserving), T070 |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| A second language toolchain (Rust/cargo) plus a cross-process bridge | Owner ruling at GATE 1 (Q1): the server is Rust on rmcp | (d), the in-process Python MCP adapter, was overruled. Among Rust seams, (b) is the only one that keeps verb changes single-sourced (research R2) |
