# Tasks: MCP server as a channel adapter (E-11, round 022, FR-602 / US-7)

**Status**: Reviewer-approved (tasks checklist, pass 3, 2026-11-14). Record: [checklists/tasks.md](checklists/tasks.md). Pass 1 had 3 gaps (Rust test-first ordering, a same-file parallel claim, a stale id); pass 2 had 2 stale ids. Do not implement before the next owner gate.

**Input**: `.specify/specs/022-mcp-channel-adapter/`:
- spec.md (GATE 1: Q1 Rust held, Q2 elicitation fail-closed, Q3 twelve verbs);
- plan.md (plan ids T010–T070, reviewer-approved pass 2);
- research.md (R1–R10);
- data-model.md;
- contracts/bridge-protocol.md and contracts/mcp-tools.md;
- quickstart.md.

The ids below are sequential (T001 and up). Each task names the plan id it implements as `(plan Txxx)`. Paths are repo-relative. `S/` = `src/sdlc/`, `T/` = `tests/`, `M/` = `interfaces/mcp/`.

**Tests**: required. The spec mandates parity and membership tests (FR-001, FR-002) and fail-closed writes (FR-005). Each new behaviour gets its test written first, and the test is seen failing for the expected reason before the implementation. On the Rust side the failing run is against compiling `todo!()`/stub bodies, never a compile error (T017 → T018/T019, T028 → T029). T015 and T036 write their tests first within the same task and run them red before the code. No existing test file is edited, except where a task says so.

**Rules for the implementer**:
- **Shared working tree:**
  - never `git add -A` or `git add .`; stage named paths only;
  - never revert or edit files outside this task list;
  - `.specify/feature.json` and `CLAUDE.md` carry other agents' edits.
- **Layering:**
  - `S/operator/tools.py` must never import `bridge`, `runtime`, `pydantic_ai`, `fastapi` or `starlette`;
  - `T/test_operator_layering.py` is never edited.
- **The bridge and the Rust side:**
  - `S/operator/bridge.py` must never import `interfaces.dashboard.api.main`, `sdlc.worker` or `sdlc.workflows.graph`;
  - Rust sources under `M/src/` never name any of the twelve verbs (T017 enforces this).
- **Hygiene:**
  - stdout is protocol-only on both sides; Rust `tracing` and Python logging go to stderr;
  - every file stays ≤ 1000 physical lines (`scripts/check_file_size.py`).
- **Cost:** no paid model runs anywhere; no task runs a `temporal` CLI command or `pytest -m temporal`.
- **If a step seems to need any of these, STOP and report:**
  - a new Python dependency;
  - a workflow signal change (e.g. an actor field on `answer_question`);
  - an edit to `T/test_operator_layering.py`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1–US4 from spec.md (US1 reads P1, US2 answer/decide P1, US3 start P2, US4 follow/artifacts P3)

---

## Phase 1: Setup

- [x] T001 Record the baseline. Run `uv run pytest -q` from the repo root and save the sorted failing test ids to `.specify/specs/022-mcp-channel-adapter/baseline-failures.txt`, with a header naming the HEAD commit. Then diff the list against `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`. Any id outside that file is a STOP: report it, and do not proceed. (plan T070 baseline)
- [x] T002 [P] Toolchain check. Run `rustup --version` and `cargo --version`. If they are missing, install rustup (user-local, `~/.cargo`) and record the stable version installed in the T001 baseline file header. Read the `rust-version` from the rmcp 3.10 workspace manifest (`https://raw.githubusercontent.com/modelcontextprotocol/rust-sdk/main/Cargo.toml`) and note it. No repo file changes. (plan T030 prerequisite)

---

## Phase 2: Foundational (blocks every story)

**Purpose**:
- framework-free composition;
- the membership tuples;
- the file-size exemption;
- shared fakes;
- the bridge skeleton (`init`/`describe`, framing, hygiene);
- the Rust skeleton that serves `tools/list` from `describe`.

No user-visible tool works yet.

### Python seams

- [x] T003 [P] Write a failing test in new `T/test_task_queue.py`:
  - `from sdlc.task_queue import TASK_QUEUE` equals `"ai-sdlc"` and `is` `sdlc.worker.TASK_QUEUE`;
  - a subprocess probe (`sys.executable -c "import sys, sdlc.task_queue; print(...)"`, `cwd` = repo root) shows that neither `temporalio` nor `sdlc.agents` is in `sys.modules`.

  Then create `S/task_queue.py` (`TASK_QUEUE = "ai-sdlc"` plus a docstring). In `S/worker.py:128`, replace the literal with `from .task_queue import TASK_QUEUE  # noqa: F401 -- re-export`, keeping the name importable from `sdlc.worker` for `S/cli.py:481`, `S/benchmarks/cli.py:333` and `S/schedules/apply.py:42`. Verify with `uv run pytest T/test_task_queue.py -q`. (plan T010)
- [x] T004 Write failing tests in new `T/test_operator_runtime.py`:
  - a subprocess probe showing that `import sdlc.operator.runtime` loads none of `fastapi`, `starlette`, `pydantic_ai`, `sdlc.worker`, `sdlc.workflows.graph`;
  - `runtime.operator_deps(poller, "chat:local")` returns `OperatorDeps` with `board is BoardStore` (the class), `actor == "chat:local"` and a callable `starter`;
  - `start_graph` calls `start_graph_run` with `run == "GraphWorkflow"` and `task_queue == TASK_QUEUE` (monkeypatch `runtime.start_graph_run` and `runtime.build_run_input`; fake poller `_client_or_connect`);
  - `GraphWorkflow`'s registered workflow name is `"GraphWorkflow"`. Read it through temporalio's definition introspection inside the test only; importing `sdlc.workflows.graph` there is fine because `T/conftest.py` sets the dummy keys.

  Then create `S/operator/runtime.py`:
  - `connect()`: `Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"), data_converter=pydantic_data_converter)`;
  - `build_poller()`: `FleetPoller(connect)`;
  - `async start_graph(poller, idea, cfg, wf_id) -> str`: import `build_run_input` lazily, then `start_graph_run(client, "GraphWorkflow", run_input, id=wf_id, task_queue=TASK_QUEUE)`, returning `handle.id`;
  - `operator_deps(poller, actor) -> OperatorDeps`: with `starter=functools.partial(start_graph, poller)`.

  Imports allowed: `temporalio.client`, `temporalio.contrib.pydantic`, `sdlc.dashboard.fleet`, `sdlc.board.store`, `sdlc.graph.start`, `sdlc.task_queue`, `sdlc.operator.deps`. Verify with `uv run pytest T/test_operator_runtime.py -q`. (plan T011)
