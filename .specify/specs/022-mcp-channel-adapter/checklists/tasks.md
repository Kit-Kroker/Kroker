VERDICT: approve

Three gaps, all doc-level in tasks.md itself; the task graph's substance
(coverage, ordering of stories, constraints, citations) is sound. Gaps 1 and
2 hit the brief's explicit checks; fix them and this file is approvable
without another full pass.

1. **T016, T017, T028 — implementation tasks whose tests land later**
   (tasks.md §Dependencies: "T016 → T017 → T020", "T028 → T029"). The
   file's own preamble and the brief require the test written first and seen
   failing before the implementation. The Python side complies
   (T010→T011, T012→T013, T021→T022, T026→T027, T031→T032, T034→T035), but
   on the Rust side: T016 (`M/src/bridge.rs` — supervisor, respawn, frame
   errors) is verified only by `cargo build`, its behaviour first tested in
   T020/T036; T017 (`M/src/server.rs` — initialize, list_tools, result
   mapping) only by clippy, tested in T020; T028 (`M/src/confirm.rs` — E1,
   E2, fail-closed, the entire write-confirmation behaviour) only by
   clippy, tested in T029. Fix: move each Rust test section into or ahead
   of its implementation task (the T015/T036 tests-in-the-same-task pattern
   is acceptable, with the failing run spelled out), or state the Rust
   carve-out explicitly in the Tests preamble.
2. **T031/T034 and T032/T035 — §Parallel examples claims same-file
   parallelism** (tasks.md §Parallel examples, last US bullet: "T034/T035
   (Python follow) ∥ T031/T032 (Python start)"). The file's `[P]`
   definition requires different files: T031 and T034 both append sections
   to `T/test_operator_bridge.py`, and T032 and T032's counterpart T035
   both edit `S/operator/bridge.py` (start path vs progress/cancel). The
   020/021 convention is that same-file sequels are never claimed parallel.
   The individual `[P]` markers survive against Rust partners (T031∥T029,
   T034∥T036, T039∥T040∥T041 — all disjoint); the bullet does not. Fix:
   reword the bullet to keep only the Python∥Rust pairs and sequence the
   two shared-file pairs.
3. **T010 cites the wrong xfail-removal task: "until T026 lands"** (tasks.md
   T010, final line). The hygiene xfail is removed in **T023**, which
   creates `T/mcp_fake_bridge.py` with `--print-in-verb` and says "Remove
   the `xfail` from T010's hygiene case"; T026 is US2's "pending" bridge
   tests and never touches the fake bridge. One-token fix.

# Tasks Quality Checklist: MCP server as a channel adapter (E-11, round 022, pass 1)

**Purpose**: validate tasks.md by spec-kit's tasks checklist method — strict
format, executability without extra context, dependency order, traceability,
no placeholders — plus the reviewer brief's consistency checks (plan-id
coverage, FR/SC coverage, GATE 1 rulings, skeptic dispositions landing in
tasks, implementer rules, test-first, `[P]` truth, story labels, path
spot-checks).
**Created**: 2026-11-14 | **Feature**: [tasks.md](../tasks.md) ·
[plan.md](../plan.md) (approved pass 2) · [spec.md](../spec.md) (GATE 1) |
**Base**: `main` at `eb3552b5` (current HEAD; all cites verified in this
tree).

## Format

- [x] CHK001 - Is every task in the strict format
  `- [ ] Txxx [P?] [USn?] description with exact path`? [Clarity] — T001–T042
  sequential, ids unique, all unchecked, every task names concrete paths,
  commands or both; new files explicitly marked new (`S/task_queue.py`,
  `S/operator/runtime.py`, `S/operator/bridge.py`, `T/operator_fakes.py`,
  `T/mcp_stdio_client.py`, `T/mcp_fake_bridge.py`, `M/` tree,
  `M/tests/fixtures/fake_bridge.py`, `scripts/check_mcp.py`, the three test
  files, `baseline-failures.txt`).
- [x] CHK002 - Placeholders? [Clarity] — None (sweep clean over tasks.md).

## Plan coverage (plan T010–T070 → tasks.md)

- [x] CHK003 - Is every plan task implemented and cited `(plan Txxx)`?
  [Traceability] — All 25 plan ids: T010→T003; T011→T004/T005; T012→T006;
  T013→T007; T020→T011; T021→T013; T022→T008/T027/T032; T023→T022/T027/
  T032/T035; T024→T010/T012/T021/T026/T031/T034; T030→T014; T031→T017;
  T032→T015; T033→T016/T020 (grep test); T034→T017/T028/T036; T035→T028;
  T036→T020/T029/T036; T040→T018/T023; T041→T024/T030/T033; T042→T025;
  T050→T037; T051→T038; T060→T039; T061→T040; T062→T041; T070→T001/T042.
  Nothing dropped; every plan T024 test bullet and every plan T041 parity
  assertion lands in a named task.

