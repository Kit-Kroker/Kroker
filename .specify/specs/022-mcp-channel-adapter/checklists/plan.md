VERDICT: approve

Four gaps, all doc-level; no task's work, ordering or safety argument changes.
Gap 1 breaks the SC→task chain the brief explicitly checks and would misdirect
`/speckit-tasks`; fix it and the plan is approvable without another full pass.

1. **Plan §Traceability omits SC-001, SC-003 and SC-004** (plan.md,
   §Traceability, lines 273–297). The table carries all eighteen FR rows plus
   SC-002/SC-005/SC-006 only; `SC-001`, `SC-003` and `SC-004` appear nowhere
   in plan.md (grep: zero hits). The implementing work exists — SC-001 →
   quickstart manual steps 3–4 (inbox → decide_gate → confirm) + T041's
   `decide_gate` E1-accept assertion; SC-003 → T024 "the `ToolError`
   passthrough" + T041 "the `ToolError` wording is verbatim"; SC-004 → T041
   (twelve-verb parity over the real binary) + research R2's per-verb-change
   cost row ("0 Rust, 1 Python") — but the brief's check is "FR-001..FR-018
   and SC-001..SC-006 each map to a plan task … (see plan §Traceability)", and
   three of the six SCs map to nothing there. Same defect class as 021 plan
   pass-1 gap 2 (rows that name no task). Fix: add three rows, e.g.
   `SC-001 three-call path | T041 (decide accept), quickstart manual 3–4`,
   `SC-003 error wording verbatim | T024, T041`,
   `SC-004 drift caught pre-merge | T041 (12 verbs), R2 cost row`.