- [x] T005 Switch `interfaces/dashboard/api/main.py` to the runtime:
  - delete `_connect` and `_start`;
  - `poller = runtime.build_poller()`;
  - `create_router(poller, starter=functools.partial(runtime.start_graph, poller))`;
  - in `mount_chat`, `deps = runtime.operator_deps(fleet_poller, "chat:local")`;
  - drop the now-unused imports of `Client`, `pydantic_data_converter`, `start_graph_run`, `GraphWorkflow`, `build_run_input` and `TASK_QUEUE`.

  Behaviour must be unchanged. Verify with `uv run pytest T/test_chat_mount.py T/test_operator_e2e.py -q` and `uv run pytest -q -k "dashboard"`: no new FAILED id vs T001. (plan T011)
- [x] T006 [P] `scripts/check_file_size.py`: add `"Cargo.lock"` and `"*/Cargo.lock"` to `EXEMPT_PATTERNS`, next to `"uv.lock"`, with the comment `# generated lock files`. `.gitignore`: add `interfaces/mcp/target/`. Verify with `uv run python scripts/check_file_size.py --full` → exit 0. (plan T012)
- [x] T007 Move the membership tuples. Cut `READ_TOOLS` and `WRITE_TOOLS` from `S/operator/agent.py:85-96` and paste them verbatim at the end of `S/operator/tools.py`, below `start_run`. `agent.py` then does `from .tools import READ_TOOLS, WRITE_TOOLS` (the name `agent.READ_TOOLS` keeps working). Verify with `uv run pytest T/test_operator_layering.py T/test_operator_agent.py -q`. (plan T013)
- [x] T008 Factor out `_check_kind`. Factor the reply-kind check from `tools._reply` (`S/operator/tools.py`, the `kind != want` block) into `def _check_kind(pending, want: str) -> None` with the identical `ToolError` sentence, and have `_reply` call it. Verify with `uv run pytest T/test_operator_writes.py -q` (unchanged tests stay green). (plan T022 prerequisite)
- [x] T009 [P] Create the shared fake module `T/operator_fakes.py`. It is a helper, not a test module; there is no `test_` prefix. It holds:
  - `FakeHandle(run_id, pending)`, implementing the real transport protocol:
    - `async query(name)` returns `[d.model_dump(mode="json") for d in pending]` for `PENDING_QUERY`;
    - `async signal(name, *args, **kw)` appends `(name, args)` to `self.signals` and removes the addressed item;
  - `FakeClient`;
  - `FakePoller(snapshot, handles)` with `snapshot()`, `_client_or_connect()`, an `async subscribe()` context manager yielding an `asyncio.Queue` the test can `put` snapshots into, and `aclose()`;
  - `seed_board(tmp_path) -> Callable[[], BoardStore]`: one project, one plan artifact, one 100 KB artifact blob, two tasks, three events, built the way `T/test_operator_tools_board.py` and `T/test_operator_read_artifact.py` build theirs;
  - `fleet()`: two open runs, one `StageGatePending`, one `ClarifyPending`, one closed run;
  - `build_fake_deps(tmp_path, actor) -> OperatorDeps` with a recording `starter`;
  - `record_to(path)`, which dumps `signals` + `started` as JSON on demand.

  It must not import pytest at module level, so it is importable from a subprocess. (plan T024/T040 support)

### Bridge skeleton

- [x] T010 Write failing tests in new `T/test_operator_bridge.py`, section "framing". They drive `bridge.serve(deps_factory, reader, writer)` over `asyncio` in-memory streams:
  - `init` with actor `mcp:test` → a `describe` frame with `protocol == 1`;
  - `init` with actor `chat:x` or `mcp:` + 41 chars → a terminal `bad_request` and no deps built;
  - a frame over 4 MiB → `bad_request`;
  - unknown `op` → `bad_request`;
  - EOF → `serve` returns, after awaiting `poller.aclose()`;
  - the subprocess probe `import sdlc.operator.bridge` loads none of `fastapi`, `starlette`, `pydantic_ai`, `sdlc.worker`;
  - a subprocess run of `T/mcp_fake_bridge.py` (T023) whose fake verb `print()`s produces only parseable JSON lines on stdout, with the printed text appearing on stderr.

  The last case is marked `xfail(strict=True)` until T023 lands. (plan T024)