## FR / SC coverage

- [x] CHK004 - FR-001..FR-018 and SC-001..SC-006 covered? [Coverage] — All
  twenty-four rows present with named task ids, verified against the task
  list: FR-001→T014–T017, T020, T024, T030; FR-002→T007, T012, T013, T024;
  FR-003→T017, T022, T024; FR-004→T021, T022, T024; FR-005→T026–T030,
  T031–T033; FR-006→T026, T030; FR-007→T015, T017, T026, T030; FR-008→T012,
  T024; FR-009→T026, T034; FR-010→T034–T036; FR-011→T024; FR-012→T017;
  FR-013→not built (README note T039); FR-014→T039; FR-015→T004, T007, T010;
  FR-016→T014; FR-017→T006, T042; FR-018→T039–T041; SC-001→T030 + quickstart
  manual 3–4 (T042); SC-002→T021, T024; SC-003→T021, T024; SC-004→T024 +
  T037/T038; SC-005→T026, T029, T030; SC-006→T005, T042. Every id named is a
  defined task.

## GATE 1 rulings reflected

- [x] CHK005 - Rust on rmcp? [Consistency] — T014 (crate, `rmcp ~3.10`,
  feature set, `rust-toolchain.toml`), T015–T017, T028; T002 records the
  toolchain prerequisite; no Python-MCP fallback anywhere.
- [x] CHK006 - Elicitation fail-closed on both E1 and E2, with the
  no-support consequence? [Consistency] — T028 implements E1
  (`elicit_with_timeout`, no-default `Confirm`), E2 (MRTR `InputRequired` +
  sealed single-use `requestState`) and `None` → the no-confirmation
  sentence; T029 exercises accept/decline/cancel/timeout/no-capability and
  tamper/replay/args-swap/expiry; T030 proves both paths over the real
  binary (protocol `2025-11-25` for E1, `2026-07-28` for E2) with zero
  signals on every refusal; T017 keeps writes fail-closed before US2 lands.
- [x] CHK007 - All twelve verbs? [Coverage] — T012 (12 names, same order),
  T021 (eight text verbs + follow parity), T024 (`tools/list` membership ==
  `READ_TOOLS + WRITE_TOOLS`), read_artifact/follow structured parity in
  T024, writes in T026–T033.

## Skeptic dispositions land in tasks

- [x] CHK008 - Each disposition concretely tasked? [Traceability] — TOCTOU
  digest → T026 (stale digest → `changed`, zero signals) + T027 (recompute
  preview inside `call`) + T031 (args-swapped digest); sealed single-use
  requestState → T028 (`SealedState`, `consumed_jti` bounded 1024, CSPRNG
  key) + T029 + T030 (replay over the real wire); runtime extraction →
  T004/T005; stdout fd hygiene → T011 `isolate_stdout()` + T010's subprocess
  stray-`print` case (xfail until T023) + T023; kill_on_drop + PDEATHSIG →
  T016; real-binary parity → T024/T030/T033; Cargo.lock exemption → T006
  (+ T014 commits the lock); single check_mcp gate + verify.py parity →
  T037/T038; actor regex → T015 (normalise + override validation) + T011
  (init) + T017 (exit 2); answer actor gap scoped → T026's per-write stderr
  log + spec FR-007/SC-005 scoping; thaw_tests/budget_usd negatives → T012,
  T024; follow progress/cancel → T034/T035/T036. Nothing unaccounted.

## Implementer rules