2. **FR-016 says *every* Rust dependency MUST be pinned to a bounded minor;
   R10/T030 bound only four** (research.md §R10; plan.md T030 "with the pins
   from research R10"). Explicit bounds exist for `rmcp ~3.10`, `tokio ~1`,
   `serde`/`serde_json ~1` and `schemars` (rmcp's major); `sha2`,
   `getrandom`, `uuid`, `libc`, `tracing`/`tracing-subscriber` (and `rand`)
   are named without any bound, so the implementer has no stated policy for
   them and FR-016's own wording is not met as written. Fix: give the
   remaining crates bounded minors (or one blanket sentence: "every crate is
   pinned to a bounded minor exactly as the four above").
3. **Constitution Check table cites the bridge import probe as "(T021)"**
   (plan.md, §Constitution Check, row 3). The probe is defined in **T024**
   (tests/test_operator_bridge.py, last bullet: "the import probe: `import
   sdlc.operator.bridge` loads none of `fastapi`, `starlette`, `pydantic_ai`");
   T021 is `describe`. One-token fix.
4. **spec.md §Test commands keeps a command T042 would silence**
   (spec.md, §Requirements → Test commands). The block lists
   `uv run pytest tests/test_operator_mcp_parity.py tests/test_operator_layering.py -q`;
   once T042 appends `and not mcp` to `addopts`, that invocation deselects
   every test in the parity file and silently runs only the layering file.
   The authoritative lists are correct (plan T050 runs `pytest -m mcp …` with
   `SDLC_MCP_BIN`; quickstart runs `scripts/check_mcp.py`); the spec line
   should match (`pytest -m mcp tests/test_operator_mcp_parity.py` or point at
   `check_mcp.py`), since the block's own header says the final list lives in
   plan.md.

# Plan Quality Checklist: MCP server as a channel adapter (E-11, round 022, pass 1)

**Purpose**: validate plan.md by spec-kit's checklist method — traceability
(FR/SC → plan task → validation), concrete steps, exact paths, explicit test
commands, no placeholders — plus the reviewer brief's consistency checks
(GATE 1 rulings honoured exactly, skeptic L1–L4b/S1–S10 dispositioned and
reflected in tasks, repo constraints, `file:line` spot-checks).
**Created**: 2026-11-14 | **Feature**: [plan.md](../plan.md) · [spec.md](../spec.md)
**Base**: `main` at `eb3552b5` (current HEAD; all cites verified in this tree).

## Content quality

- [x] CHK001 - Placeholder sweep over the artifacts? [Clarity] — Clean
  (TODO/TBD/TKTK/FIXME/???/NEEDS CLARIFICATION: zero hits in spec, plan,
  research, data-model, quickstart, both contracts).
- [x] CHK002 - Steps concrete with exact paths and line anchors? [Clarity] —
  Every task T010–T070 names its file(s), with `:line` anchors for edits and
  explicit "new" markers; the seam-specific placement rows in the spec are
  resolved to a full §Source-code-touched list in the plan.
- [x] CHK003 - Test commands explicit? [Measurability] — T050 is an exact
  command batch with cargo-absent semantics (SKIPPED unless `CI`); T070 is
  the full battery; quickstart gives per-concern commands with expected
  outcomes, incl. the manual client scenario and the `kill -9` orphan check.

## Traceability (FR-001..FR-018, SC-001..SC-006)

- [x] CHK004 - FR-001..FR-018 each map to task(s) and a validation?
  [Traceability] — All eighteen rows present and verified against the task
  list: FR-001→T030–T036, T041; FR-002→T013, T021, T024, T041; FR-003→T023,
  T034, T041; FR-004→T023, T034, T024, T041; FR-005→T022, T023, T035, T036,
  T041; FR-006→T034, T041; FR-007→T021, T032, T034, T041; FR-008→T024, T041;
  FR-009→T020, T024; FR-010→T023, T034, T036; FR-011→T041; FR-012→T031;
  FR-013→"not built" (deferred scope, row present); FR-014→T060;
  FR-015→T013, T024, existing layering test; FR-016→T030; FR-017→T012, T070;
  FR-018→T060–T062.
- [ ] CHK005 - SC-001..SC-006 each map to a plan **task (T0xx)**?
  [Traceability] — **No** (gap 1): SC-002→T024, T041; SC-005→T035, T041;
  SC-006→T011, T070 are present, but SC-001, SC-003 and SC-004 have no row
  and appear nowhere in plan.md.

## GATE 1 rulings honoured exactly

- [x] CHK006 - Q1: server is Rust on official rmcp? [Consistency] — Plan
  Summary + T030–T036; seam (d) excluded; R10 pins `rmcp ~3.10` with the
  feature set; the minority (d) recommendation stays recorded in spec
  §Seam Decision with reopen conditions, as Q1 requires.
- [x] CHK007 - (a)/(b)/(c) re-costed for all twelve verbs against rmcp docs?
  [Coverage] — Research R1 is the rmcp 3.10.0 capability table (verified
  APIs, both elicitation paths, progress, cancellation, client identity);
  R2 re-costs (a′)/(b)/(c) with the twelve verbs enumerated (nine reads +
  three writes), per-verb-change cost, `start_run` feasibility ("no without
  re-architecting" for (c)), and shows original (a) dominated by (a′)
  (no `follow` route, no paged `read_artifact`). Seam (b) locked with
  rationale.
- [x] CHK008 - Q2: elicitation fail-closed, incl. "no support → directing
  error until it does"? [Consistency] — R4 step 5 ("writes stay refused in
  that session until the client supports it"); T035 "None: the fail-closed
  sentence"; refusal text fixed verbatim in contracts/mcp-tools.md; FR-005
  records the consequence; both protocol paths implemented (E1 elicit,
  E2 MRTR InputRequired + sealed requestState), so no version class is
  silently refused.
- [x] CHK009 - Q3: twelve verbs regardless of seam? [Coverage] — FR-002;
  R2's twelve-verb enumeration; T021 `describe` over `READ_TOOLS +
  WRITE_TOOLS`; T024 membership test; T041 asserts the twelve tool names.

## Skeptic disposition (L1–L4b, S1–S10)

- [x] CHK010 - All fifteen findings dispositioned in plan §Skeptic
  disposition? [Coverage] — L1, L2, L3, L4, L4b, S1–S10 each have a row
  (4 BLOCKER, 10 MUST-FIX, 1 ACCEPTABLE); none unaccounted.
- [x] CHK011 - Is each disposition actually reflected in a task?
  [Traceability] — L1→T030 pins/toolchain + T035 E2; L2→R1 client-reality
  research + T035 no-default `Confirm` form + T060 trust-boundary README
  (auto-accept is client policy; auto-decline fails safe); L3→T023
  progress/cancel + T060 streak note (cancelled wait still counts);
  L4→T032 normalisation unit tests (collisions, `../../admin`, control
  chars, 500 chars, empty→`mcp:local`) + spec FR-007/SC-005 scoping of the
  answer-identity gap + T023 per-write actor log; L4b→T024/T041 negative
  schema assertions; S1→T022 pure-read preview (no `note_other_tool`) +
  T023 `expect_digest` re-check + T024 streak/digest tests; S2→T035 sealed
  `{jti, tool, args_sha256, digest, exp}` + 32-byte CSPRNG key + bounded
  single-use `jti` map + T036/T041 tamper/replay/args-swap/expiry tests;
  S3→R3 metadata flags + T021 `CONFIRM`/`PROGRESS` + T033 grep test (no
  verb names in `M/src/`) + "zero per-verb logic" wording; S4→T010/T011
  (`task_queue.py`, `runtime.py`, workflow by name); S5→T024 import probe
  (bridge a leaf; `temporalio` allowed, the trio not); S6→T020
  `isolate_stdout()` before any `sdlc` import + T024 stray-`print`
  subprocess test; S7→T020 EOF cleanup + T033 `kill_on_drop` + Linux
  PDEATHSIG + quickstart `kill -9` check; S8→T041 real-binary parity
  (marker `mcp`, not tautological); S9→T012; S10→T050/T051 single gate
  line + `verify.py` entry + `Swatinem/rust-cache`.
  Minor: the Constitution table's probe cite says T021 where the probe is
  defined in T024 (gap 3).

## Repo constraints

- [x] CHK012 - 1000-line ceiling incl. `Cargo.lock`? [Consistency] — T012
  adds `"Cargo.lock"`/`"*/Cargo.lock"` to `EXEMPT_PATTERNS` beside `uv.lock`
  (verified: `scripts/check_file_size.py` scopes `interfaces/` and today
  exempts only `uv.lock`, `*-lock.json` — which does **not** match
  `Cargo.lock`, so the exemption is genuinely needed); sizes bounded
  (each `.rs` < 400, `bridge.py` < 400, `runtime.py` < 120); nothing added
  to `cli.py` (908).
- [x] CHK013 - `tests/test_operator_layering.py` assertions unchanged?
  [Consistency] — No task edits it (verified against §Source code touched);
  T013's tuples are pure references and `agent.py` keeps `pydantic_ai`, so
  `test_only_agent_py_may_name_a_framework`,
  `test_agent_py_is_the_one_that_does` and the transitive
  `test_importing_tools_does_not_load_a_framework_transitively` (which also
  checks `temporalio`) all still hold.
- [x] CHK014 - No dashboard/worker boot import? [Consistency] — T011 swaps
  `main.py` to `runtime.*` behaviour-preserving (verified `app =
  create_app()` :42, `FleetPoller(_connect)` :53, `include_router` :65,
  `mount_chat` :102, `_connect` :45, `_start` :56); the bridge is spawned as
  `python -m sdlc.operator.bridge` and imports `runtime`, never `main.py`;
  R5's measured import table backs the design; T024's probe enforces it.
- [x] CHK015 - `tests/test_verify.py` parity for the new CI line?
  [Consistency] — T051 adds exactly one `run: python scripts/check_mcp.py`
  line (the `check_ui.py` precedent at `ci.yml:78`) and one
  `("mcp", [sys.executable, "scripts/check_mcp.py"])` gate after `ui`
  (verified `ui` exists in `GATES`); `_gate_key` matches on both sides; the
  ordering test only constrains ruff < mypy < pytest.
- [ ] CHK016 - Bounded pins for every Rust dependency? [Consistency] —
  **Partial** (gap 2): rmcp/tokio/serde/schemars are bounded in R10;
  sha2/getrandom/uuid/libc/tracing(-subscriber)/rand are not, and FR-016
  demands bounds for all.

## Citation spot-checks (20+ verified at `eb3552b5`)

- [x] CHK017 - Do cited paths and `file:line` exist? [Traceability] —
  Verified in the tree: `src/sdlc/worker.py:128` (`TASK_QUEUE = "ai-sdlc"`),
  `src/sdlc/operator/agent.py:85-96` (`READ_TOOLS`/`WRITE_TOOLS`),
  `agent.py:3-5` (mcp.py-sibling docstring), `src/sdlc/cli.py:469`
  (`load_dotenv()`), `cli.py:481` (`from .worker import TASK_QUEUE`),
  `S/benchmarks/cli.py:333` and `S/schedules/apply.py:42` (the re-export
  consumers T010 names), `src/sdlc/channels/contract.py:107-108`
  (ClarifyPending `SignalCall`) and `:182-186` (`ActorChannel.translate`
  reviewer-only), `src/sdlc/operator/tools.py:1-12` (E-11 second consumer)
  and `:416` (`deps.note_follow()`), `deps.py:33-34`
  (`max_artifact_bytes` 32 KB, `max_follow_calls` 10) and `:48`
  (`note_other_tool`), `errors.py` (74 lines; `translate`; "the factory
  raised …" fallback), `interfaces/dashboard/api/main.py:42/53/65/102`,
  `pyproject.toml:39` (`where=["src"]`), `pyproject.toml:122` (addopts, the
  line T042 amends), `ROADMAP.md:345` (FR-602 `- [ ]`), `ARCHITECTURE.md:886`
  ("no `interfaces/mcp/`" note), `docs/superpowers/specs/2026-08-20-operator-chat-surface-design.md`
  §2 D1 (the E-11 HTTP-seam rejection quote), `docs/roadmap/filesystem-first.md:69`
  (E-11 re-export line), `verify.py` GATES (`ui` present),
  `scripts/check_ui.py` exists; no `Cargo.toml` outside `.venv`; `mcp`
  absent from `uv.lock`; `start_graph_run(client, run: Any, …)` duck-typed
  as R5 claims; `FleetPoller`/`BoardStore` where cited; the
  `tests/test_operator_*` fake helpers T024 reuses exist.

## Notes

- The plan's substance is sound: seam (b) with a metadata-driven Rust server
  over a Python-owned bridge contract, dual-path fail-closed elicitation
  with a TOCTOU digest re-check and a sealed single-use requestState, the
  `runtime.py`/`task_queue.py` extraction that keeps the layering test and
  dashboard untouched, and a real-binary parity gate — each concrete,
  tested, and traceable. All four gaps are documentation-level; gap 1 alone
  requires fixes-needed because the brief checks SC traceability through
  §Traceability and `/speckit-tasks` consumes that table.
- The advisor answer is a recovered partial (see its recovery note); the
  plan records the ranking it preserved ((b) > (a′) > (c)) and resolves the
  unrecovered per-decision answers itself, with the skeptic covering the
  same ground adversarially. No open dependency on the lost text remains.

## Pass 2 (2026-11-14)

The four pass-1 gaps re-checked against the edited artifacts, plus a fresh
placeholder and stale-reference sweep. **All resolved.**

1. **RESOLVED — SC traceability rows.** plan.md §Traceability now carries
   all six SC rows (lines 295–300): SC-001 → T041 (`decide_gate` E1 accept),
   quickstart manual steps 3–4; SC-003 → T024 (`ToolError` passthrough),
   T041 (verbatim wording), contracts/bridge-protocol.md `internal`
   sentence; SC-004 → T041 (all twelve verbs over the real binary, in the
   CI `mcp` job via T050/T051) + research R2's per-verb-change cost row
   ("0 Rust, 1 Python"). Every named task is defined in §Phases; the
   quickstart manual steps 3–4 are the inbox → decide_gate → confirm
   scenario SC-001 measures.
2. **RESOLVED — bounded pins for every crate.** research R10 now states the
   blanket rule: "**Every** crate, direct and dev, is written as a bounded
   minor `"~MAJOR.MINOR"` of the version cargo resolves at T030 (e.g.
   `tokio = "~1.N"`). No bare major (`"1"`, `"~1"`) and no `*`", with a
   committed `Cargo.lock` pinning exact versions and upgrades moving bound +
   lock + code in one PR. T030 takes its pins from R10. FR-016 is met as
   written.
3. **RESOLVED — Constitution Check citations.** Row 3 now cites the import
   probe as **(T024)** — where `tests/test_operator_bridge.py` defines it —
   and records the `_check_kind` helper factored out of `_reply` as the
   other `tools.py` change **(T022)**, matching the T022 task text and
   §Source code touched.
4. **RESOLVED — spec §Test commands.** The block now runs the parity file
   as `SDLC_MCP_BIN=interfaces/mcp/target/release/kroker-mcp uv run pytest
   -m mcp tests/test_operator_mcp_parity.py -q` (the marker override makes
   it immune to the T042 `not mcp` addopts filter), names
   `python scripts/check_mcp.py`, and the default-tier line lists
   `tests/test_operator_bridge.py tests/test_operator_layering.py
   tests/test_task_queue.py` — all three files created or kept by named
   tasks (T024, T013, T010).

Sweeps: placeholder sweep over spec, plan, research, data-model, quickstart
and both contracts clean (TODO/TBD/TKTK/FIXME/???/NEEDS CLARIFICATION: zero
hits); stale-reference sweep clean — every `T0xx` id cited anywhere in
plan.md (now including the new SC rows' T041/T050/T051) is defined in
§Phases (T010–T013, T020–T024, T030–T036, T040–T042, T050–T051, T060–T062,
T070), and the SC rows' non-task references (quickstart manual steps,
the bridge-protocol `internal` sentence, R2's cost row) all exist.

**plan.md is approved.** All pass-1 checklist items stand; CHK005 and
CHK016 now pass with gaps 1 and 2 closed, and the gap-3/gap-4 citations
are corrected.