- [x] T011 Create `S/operator/bridge.py`, framing and lifecycle. It holds:
  - `BRIDGE_PROTOCOL = 1`;
  - `isolate_stdout() -> BinaryIO`: `os.fdopen(os.dup(1), "wb", buffering=0)`, then `os.dup2(2, 1)`, then `sys.stdout = sys.stderr`;
  - `async serve(deps_factory, reader, writer)`:
    - newline-delimited JSON, at most 4 MiB a frame;
    - one task per request id;
    - an `asyncio.Lock` around writes;
    - a `cancel` op;
    - on EOF, cancel all tasks and `await deps.poller.aclose()` when present;
  - `main()`: `isolate_stdout()` first, then `load_dotenv()`, then import `runtime`, connect stdin/the proto fd with `connect_read_pipe`/`connect_write_pipe`, then `asyncio.run(serve(lambda actor: runtime.operator_deps(runtime.build_poller(), actor), ...))`;
  - `if __name__ == "__main__": main()`.

  The actor regex is `^mcp:[a-z0-9-]{1,40}$`. Fixed error sentences come verbatim from contracts/bridge-protocol.md. Logging goes to stderr. Keep it under 400 lines. Verify with `uv run pytest T/test_operator_bridge.py -q -k framing`. (plan T020)
- [x] T012 Write failing tests in `T/test_operator_bridge.py`, section "describe":
  - tool names == `[f.__name__ for f in tools.READ_TOOLS + tools.WRITE_TOOLS]` (12, same order);
  - every `description == inspect.getdoc(fn)`;
  - no `input_schema` mentions `deps`;
  - `decide_gate` has no `thaw_tests`; `start_run` has no `budget_usd`;
  - `output_schema` is non-null exactly for `read_artifact`, `follow`, `answer_question`, `decide_gate`;
  - `read_only` is true exactly for `READ_TOOLS`;
  - `confirm` is `start` for `start_run`, `pending` for `answer_question`/`decide_gate`, `none` otherwise; every `WRITE_TOOLS` member is non-`none`;
  - `progress` is true only for `follow`;
  - `GateOutcome`/`ProjectMode` appear as enums in the schemas. (plan T024)
- [x] T013 Implement `describe` in `S/operator/bridge.py`:
  - `pydantic.create_model(f"{name}_args", **{p: (hint, default)})` over `inspect.signature(fn)` params minus `deps`, with `typing.get_type_hints(fn)`;
  - `input_schema = Model.model_json_schema()`;
  - `output_schema` from the return hint when it is a `BaseModel` subclass;
  - `CONFIRM` and `PROGRESS` dicts as in plan T021.

  `init` builds deps via the injected factory and replies `describe`. Verify with `uv run pytest T/test_operator_bridge.py -q -k "framing or describe"`. (plan T021)

### Rust skeleton