- [x] CHK009 - Rules hold? [Consistency] — `T/test_operator_layering.py`
  never edited (stated as a rule + STOP condition; T007/T040 only run it);
  `tools.py` gains exactly the tuples (T007), `_check_kind` (T008) and the
  docstring (T040) — matching plan and the Constitution row; no new Python
  dependency (STOP rule; the bridge is stdlib + pydantic, the stdio client
  test-only stdlib); no `pytest -m temporal` and no `temporal` CLI anywhere
  (T001's baseline is `pytest -q`, fast tier by addopts); no paid runs
  (stated; T042's manual walk is client-side only); shared-tree staging
  (never `git add -A`; T042 stages the plan's named paths only).

## Test-first discipline

- [ ] CHK010 - Tests precede implementation for every new behaviour?
  [Measurability] — Python: yes (T010→T011, T012→T013, T021→T022, T026→T027,
  T031→T032, T034→T035, each with failing-tests-first phrasing; T023's
  xfail-removal is the documented follow-through). Rust: **no** (gap 1) —
  T016 and T017 verify with build/clippy only and are first tested in
  T020/T036; T028 (confirm.rs) in T029. T015/T036 bundle tests with
  implementation in one task — acceptable only if the failing run is spelled
  out.

## Parallel claims

- [ ] CHK011 - Is every `[P]` true (disjoint files, no unmet dependency)?
  [Consistency] — True for T002 (no files), T003/T006/T009/T014/T018/T019
  (all disjoint; the foundational batch), T015 (∥ T016), T021 (∥ T018),
  T026 (∥ T028), T039/T040/T041 (docs/docstrings/roadmap disjoint). **But**
  §Parallel examples additionally asserts T034/T035 ∥ T031/T032, which
  share `T/test_operator_bridge.py` (T031/T034) and `S/operator/bridge.py`
  (T032/T035) — same files, violating the file's own definition (gap 2).

## Story labels and independent tests

- [x] CHK012 - Labels match spec US1–US4? [Traceability] — Phase headers
  restate the spec story titles; [US1] on T021–T025, [US2] on T026–T030,
  [US3] on T031–T033, [US4] on T034–T036; setup, foundational and polish
  unlabelled (020/021 convention). Priorities match the spec (US1/US2 P1,
  US3 P2, US4 P3).
- [x] CHK013 - Phases independently testable? [Measurability] — Each phase
  header carries an Independent Test that matches the spec story's own:
  parity `-k reads` (US1), `-k decide_or_answer` + `cargo test confirm`
  (US2), `-k start` (US3), bridge `-k follow` + `cargo test progress`
  (US4); checkpoints T020/T023-line verify commands run the fast tier and
  cargo per slice.

## Path and citation spot-checks (25+ verified at `eb3552b5`)

- [x] CHK014 - Do cited paths and `file:line` exist (or marked new)?
  [Traceability] — Verified: `src/sdlc/worker.py:128` (`TASK_QUEUE`),
  `src/sdlc/operator/agent.py:85-96` (the tuples T007 moves),
  `src/sdlc/operator/tools.py:469-473` (the `_reply` `kind != want` block
  T008 factors out), `src/sdlc/dashboard/fleet.py:316` (inside
  `fleet_pending_cap`, :310–320, T031's cite), `src/sdlc/channels/
  transport.py:29` (`PENDING_QUERY`), `src/sdlc/core/models.py:152-157`
  (`GateDecision` with `decided_by` Literal incl. "human" and `reviewer` —
  T026's assertions), `src/sdlc/cli.py:481`, `src/sdlc/benchmarks/cli.py:333`,
  `src/sdlc/schedules/apply.py:42` (the re-export consumers T003 keeps
  working), `ROADMAP.md:345` (FR-602), `ROADMAP.md:505` (US-7 "MCP server
  pending"), `ARCHITECTURE.md:886` (the note T041 replaces),
  `docs/roadmap/filesystem-first.md` E-11 line, `scripts/check_ui.py`
  (T037's model), `tests/conftest.py` (dummy keys, T004's premise),
  `tests/test_operator_layering.py`, `test_operator_agent.py`,
  `test_operator_writes.py`, `test_chat_mount.py`, `test_operator_e2e.py`,
  `test_operator_tools_board.py`, `test_operator_read_artifact.py` (T009's
  sources), `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`
  (T001's diff base). One stale cross-reference found (gap 3: T010's
  "until T026 lands" — the xfail is removed by T023).

## Notes

- The task graph is sound and complete: every plan id and every FR/SC is
  covered, the GATE 1 rulings and all fifteen skeptic dispositions land in
  concrete tasks, the implementer rules are stated as enforceable rules with
  STOP conditions, and the MVP (Phase 1+2+US1) is a shippable, fail-closed
  slice. All three gaps are documentation-level fixes inside tasks.md;
  none changes what is built, only the stated discipline (test-first on the
  Rust side), one parallelism sentence, and one task-id cross-reference.
- Per the 020 precedent (a single doc-level gap still drew fixes-needed),
  gaps 1–2 require a fixes-needed verdict; gap 1 in particular contradicts
  the file's own Tests preamble.

## Pass 2 (2026-11-14)

The three pass-1 gaps re-checked against the renumbered tasks.md, plus the
mandated fresh stale-id sweep over the renumbered range (T016–T020,
T028–T029). **Gaps 1 and 2 resolved; gap 3 half-fixed, and the sweep finds
one more stale id — two one-token fixes remain.**

1. **RESOLVED — Rust test-first.** T017 now writes the failing
   `M/tests/server.rs` "list" + "supervisor" sections **before** T018/T019,
   against compiling `todo!()` stubs ("fail at runtime for the expected
   reason, not with a compile error"), and runs them red; T018/T019 then
   implement `bridge.rs` / `server.rs`/`main.rs` and turn the same tests
   green. T028 writes the failing "confirm" section against a fail-closed
   `confirm.rs` stub before T029 implements it (accept/E2/replay cases red,
   fail-closed cases already passing — the expected split). T036 is
   test-first in-task ("Write … section 'progress' and run it red … Then
   implement"), and the Tests preamble now states the Rust
   red-against-stub rule with the correct new ids, plus T015/T036's
   in-task red runs. The dependency chain (T014+T016 → T017 → T018 → T019;
   T028 → T029) matches.
2. **RESOLVED — parallel examples.** The US3/US4 bullet now claims only the
   Python∥Rust pairs (T031 ∥ T036, T034 ∥ T036 — disjoint files) and
   sequences the shared-file Python pairs explicitly: T031 → T032 → T034 →
   T035, with §Dependencies noting "T034 follows T032 (both edit
   `T/test_operator_bridge.py` / `S/operator/bridge.py`)". All remaining
   `[P]` markers hold against disjoint partners (T016 ∥ T020 ∥ T014 in the
   foundational batch; T021 ∥ T020 while T019 lands; T026 ∥ T028 then
   T027 ∥ T029; T039 ∥ T040 ∥ T041).
3. **PARTIALLY RESOLVED — T010's stale xfail cite.** The trailing sentence
   (tasks.md:118) now correctly says "until T023 lands". **But the same
   bullet's file-creation parenthetical is still stale** (tasks.md:116): "a
   subprocess run of `T/mcp_fake_bridge.py` (**T026**)" — the fake bridge is
   created by **T023** (tasks.md:234); T026 is US2's "pending" bridge tests
   and creates nothing. One-token fix: `(T023)`.
4. **OPEN (new, found by the mandated stale-id sweep) — the implementer
   rules cite the old T020** (tasks.md:27): "Rust sources under `M/src/`
   never name any of the twelve verbs (**T020** enforces this)". The
   `verb_names_absent` grep test lives in **T017** (tasks.md:173) after the
   renumbering; T020 is now the Python stdio client. One-token fix:
   "(T017 enforces this)".

Fresh sweep, rest of the renumbered range clean: preamble (T017 → T018/T019,
T028 → T029, T015/T036) ✓; T018/T019/T029 "replacing the T017/T028 stub(s)"
✓; §Dependencies (US1 needs T013, T019, T020; US3 needs T027/T029; T036
needs T019) ✓; §Parallel examples (foundational batch renumbered to
T003/T006/T009/T014/T016/T020; "while T019 lands") ✓; §Traceability
correctly renumbered (FR-001 T014–T020; FR-003 T017, T019; FR-007 T015,
T019; FR-012 T019; SC-005 +T028/T029) ✓. Notes, not gaps: the Checkpoint
line lost its blank line before it (cosmetic); §Dependencies does not state
T015 → T019 explicitly, though T019's own text names `actor::validate_override`,
so the need is discoverable in place.

**Verdict: fixes-needed** — items 3 and 4 only; both are single-token
cross-reference fixes inside tasks.md. Everything else from pass 1 stands
with the renumbering folded in.

## Pass 3 (2026-11-14)

The two pass-2 residuals re-checked, plus a quick stale-id sweep. **Both
resolved; tasks.md is approved.**

3. **RESOLVED — T010's parenthetical** (tasks.md:116): now reads
   "`T/mcp_fake_bridge.py` (T023)", consistent with line 118's "until T023
   lands" and T023's own creation of the fake bridge. No `(T026)` cite
   remains anywhere in the file.
4. **RESOLVED — the implementer rule** (tasks.md:27): now reads "(T017
   enforces this)", matching `verb_names_absent`'s home in T017.

Notes applied and verified: §Dependencies now states `T014 → T015 → T019`
(the `actor.rs` ordering note from pass 2), and the blank line before the
foundational Checkpoint is restored.

Sweeps: stale-id sweep clean — every `T0xx` cited in prose resolves either
to a defined tasks.md task (T001–T042) or to a plan id inside a
`(plan Txxx)` citation (T050/T051/T060/T061/T062/T070, at lines 46, 364,
377, 392, 393, 403, 412 — exactly the plan-coverage mapping of CHK003);
placeholder sweep clean.

**tasks.md is approved.** All pass-1 checklist items stand with the pass-2
renumbering folded in; CHK010 (test-first) and CHK011 (`[P]` truth) now
pass with the Rust red-against-stub ordering and the corrected parallel
claims, and CHK014's citation record is fully clean.