- [x] T014 Create the crate `M/`:
  - `M/Cargo.toml`: package `kroker-mcp`, edition 2024, `[[bin]] name = "kroker-mcp"`. Dependencies follow research R10: every crate as `"~MAJOR.MINOR"` of the version cargo resolves today, with `rmcp` at `"~3.10"`, `default-features = false`, and features `server`, `transport-io`, `elicitation`, `schemars`, `request-state`. Dev-dependencies: `rmcp` with `client`, `tokio` with `test-util`.
  - `M/rust-toolchain.toml`: `channel = "<stable from T002>"` (≥ rmcp's `rust-version`), components `rustfmt`, `clippy`.
  - Run `cargo generate-lockfile --manifest-path M/Cargo.toml` and commit the resulting `M/Cargo.lock`.

  Verify with `cargo metadata --manifest-path interfaces/mcp/Cargo.toml --format-version 1 >/dev/null`. (plan T030)
- [x] T015 [P] Write `M/src/actor.rs`: `pub fn normalise(name: &str) -> String` per research R8, and `pub fn validate_override(s: &str) -> Result<String, String>`. Unit tests in the same file:
  - `"Claude Code"` → `mcp:claude-code`;
  - `"Claude Code!!!"` → `mcp:claude-code`;
  - `"../../admin"` → `mcp:admin`;
  - control characters stripped;
  - a 500-char name truncated to 40 after the prefix;
  - `""` and `"!!!"` → `mcp:local`;
  - the override `mcp:ok-1` is accepted; `chat:x` and `mcp:Bad` are rejected.

  Verify with `cargo test --manifest-path interfaces/mcp/Cargo.toml actor`. (plan T032)
- [x] T016 [P] Write `M/tests/fixtures/fake_bridge.py`, a scripted bridge for `cargo test`. It speaks contracts/bridge-protocol.md over stdin/stdout, reads a scenario JSON from argv[1], and returns canned `describe`/`result`/`progress` frames. It records the requests it received to a path in the scenario. It imports only stdlib. (plan T036 support)
- [x] T017 Write the failing Rust integration test `M/tests/server.rs`, sections "list" and "supervisor", **before** T018/T019. Create `M/src/{main,server,bridge}.rs` as compiling stubs whose bodies are `todo!()` (and a `main` that serves no tools), so the tests fail at runtime for the expected reason, not with a compile error. It uses an in-process rmcp client (feature `client`) against the server, built with `--bridge-cmd python3 M/tests/fixtures/fake_bridge.py <scenario>`, and checks:
  - `tools/list` mirrors `describe` (names, descriptions, input/output schemas, annotations);
  - a read call maps `ok:true` text, an object to `structuredContent`, and `ok:false` to `isError`.

  Section "supervisor": the scripted bridge emits a frame over 4 MiB → that call is `isError` with the `internal` sentence and the child is gone; it exits mid-call → `isError` with `internal`, and the next call respawns it and succeeds. Also add `verb_names_absent`: a test that reads every file under `M/src/` and asserts that none of the twelve verb names appears. Run `cargo test --manifest-path interfaces/mcp/Cargo.toml` and see the list/supervisor cases fail on `todo!()`. `verb_names_absent` already passes. (plan T036, T033 grep test)

- [x] T018 Implement `M/src/bridge.rs` (replacing the T017 stub), the child supervisor and the protocol client, per contracts/bridge-protocol.md §Rust-side obligations.
  - **Spawn:** `struct Bridge` spawns `tokio::process::Command` from either `--bridge-cmd` argv or `<repo>/.venv/bin/python -m sdlc.operator.bridge` (`Scripts\python.exe` on Windows; `SDLC_MCP_PYTHON` overrides), with:
    - `current_dir(repo)`;
    - `kill_on_drop(true)`;
    - piped stdin/stdout and inherited stderr;
    - `#[cfg(target_os = "linux")]` `pre_exec` with `libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM)`.
  - **Protocol:**
    - a reader task;
    - `HashMap<String, oneshot::Sender<Frame>>` for terminal frames and `mpsc` senders for `progress`;
    - `init` and `describe` with a 20 s timeout;
    - `preview`, `call` and `cancel` methods;
    - frames over 4 MiB or unparsable → kill the child and fail in-flight calls with the `internal` sentence;
    - lazy respawn on the next call.
  - **No verb names.** Verify with `cargo test --manifest-path interfaces/mcp/Cargo.toml supervisor` → green. (plan T033)
- [x] T019 Implement `M/src/server.rs` (reads only for now) and `M/src/main.rs`, replacing the T017 stubs.
  - **`main.rs`:**
    - args `--repo <path>` (env fallback `SDLC_REPO_ROOT`, else exit 2 with usage on stderr) and `--bridge-cmd <argv…>` (rest of args);
    - `SDLC_MCP_ACTOR` validated via `actor::validate_override` (exit 2 on error);
    - `tracing_subscriber::fmt().with_writer(std::io::stderr)`;
    - `Server::new(cfg).serve(stdio()).await?.waiting().await`.
  - **`server.rs`, `impl ServerHandler`:**
    - `get_info`: tools capability only;
    - `initialize`: store the negotiated protocol version and whether the client declared elicitation, then `negotiate_initialize`;
    - `on_initialized`: actor = override, or `normalise(peer_info().client_info.name)`; spawn the `Bridge`;
    - `list_tools`: await `describe` (20 s), map each descriptor to `rmcp::model::Tool` with `ToolAnnotations::new().read_only(..)`, and for writes `.destructive(true).idempotent(false)`, `.open_world(false)`; `output_schema` when non-null;
    - `call_tool` for `confirm == "none"`: bridge `call` → result mapping per contracts/mcp-tools.md §Result rules (text → one text block; object → `structuredContent` + JSON text; `ok:false` → `isError: true` with the message).

  Confirm tools return the fail-closed sentence until US2 lands. Verify with `cargo test --manifest-path interfaces/mcp/Cargo.toml` (list + supervisor green) and `cargo clippy --manifest-path interfaces/mcp/Cargo.toml --all-targets -- -D warnings`. (plan T031, T034 part)
- [x] T020 [P] Write the test-only `T/mcp_stdio_client.py`, a raw JSON-RPC 2.0 client over a subprocess's stdin/stdout with no new dependency. It provides:
  - `initialize(protocol_version, capabilities, client_name)`;
  - `list_tools()`;
  - `call_tool(name, args, progress_token=None, meta=None)`;
  - a scripted elicitation responder (`accept` / `decline` / `cancel` / `content`) for `elicitation/create` requests;
  - `call_tool_mrtr(name, args, responses)` handling `InputRequiredResult` by retrying with `requestState` + `inputResponses`;
  - collection of `notifications/progress`;
  - `cancel(request_id)`;
  - `close()`. (plan T040)

**Checkpoint**: `uv run pytest T/test_task_queue.py T/test_operator_runtime.py T/test_operator_bridge.py T/test_operator_layering.py T/test_operator_agent.py -q` green. `cargo test` green.

---

## Phase 3: User Story 1 — ask an MCP client what is blocked (P1) 🎯 MVP

**Goal**: the nine reads (`list_runs`, `get_run`, `inbox`, `list_projects`, `get_project`, `list_tasks`, `project_events`, `read_artifact`, `follow` — the last without progress, which comes in US4) work end to end over the real binary, byte-identical to chat.

**Independent Test**: `SDLC_MCP_BIN=interfaces/mcp/target/release/kroker-mcp uv run pytest -m mcp T/test_operator_mcp_parity.py -q -k reads` passes.

- [x] T021 [P] [US1] Write failing tests in `T/test_operator_bridge.py`, section "reads". On `T/operator_fakes.fleet()` and `seed_board`, check that `call` for each text verb (`list_runs` with `open`/`closed`/`all`, `get_run` open/closed, `inbox`, `list_projects`, `get_project`, `list_tasks`, `project_events`) returns `value` byte-identical to `await tools.<verb>(deps, **args)` on an identical fresh deps. Also:
  - `get_run("nope")` → `error.code == "tool_error"`, with the message equal to the direct `ToolError.message`;
  - `list_runs(status="bogus")` → `tool_error` naming the allowed values;
  - a bad arg type → `bad_request`, whose message has no argument values;
  - a raw `RuntimeError` inside a fake verb → `internal` with the type-only sentence. (plan T024; spec US1 scenarios 1–3, SC-002, SC-003)
- [x] T022 [US1] Implement `call` for `confirm == "none"` tools in `S/operator/bridge.py`:
  - validate args with the descriptor model (`ValidationError` → `bad_request` with a summary of `loc`/`type` only);
  - `await fn(deps, **validated)`;
  - `str` → `value`, `BaseModel` → `model_dump(mode="json")`;
  - `ToolError` → `tool_error` verbatim; anything else → `internal`, type-only.

  Verify with `uv run pytest T/test_operator_bridge.py -q -k reads`. (plan T023)
- [x] T023 [US1] Create `T/mcp_fake_bridge.py`. It calls `bridge.isolate_stdout()` and then `bridge.serve(...)` with `T/operator_fakes.build_fake_deps(Path(argv[1]), actor)`; `argv[2]` is the record path. Writes from US2 land in the record file. A `--print-in-verb` flag installs a fake verb that `print()`s, for T010's hygiene case. Remove the `xfail` from T010's hygiene case. Verify with `uv run pytest T/test_operator_bridge.py -q`. (plan T040)
- [x] T024 [US1] Create `T/test_operator_mcp_parity.py`. Mark it `pytestmark = pytest.mark.mcp` and skip unless `SDLC_MCP_BIN` names an executable file. It spawns `$SDLC_MCP_BIN --repo <repo> --bridge-cmd <sys.executable> T/mcp_fake_bridge.py <tmp> <record>` through `T/mcp_stdio_client.py`. Section "reads":
  - `tools/list` names == `tools.READ_TOOLS + tools.WRITE_TOOLS`;
  - no schema has `deps`; `decide_gate` has no `thaw_tests`; `start_run` has no `budget_usd`;
  - read tools have `annotations.readOnlyHint == true`;
  - every text read verb's single text block is byte-identical to the direct `tools.<verb>` result on an identical fake fleet;
  - `read_artifact` `structuredContent == ArtifactRead.model_dump(mode="json")`, with `outputSchema` present, `truncated == true` and `next_offset == 32768` on the 100 KB blob;
  - `get_run("nope")` → `isError` with the verbatim sentence. (plan T041; spec US1, US4 scenario 3, FR-002/003/004/008/011, SC-002/003/004)
- [x] T025 [US1] Register the marker in `pyproject.toml` `[tool.pytest.ini_options]`: add `"mcp: spawns the built kroker-mcp binary (scripts/check_mcp.py builds it)"` to `markers` and append ` and not mcp` inside the `addopts` `-m` expression. Verify that `uv run pytest -q --co T/test_operator_mcp_parity.py` collects 0 tests, and that `cargo build --release --manifest-path interfaces/mcp/Cargo.toml && SDLC_MCP_BIN=interfaces/mcp/target/release/kroker-mcp uv run pytest -m mcp T/test_operator_mcp_parity.py -q -k reads` passes. (plan T042)

**Checkpoint**: US1 is shippable on its own: reads work over MCP, and writes are refused with the fail-closed sentence.

---

## Phase 4: User Story 2 — approve a gate or answer a question (P1)

**Goal**: `answer_question` and `decide_gate` are confirmed by elicitation on both protocol paths, fail-closed, TOCTOU-safe, with the actor stamped as reviewer.

**Independent Test**: `SDLC_MCP_BIN=… uv run pytest -m mcp T/test_operator_mcp_parity.py -q -k decide_or_answer`, plus `cargo test --manifest-path interfaces/mcp/Cargo.toml confirm`.

- [x] T026 [P] [US2] Write failing tests in `T/test_operator_bridge.py`, section "pending".
  - **`preview`:**
    - `preview(decide_gate, {run_id, key: GATE.key, outcome: "approve"})` returns `message`, containing the `default_render` title, body and rows plus `Proposed: approve`, and a 64-hex `digest`;
    - the same call twice gives the same digest;
    - a different `outcome` or `text` gives a different digest;
    - `preview` on a question key with `decide_gate` → `tool_error` with `_check_kind`'s sentence; a stale key → the `NoMatch` translation.
  - **Streak:** ten `follow`s, then a `preview`, then the eleventh `follow` is still refused.
  - **`call`:**
    - with `expect_digest` matching → exactly one `submit_gate_decision` in `FakeHandle.signals`, whose `GateDecision.reviewer == "mcp:test"` and `decided_by == "human"`;
    - with no `expect_digest` → `bad_request`, zero signals;
    - with a stale `expect_digest` (mutate the fake pending item's body between preview and call) → `error.code == "changed"` with the verbatim sentence, zero signals;
    - `answer_question` → one `answer_question` signal with `(key, text)`;
    - `confirmed=false` (the fake handle keeps the item pending) → `ok: true` with `confirmed: false`;
    - every write logs `mcp write actor=mcp:test tool=… run=… key=… confirmed=…` to stderr (`caplog`). (plan T024; spec US2 scenarios 1–3, FR-005/006/007, SC-005)
- [x] T027 [US2] Implement `preview` and `call` for `confirm == "pending"` in `S/operator/bridge.py`:
  - `preview`: handle via `deps.poller._client_or_connect()`, then `transport.resolve_key`, then `tools._check_kind(pending, want)`, then `default_render`; message and digest per data-model.md PreviewResult; no `note_other_tool`; errors via `translate`;
  - `call`: require `expect_digest`, recompute the preview and compare (mismatch → `changed`), then `await tools.answer_question/decide_gate(deps, **args)`, then the INFO write log line.

  Verify with `uv run pytest T/test_operator_bridge.py -q -k pending`. (plan T022, T023)
- [x] T028 [P] [US2] Write the failing `M/tests/server.rs` section "confirm" **before** T029. First add `M/src/confirm.rs` as a stub: `confirm_and_call` always returns the no-confirmation sentence, and `server.rs` routes `confirm != "none"` to it. The accept cases then fail for the expected reason (no `call` reaches the bridge), while the fail-closed cases already pass. The section covers, with scripted client capabilities and responses:
  - **E1:** accept → bridge receives `call` with `expect_digest`; decline / cancel / timeout (`tokio::time::pause`) → no `call` sent, with the did-not-confirm sentence; no elicitation capability → the no-confirmation sentence and no `call`;
  - **E2:** accept-on-retry → one `call`; a tampered `requestState` → invalid; the same `requestState` replayed → invalid and still one `call`; a swapped-args retry → invalid; expired (`exp` in the past via an injected clock) → invalid;
  - **Bridge errors:** a bridge `changed` error surfaces verbatim as `isError`; a preview `ok:false` → `isError` and no elicitation sent.

  Run `cargo test --manifest-path interfaces/mcp/Cargo.toml confirm` and see the accept, E2 and replay cases fail. (plan T036)
- [x] T029 [US2] Implement `M/src/confirm.rs` (E1, E2, fail-closed), replacing the T028 stub, per research R4 and contracts/mcp-tools.md §Write confirmation.
  - **Form and key:** `#[derive(Deserialize, JsonSchema)] struct Confirm { confirm: bool }` with no `#[serde(default)]`, plus `elicit_safe!(Confirm)`. The session `state_key: [u8; 32]` comes from `getrandom` at startup, with `RequestStateCodec::try_new(&state_key)`.
  - **Flow:** `async fn confirm_and_call(session, bridge, tool, args, ctx) -> CallToolResponse`:
    1. bridge `preview` (an `ok:false` result → `isError` with its message, and no prompt);
    2. branch on the session's elicitation mode:
       - `E1` → `peer.elicit_with_timeout::<Confirm>(message, Some(300s))`;
       - `E2` (first call, no `request_state`) → `CallToolResponse::InputRequired(InputRequiredResult::new(Some(InputRequests{"confirm": InputRequest::Elicitation(..)}), Some(codec.seal_json(&SealedState{jti, tool, args_sha256, digest, exp})?)))`;
       - `E2` retry → `open_json` (failure → the invalid-confirmation sentence), then check `tool`/`args_sha256`/`exp`/`consumed_jti` (map bounded to 1024; when full of unexpired entries → the invalid-confirmation sentence), mark the jti consumed, and read `input_responses["confirm"]`;
       - `None` → the no-confirmation sentence;
    3. on accept with `confirm == true` → bridge `call` with `expect_digest = digest`; on decline, cancel, timeout, `confirm == false` or a schema failure → the did-not-confirm sentence.

  `args_sha256` is the SHA-256 of `serde_json` canonical bytes (keys sorted). Wire `server.rs` `call_tool` to `confirm_and_call` for `confirm != "none"`. Every sentence is verbatim from contracts/mcp-tools.md. Verify with `cargo test --manifest-path interfaces/mcp/Cargo.toml confirm` → green, then `cargo clippy --manifest-path interfaces/mcp/Cargo.toml --all-targets -- -D warnings`. (plan T035, T034)
- [x] T030 [US2] Extend `T/test_operator_mcp_parity.py`, section "decide_or_answer", over the real binary with `client_name = "parity-client"`:
  - **E1** (protocol `2025-11-25`, elicitation capability, scripted accept): `decide_gate` → `isError == false`, `structuredContent.confirmed == true`, and the record file shows exactly one `submit_gate_decision` with `reviewer == "mcp:parity-client"`; the elicitation message the client received contains the gate's `default_render` title;
  - **E1** scripted decline → the did-not-confirm sentence, zero signals;
  - no elicitation capability → the no-confirmation sentence, zero signals;
  - **E2** (protocol `2026-07-28`): accept via `call_tool_mrtr` → one signal; replaying the same `requestState` → the invalid-confirmation sentence, still one signal;
  - `answer_question` E1 accept → one `answer_question` signal;
  - a key the fake reports still pending after the signal → `confirmed == false` and `isError == false`;
  - write tools have `annotations.destructiveHint == true` and `readOnlyHint == false`. (plan T041; spec US2 scenarios 1–5, FR-005/006/007, SC-001, SC-005)

**Checkpoint**: US1 + US2 close US-7's MCP half (inbox plus decisions over MCP).

---

## Phase 5: User Story 3 — start a run from the assistant (P2)

**Goal**: `start_run` is confirmed against a summary of the run that would start, with the B4 cap, the brownfield-repo rule, the slug rule and duplicate-id handling surfaced verbatim.

**Independent Test**: `SDLC_MCP_BIN=… uv run pytest -m mcp T/test_operator_mcp_parity.py -q -k start`.

- [x] T031 [P] [US3] Write failing tests in `T/test_operator_bridge.py`, section "start".
  - **`preview(start_run, {title, mode, description, repo})`:**
    - the `message` lists the title, mode, repo and description;
    - with `SDLC_FLEET_PENDING_CAP` (read by `fleet_pending_cap`, `S/dashboard/fleet.py:316`) set, the message includes `fleet: <pending>/<cap>`;
    - the digest covers args only.
  - **`call` with a matching digest:**
    - the recording starter gets the `IdeaBrief` and `wf_id == "feature-<slug>"`, and `value` is the starter's id;
    - brownfield with no repo → `tool_error` with the verb's sentence, and the starter is not called;
    - the fleet at its cap → the B4 sentence, and the starter is not called;
    - a title of `"!!!"` → the slug sentence;
    - a starter raising `already started` → the duplicate sentence.
  - **Mismatches:** an args-swapped `expect_digest` → `changed`, and the starter is not called. (plan T024; spec US3 scenarios 1–3)
- [x] T032 [US3] Implement the `confirm == "start"` path in `S/operator/bridge.py`: `preview` builds the message from the args plus `fleet_pending_cap()` and, only when a cap is set, `await deps.poller.snapshot()`. The digest = sha256 of canonical `{tool, args, rendered: null}`. `call` re-checks the digest and then awaits `tools.start_run`. Verify with `uv run pytest T/test_operator_bridge.py -q -k start`. (plan T022, T023)
- [x] T033 [US3] Extend `T/test_operator_mcp_parity.py`, section "start", over the real binary (E1, `client_name = "parity-client"`):
  - accept → the record shows exactly one start with `wf_id == "feature-add-sso"`, and the elicitation message names the title and mode;
  - decline → zero starts;
  - brownfield without `repo`, accepted → `isError` with the verb's verbatim brownfield sentence and zero starts. The preview succeeds, so the refusal comes from `tools.start_run` after confirmation. (plan T041; spec US3)

---

## Phase 6: User Story 4 — follow a run and read its artifacts (P3)

**Goal**: `follow` streams progress, honours cancellation and keeps the per-session brake. `read_artifact` paging is unchanged (its parity was already covered in T024).

**Independent Test**: `uv run pytest T/test_operator_bridge.py -q -k follow`, plus `cargo test --manifest-path interfaces/mcp/Cargo.toml progress`.

- [x] T034 [P] [US4] Write failing tests in `T/test_operator_bridge.py`, section "follow":
  - a `follow(run_id, timeout_s=31)` on an unchanging `FakePoller`, with the bridge's progress interval injected as 0.01 s and `MIN_TIMEOUT_S` respected → at least one `progress` frame with the same `id` before the terminal `result` with `timed_out == true`;
  - putting a snapshot with a new pending item into the queue → an early return with `changed` naming it;
  - `cancel(id)` mid-wait → a terminal `cancelled` frame, and `FakePoller` reports its subscription closed;
  - eleven consecutive follows → the eleventh is a `tool_error` with the brake sentence;
  - a `list_runs` in between resets the streak. (plan T024; spec US4 scenarios 1–2, FR-009/010)
- [x] T035 [US4] Implement progress and cancel in `S/operator/bridge.py`. For `PROGRESS` tools, run the verb as a task and, every `PROGRESS_INTERVAL_S = 15` (overridable in `serve()` for tests), emit `{"op":"progress","id","elapsed_s","message"}` until it finishes. `cancel` cancels the task, and the terminal frame is `cancelled`. Verify with `uv run pytest T/test_operator_bridge.py -q -k follow`. (plan T023)
- [x] T036 [P] [US4] Rust progress and cancel forwarding in `M/src/server.rs`, test first. Write `M/tests/server.rs` section "progress" and run it red: the scripted bridge emits two `progress` frames, and a client with a token must receive two notifications (and none without a token); a client cancel must reach the bridge as `cancel`. Then implement:
  - read `ctx.meta` `"progressToken"` (`NumberOrString`); for each bridge `progress` frame, call `peer.notify_progress(ProgressNotificationParam{progress_token, progress: elapsed_s, total: None, message})`;
  - `on_cancelled` maps the MCP request id to the bridge id and sends `cancel`.

  Verify with `cargo test --manifest-path interfaces/mcp/Cargo.toml progress` → green. (plan T034, T036)

---

## Phase 7: Polish & cross-cutting

- [x] T037 Create `scripts/check_mcp.py`, modelled on `scripts/check_ui.py`, with a module docstring stating the `test_verify.py` parity reason.
  - **Locate cargo:** `shutil.which("cargo")`. If it is absent: when `os.environ.get("CI")` is unset, print `mcp gate: SKIPPED (cargo not found)` and exit 0; otherwise print an error and exit 1.
  - **Run, in order, stopping at the first failure:**
    1. `cargo fmt --manifest-path interfaces/mcp/Cargo.toml --check`
    2. `cargo clippy --manifest-path interfaces/mcp/Cargo.toml --all-targets -- -D warnings`
    3. `cargo test --manifest-path interfaces/mcp/Cargo.toml`
    4. `cargo build --release --manifest-path interfaces/mcp/Cargo.toml`
    5. `sys.executable -m pytest -m mcp tests/test_operator_mcp_parity.py -q`, with `SDLC_MCP_BIN=interfaces/mcp/target/release/kroker-mcp` (`.exe` on Windows)
  - **On success:** print `mcp gate: ok`.

  Verify with `python scripts/check_mcp.py` → `mcp gate: ok`. Also, with `PATH` stripped of cargo, the run gives `SKIPPED` and exits 0, and with `CI=1` it exits 1. (plan T050)
- [x] T038 Wire the gate into CI and verify.
  - **`.github/workflows/ci.yml`, new job `mcp`** (`runs-on: ubuntu-latest`):
    - `actions/checkout`;
    - `actions/setup-python` with `python-version: "3.13"`;
    - `astral-sh/setup-uv` as the existing jobs use it;
    - `run: uv sync --frozen --extra dev`;
    - `Swatinem/rust-cache` with `workspaces: interfaces/mcp`, pinned to a major tag as the other actions are;
    - one step `name: MCP gate`, `run: python scripts/check_mcp.py`, with a comment pointing at `tests/test_verify.py`.

    rustup on the runner honours `interfaces/mcp/rust-toolchain.toml`.
  - **`scripts/verify.py`:** add `("mcp", [sys.executable, "scripts/check_mcp.py"])` to `GATES` after `"ui"`.

  Verify with `uv run pytest tests/test_verify.py -q`. (plan T051)
- [x] T039 [P] Write the docs under `M/`.
  - **`M/README.md`:**
    - prerequisites;
    - the build command;
    - the Claude Code (`claude mcp add kroker -- <repo>/interfaces/mcp/target/release/kroker-mcp --repo <repo>`) and goose configuration;
    - the env vars (`SDLC_REPO_ROOT`, `SDLC_MCP_PYTHON`, `SDLC_MCP_ACTOR`, `TEMPORAL_HOST`);
    - the twelve tools table, linking `contracts/mcp-tools.md` content;
    - the confirmation requirement and the trust boundary (research R1: auto-accepting clients or hooks bypass the human gate by client policy; auto-decline means nothing changes; clients without elicitation cannot write);
    - the per-session follow brake (a cancelled follow still counts; a bridge respawn restarts the streak);
    - the localhost/no-socket auth posture (FR-014, OQ-11 unchanged).
  - **`M/client-config.example.json`:** the `mcpServers` snippet.
  - **`M/AGENTS.md`:** the local rules (no verb names in Rust; Python owns `bridge-protocol`, bump `BRIDGE_PROTOCOL` on both sides; stdout is MCP-only; the gate is `python scripts/check_mcp.py`; files ≤ 1000 lines).
  - **`interfaces/AGENTS.md`:** a router line for `mcp/` under "Tree layout".

  Verify with `uv run python scripts/check_file_size.py --full`. (plan T060)
- [x] T040 [P] Update docstrings: `S/operator/agent.py` lines 1-5 (E-11's MCP server is the Rust `interfaces/mcp/` binary over `S/operator/bridge.py`, which is this module's sibling consumer of `tools.py`) and `S/operator/tools.py` lines 1-6 (consumers: `agent.py` and `bridge.py`; the membership tuples live here). Verify with `uv run pytest tests/test_operator_layering.py -q`. (plan T061)
- [x] T041 [P] Update the living docs.
  - **`ROADMAP.md`:**
    - `:345` FR-602 becomes `[x]`, with a pointer to `.specify/specs/022-mcp-channel-adapter/`;
    - the E-11 line is amended to "Rust `rmcp` server (`interfaces/mcp/`) over a Python verb bridge (`sdlc/operator/bridge.py`) that re-exports `sdlc/operator/tools.py`";
    - the US-7 line (`:505`) closes its MCP half;
    - the Last-verified cell gets a one-sentence entry, with the full entry prepended to `docs/roadmap/last-verified-log.md`.
  - **`ARCHITECTURE.md:886`:** replace the "no `interfaces/mcp/`" note.
  - **`docs/roadmap/filesystem-first.md`:** the E-11 line.

  Verify with `uv run python scripts/check_file_size.py --full`. (plan T062)
- [x] T042 Run the full battery from the repo root and paste the outputs into the hand-off:
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy`
  - `uv run python scripts/check_file_size.py --full`
  - `uv run pytest -q`: diff the FAILED ids against `.specify/specs/022-mcp-channel-adapter/baseline-failures.txt` (T001); a novel id is a STOP
  - `python scripts/check_mcp.py`

  Then walk `quickstart.md` §Manual end-to-end steps 1–5 if a real MCP client and Temporal are available, and record whether it was run or skipped. Stage only the paths listed in plan.md §Source code touched, plus this round's `.specify/specs/022-mcp-channel-adapter/` files. (plan T070)

---

## Dependencies & execution order

- **Setup:** T001 → everything. T002 → T014.
- **Foundational, Python:** T003 → T004 → T005. T006 ∥ T003. T007 → T010 → T011 → T012 → T013. T008 → T027. T009 → T010, T021, T023.
- **Foundational, Rust:** T014 → T015 → T019. T014 + T016 → T017 → T018 → T019. T016 ∥ T020 ∥ T014.
- **US1:** needs T013, T019, T020. T021 → T022 → T023 → T024 → T025.
- **US2:** needs US1 (it shares the bridge `call` path and the parity harness). T026 → T027. T028 → T029. T027 + T029 → T030.
- **US3:** needs T027/T029 (the confirm machinery). T031 → T032 → T033.
- **US4:** needs US1. It is independent of US2/US3, except that T034 follows T032 (both edit `T/test_operator_bridge.py` / `S/operator/bridge.py`). T034 → T035. T036 needs T019.
- **Polish:** T037 needs T025. T038 needs T037. T039–T041 run in parallel. T042 is last.

## Parallel examples

- **Foundational:** T003, T006, T009, T014, T016 and T020 touch disjoint files and can start together after T001/T002.
- **US1:** T021 (bridge tests) ∥ T020 (client) while T019 lands.
- **US2:** T026 (Python tests) ∥ T028 (Rust confirm tests); then T027 ∥ T029.
- **US3 / US4** once T027/T029 exist: T031 ∥ T036 (Python test file vs Rust), and T034 ∥ T036. The two Python pairs share `T/test_operator_bridge.py` and `S/operator/bridge.py`, so they run in sequence: T031 → T032 → T034 → T035.
- **Polish:** T039 ∥ T040 ∥ T041.

## Implementation strategy

1. **MVP = Phase 1 + 2 + US1.** Read-only MCP over the real binary, with writes refused fail-closed. This is shippable on its own and safe.
2. **+ US2:** closes US-7's MCP half (FR-602's answer/decide), the highest operator value.
3. **+ US3:** `start_run`.
4. **+ US4:** follow progress and cancel.
5. **Polish:** the gate, CI and docs. T042 is the done-claim gate, and no done-claim comes before it.

## Traceability

| Spec item | Tasks |
|---|---|
| FR-001 Rust + parity | T014–T020, T024, T030 |
| FR-002 twelve verbs, membership | T007, T012, T013, T024 |
| FR-003 result shapes | T017, T019, T022, T024 |
| FR-004 errors verbatim | T021, T022, T024 |
| FR-005 elicitation fail-closed, E1+E2 | T026–T030, T031–T033 |
| FR-006 confirmed=false not an error | T026, T030 |
| FR-007 actor | T015, T019, T026, T030 |
| FR-008 no thaw_tests / budget_usd | T012, T024 |
| FR-009 per-session brake | T026 (preview leaves the streak alone), T034 |
| FR-010 progress / cancel | T034–T036 |
| FR-011 paging | T024 |
| FR-012 stdio | T019 |
| FR-013 HTTP later | not built (README note T039) |
| FR-014 auth posture | T039 |
| FR-015 layering | T004, T007, T010 |
| FR-016 pins | T014 |
| FR-017 file size | T006, T042 |
| FR-018 docs | T039–T041 |
| SC-001 three-call path | T030, quickstart manual 3–4 (T042) |
| SC-002 byte-identical | T021, T024 |
| SC-003 verbatim errors, no raw exceptions | T021, T024 |
| SC-004 drift caught pre-merge | T024 + T037/T038 (CI `mcp` job) |
| SC-005 confirmation + actor | T026, T028, T029, T030 |
| SC-006 dashboard unaffected | T005, T042 |
