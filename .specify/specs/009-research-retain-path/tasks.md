# Tasks: Research Retain Path

**Input**: `.specify/specs/009-research-retain-path/` (spec.md, plan.md, research.md, quickstart.md)

**Tests**: required (spec FR-007, SC-001, SC-004, SC-005; plan D3, D4). The one source change is preceded by its RED tasks. Inside a RED task, tests marked PIN pin behaviour that already exists and are expected to pass on first run; a red PIN test is a stop-guard, not a cue to edit source.

`R/` = `src/sdlc/stages/research/`.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (bound to `D:\own\Kroker-007`; see quickstart.md). Never the host venv. Never alongside a live pipeline run. One pytest per command; do not add `-q` (already in `addopts`). Capture with `> <log> 2>&1; echo RC=$?`.
- Read `.workspace/tasks/` for known host hazards before any tier run. `-m temporal` runs in the container only.
- Read the root `AGENTS.md`, `src/sdlc/stages/research/AGENTS.md` and `src/sdlc/workflows/AGENTS.md` before T002.
- RED tasks are written by the qa seat and must be seen failing on the branch for the stated reason before T007 starts. Their files are committed in T007's commit, so no commit on the branch is red. The reviewer gate still applies to each RED diff on its own.
- Commit: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`. Host shell is PowerShell 5.1: no heredocs.
- Reviewer gate is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N.
- **`SDLC_CAPTURE_HISTORIES` is never set.** It re-records every existing replay fixture. The new history has its own switch, used once, in T002.
- Forbidden paths: `R/verify.py`, `R/stage.py`, `R/models.py`, `src/sdlc/workflows/`, `src/sdlc/memory/`, `src/sdlc/grounding.py`, `tests/replay/scenarios.py`, `tests/replay/harness.py`, every existing file under `tests/replay/histories/` and `tests/replay/golden/`, `tests/replay/test_fixtures_present.py`, `tests/replay/test_notify_registration_chaos.py`, `tests/research/test_research_slice_contract.py`, `pyproject.toml`, `uv.lock`, `docs/reports/external-ideas-2026-09.md`, earlier `.specify/specs/*`, and every `AGENTS.md` except the one bullet named in T008. No activity is added, removed, reordered or given different arguments or options. The user's uncommitted files in the primary checkout are not touched.
- Tests use fake activities, stub contexts and the fake memory backend only, with `SDLC_RUNS_ROOT` pointed at a temp directory. No real model call, no network, no credentials.
- Line numbers in spec.md, plan.md and research.md are as of main `d51eef5`; re-locate by symbol, not by number.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** An edit to a forbidden path, a new activity, or a change to `verify_brief_activity` appears necessary.
- **SG-2** Any existing test fails after a change and this file does not name it as an intended edit. Do not edit the test to pass. Never re-record or edit an existing history or golden file.
- **SG-3** The captured history does not hold exactly one `gate_feedback` and two `research_finding` retains, or its two captures disagree. Fix the scenario, not the projection.
- **SG-4** On unmodified source the `absent` or `overwritten` replay row passes, or the `present` row fails.
- **SG-5** After T007 any of the three replay rows fails. Do not re-capture.
- **SG-6** A test this file marks RED passes before T007, or a test marked PIN is red.
- **SG-7** `SDLC_CAPTURE_HISTORIES` is about to be set, or the capture test is about to run after any edit under `src/`.

## Phase order

| Phase | Purpose | Story | Plan | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | — | — | — | 1 |
| 2 The replay fixture and its test (RED) | the defect, recorded | US1 | D3 | 0 (rides T007) |
| 3 The retain contract (RED) | only verified findings | US2 | D1, D4 | 0 (rides T007) |
| 4 The step retains what was verified (RED + PIN) | pairing; failure path | US1, US3 | D2, D4 | 0 (rides T007) |
| 5 The change | all three stories | US1, US2, US3 | D1, D2 | 1 |
| 6 Living docs + verification | — | — | D5 | 2 |

The fixture is recorded in phase 2, before any source edit (Q2 = A). The single source change is in phase 5; it cannot be split, because the step and the retain function change shape together.

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [ ] T001 Create branch `009-research-retain-path` from main `d51eef5` in the `D:\own\Kroker-007` worktree, confirm `kroker-dev` sees it at `/app` and syncs (`uv sync --frozen --extra dev --extra logfire`), run `pytest` and `mypy` once each, and record the base sha, the fast-tier pass count, any pre-existing failures, the mypy error count and the line counts of `R/step.py`, `R/retain.py` and `tests/replay/scenarios.py` in `.specify/specs/009-research-retain-path/baseline.md`. Commit (spec set + baseline)

**Checkpoint**: baseline.md holds base sha, pass count, mypy count; `git diff d51eef5 --stat -- src` is empty.

---

## Phase 2: User Story 1 — a research run replays without its pages (P1), RED

**Goal**: a committed history of a research run with grounded findings and memory on, recorded from the unchanged workflow code, and a test that replays it with the pages present, absent and overwritten (FR-007; plan D3).

**Independent test**: `pytest tests/replay/test_research_retain_replay.py`.

- [ ] T002 [US1] Create `tests/replay/research_retain.py` (not a test module) per plan D3, starting from `.workspace/tmp/research-retain-path-e5.py`: `NAME = "research_retain_grounded"`; `FINDINGS`, two `(url, quote, claim)` tuples; `page_text(quote)`; `BRIEF` built from `FINDINGS`; three fake activities under the production names `plan_research` (one sub-question `sq-0`), `research_subquestion` (writes each page with `verify.write_page(inp.deps.run_id, url, page_text(quote))`, returns a `SubQuestionFinding` carrying `BRIEF`) and `synthesize_brief` (returns `BRIEF` and a zero `RoleUsage`); `cfg()` = the research replay config with `memory.enabled = True` and `memory.backend = "fake"` set explicitly; `activities()` = the `research_greenfield` scenario's registrations with every registration named `plan_research`, `research_subquestion` or `synthesize_brief` dropped, plus the three fakes and the real `capture_watermark`, `recall_snapshot` and `retain`; a driver that waits for `awaiting:clarify`; `SCENARIO = Scenario(NAME, greenfield_idea, cfg, activities, drive, mode="partial", golden=False)`, **not** added to `SCENARIOS`; `stage_pages(wf_id, how)` for `present` / `absent` / `overwritten`. In `tests/replay/test_research_retain_replay.py` add `test_capture_research_retain_history`: `temporal`-marked, skipped unless `SDLC_CAPTURE_RESEARCH_RETAIN == "1"`; captures `SCENARIO` twice with `capture(SCENARIO, FEATURE_STARTER, monkeypatch, <dir>, sandboxed=True)` into `tmp_path / "a"` and `tmp_path / "b"`, asserts the two `commands` projections are equal (SG-3), and writes **only** `tests/replay/histories/research_retain_grounded.json` in the JSON shape `harness.write_fixtures` uses for a history (`workflow_id`, `workflow`, `source_commit`, `history`); it does not call `write_fixtures`. Then, with `git diff --quiet d51eef5 -- src` returning 0, run the capture **once**: `SDLC_CAPTURE_RESEARCH_RETAIN=1 pytest -m temporal tests/replay/test_research_retain_replay.py::test_capture_research_retain_history`. Record the fixture's `source_commit` and confirm `git diff d51eef5 <source_commit> -- src` is empty
- [ ] T003 [US1] RED: in `tests/replay/test_research_retain_replay.py` add plan-D3 tests 1 and 2 (fast tier, no `temporal` mark). (1) `test_retain_decisions_do_not_depend_on_page_files`, parametrized over `present`, `absent`, `overwritten`: load the history with `load_history(NAME)`, `monkeypatch.setenv("SDLC_RUNS_ROOT", str(tmp_path))`, `stage_pages(history.workflow_id, how)`, for `absent` assert `verify.pages_dir(history.workflow_id)` does not exist, replay with `tests.replay.test_feature_replay.replayer()` and `raise_on_replay_failure=True`, assert `replay_failure is None`. (2) PIN `test_fixture_holds_the_grounded_retain_path`: from the committed file, `command_projection` contains `activity:verify_brief_activity` once, `activity:research_subquestion` once and `activity:retain` three times; decoding the input payload of each scheduled `retain` gives `item.kind` values `gate_feedback`, `research_finding`, `research_finding` in that order (SG-3); `source_commit` has 40 characters; `workflow == "FeatureWorkflow"`. Run `pytest tests/replay/test_research_retain_replay.py` on the unmodified source and save the output to `.workspace/tmp/009-red.txt`: `present` passes, `absent` and `overwritten` fail with a nondeterminism error (`retain` in history, `recall_snapshot` issued), the PIN passes, the capture test is deselected by the fast tier's `addopts` (SG-4, SG-6)

**Checkpoint**: the defect is reproduced from a committed-to-be fixture; nothing under `src/` has changed.

---

## Phase 3: User Story 2 — only verified findings reach memory (P1), RED

**Goal**: the unit contract of the retain function under its new signature (FR-004, FR-005, FR-006; plan D1, D4).

**Independent test**: `pytest tests/research/test_research_grounding.py`.

- [ ] T004 [US2] RED: edit `tests/research/test_research_grounding.py` per plan D4 (the edit to cases 1 and 2 is approved at GATE 1; every existing assertion stays; the two `verify_brief_activity` tests are untouched). (1) `test_only_verified_findings_are_retained`: call `verified_findings_to_retain(brief, verify.verify_brief(brief, "r1"))`. (2) `test_recalled_lead_in_grounded_fails_verification`: pass the `vios` it already computes. (3) new: write both pages so both findings verify, then pass a hand-built `[Violation(kind="quote_not_found", source="https://x/2", quote=<that finding's quote>)]` → exactly the `https://x/1` item is returned. (4) new: an empty result for a two-finding brief → two items, in the brief's order, each with `kind is MemoryKind.RESEARCH_FINDING`, `bank == "project:default"` (and the passed bank when `bank=` is given), `text == f"{claim} — {source_url}"`, `metadata == {"stage": "research", "source_url": source_url}`. (5) new: compute the items for case 1's brief and result; then inside `monkeypatch.context()` patch `verify.pages_dir` and `Path.is_file`, `Path.exists`, `Path.read_text`, `Path.open` to raise `AssertionError`, call again with the same arguments, and assert the same items (SC-004). (6) new: `inspect.signature(verified_findings_to_retain)` has parameters exactly `brief`, `violations`, `bank`, and `violations` has no default (this assertion carries the RED); calling with the brief alone raises `TypeError`. Confirm 1-6 fail on unmodified source for the stated reason (the old function treats the second argument as a run id, or reads files, or has a `run_id` parameter) and the two activity tests pass
- [ ] T005 [P] [US2] RED: create `tests/research/test_research_workflow_purity.py` (fast tier) per plan D4, modelled on `tests/graph_workflow/test_determinism_lint.py`. Parse `src/sdlc/stages/research/step.py` and `src/sdlc/stages/research/retain.py` with `ast`. Fail on any whole identifier (`ast.Name.id`, `ast.Attribute.attr`, or an imported name/alias) equal to `verify_brief`, `pages_dir`, `page_filename`, `write_page`, `open`, `Path` or `os`; never match by substring (`verify_brief_activity` is allowed). Fail on any `from .verify import ...` in `retain.py`. In `step.py` the only names imported from `.verify` are `brief_digest` and `verify_brief_activity`. Add a self-test that runs the same check on a temporary file containing `from .verify import verify_brief` and expects a finding, and on one containing only `verify_brief_activity` and expects none. Do not edit `tests/graph_workflow/test_determinism_lint.py`. Confirm the `retain.py` checks fail on unmodified source (it imports `verify_brief`) and the `step.py` checks and the self-test pass

**Checkpoint**: the contract tests are red for the right reasons.

---

## Phase 4: User Stories 1 and 3 — the step retains what was verified; the failure path does not move, RED + PIN

**Goal**: stage-level proof that the step passes the activity's own result for the brief it verified, reads nothing, and leaves the violation paths alone (FR-001, FR-002, FR-003, FR-008; plan D2, D4).

**Independent test**: `pytest tests/research/test_research_retain_pairing.py`.

- [ ] T006 [US1] [US3] RED + PIN: create `tests/research/test_research_retain_pairing.py` (fast tier) per plan D4, driving `sdlc.stages.research.step` with a stub context (records `stage`, `record`, `retain`, a scripted `gate`, a `judge`) and a mocked `temporalio.workflow.execute_activity` dispatched by activity name, in the style of `tests/research/test_research_slice_contract.py` (which stays untouched). The real `verified_findings_to_retain` is used unless stated. (1) RED: `verify.pages_dir` patched to raise; plan one sub-question, a synthesized brief with two grounded findings, verify returns `[]`, gate approves → two retained items whose texts are the two findings'. Fails today (the step re-verifies and hits the patch). (2) RED: replace `step.verified_findings_to_retain` with a spy `lambda brief, violations, bank: ...` that records its arguments and returns `[]`; the verify mock returns one specific list object → the spy received the synthesized brief and **that same list object** (`is`). Fails today (it receives the run id). (3) RED: gate answers REVISE then the refine round's `synthesize_brief` raises → the retained items are exactly the first brief's findings (EC5). Fails today (no page files, so the re-read drops them). (4) RED: gate answers REVISE; the refine round's `synthesize_brief` returns a second brief with different findings and a distinct usage object; `step._fold_research_usage` is wrapped to raise only when called with that usage object (no call counter: the planner and finding folds come first) → the retained items are the first brief's findings, none of the second's (EC2, A1). Fails today. (5) PIN: first verification returns one violation → nothing retained, one record with outcome FAIL and an error starting `rejected:research.grounding:`, the outcome's digest is empty. (6) PIN: gate answers REVISE, the refine round's verification returns one violation → nothing retained, one FAIL record with error `rejected:research.grounding (refine)`. (7) PIN: a verified brief with no grounded findings → nothing retained, one PASS record (EC4). Confirm 1-4 fail for the stated reasons and 5-7 pass on unmodified source

**Checkpoint**: every RED of the feature is in place and seen failing; `.workspace/tmp/009-red.txt` holds the replay evidence.

---

## Phase 5: The change (US1, US2, US3)

- [ ] T007 [US1] [US2] [US3] Implement plan D1 and D2. In `src/sdlc/stages/research/retain.py`: signature `verified_findings_to_retain(brief: ResearchBrief, violations: list[Violation], bank: str = "project:default")`, `violations` required, `run_id` removed; build the `(source, quote)` set from `violations` and skip matching findings; item content and order unchanged; import `Violation` from `...grounding`; remove the `.verify` import; rewrite the module docstring (FR-009, pre-approved): keep "verified grounded findings only", add that the caller passes the result `verify_brief_activity` returned for this same brief, that this function reads no file, and that an empty list is the caller's claim of a clean verification which this function cannot check. In `src/sdlc/stages/research/step.py`: add `Violation` to the existing passed-through import block; add the module-level coroutine `_verify(brief, run_id)` returning `(brief, await workflow.execute_activity(verify_brief_activity, args=[brief, run_id], **VERIFY_ACT))`; replace both verification call sites with `verified_brief, violations = await _verify(brief, run_id_val)`; change the retain call to `verified_findings_to_retain(verified_brief, violations, bank=cfg.memory.project_bank)` (result positional, `bank` by keyword). Change nothing else in the step: digest, judge, records and the returned outcome keep using `brief`. Do **not** run the capture test again (SG-7). T003-T006 go green. Then run, as separate commands: `pytest tests/replay/test_research_retain_replay.py`; `pytest tests/research`; `pytest tests/replay`; `pytest -m temporal tests/replay`; `pytest -m temporal tests/research/test_research_e2e.py`; `python scripts/check_file_size.py` (SG-2, SG-5). Commit T002-T007 together; the message states that the fixture was recorded from workflow code at `<source_commit>`, whose `src/` is identical to `d51eef5`

**Checkpoint**: all acceptance scenarios of US1, US2 and US3 hold; three of three replay rows pass.

---

## Phase 6: Living docs and verification

- [ ] T008 In `src/sdlc/stages/research/AGENTS.md` rewrite exactly one bullet (pre-approved at GATE 1; nothing else in the file): the last bullet under "Verifier rules", beginning "Retention re-runs the verifier" → retention does not verify: `retain.py` takes the violations list `verify_brief_activity` returned for that brief and reads no file; the step retains the brief that was verified (`step.py`), so a replay does not depend on the page files. Commit
- [ ] T009 Run quickstart.md §1 to §5 as separate commands and record in `.specify/specs/009-research-retain-path/verification.md`: each command's result; the three replay rows before (from `.workspace/tmp/009-red.txt`) and after; the fixture's `source_commit` and the empty `git diff d51eef5 <source_commit> -- src`; the decoded retain kinds of the fixture; the pass-count delta against baseline.md; the mypy count against baseline.md; the empty forbidden-path diff; `git status --short tests/replay/histories tests/replay/golden` showing only the one added file; the line counts of `R/step.py` and `R/retain.py`; and the per-task commit shas. Commit

---

## Dependencies

- T001 first; T009 last.
- T002 → T003 (the rows need the fixture). T002 must run before any edit under `src/`.
- T004, T005 and T006 need only T001. T005 is `[P]`: its file is independent of T004's and T006's.
- T007 needs T003, T004, T005 and T006 seen red (and their PINs green).
- T008 needs T007 (it describes what landed).

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001 | T007; T006 (1, 2) |
| FR-002, SC-004 | T007; T004 (5), T005, T006 (1) |
| FR-003 | T007 (`_verify`); T006 (2, 3, 4) |
| FR-004, SC-005 | T007; T004 (1, 2, 3) |
| FR-005 | T007; T004 (6); unmodified `test_research_stage_wiring.py`, `test_research_slice_contract.py` |
| FR-006 | T007; T004 (4) |
| FR-007, SC-001, SC-002 | T002, T003, T007 |
| FR-008, SC-003 | T007 regression runs; T006 (5, 6); T009 |
| FR-009 | T007 (docstring), T008 |
| FR-010, SC-007 | T002 (own module); T007 and T009 (`check_file_size.py`) |
| FR-011 | Standing rules (forbidden paths); T009 (forbidden-path diff) |
| SC-006 | T009; the only edited existing test is T004 (1, 2) |
| Edge cases | EC1 T003 (`overwritten`); EC2 T006 (4); EC3 unchanged (`ctx.retain` returns early), no new test; EC4 T006 (7); EC5 T006 (3); EC6 T004 (3); EC7 and N2 accepted as not replayable, no test |
| GATE 1 rulings | Q1 T004, T007; Q2 T002 (recorded before the change), no patch marker in T007; Q3 T006 (5, 6); Q4 `R/verify.py` forbidden |
| Amendments | A1 T006 (4), T007; A2 T007 (positional), slice-contract test forbidden; A3, A5 T002 (memory on), T003 (2, isolated root); A4 T004 (5), T005, T006 (1); A6 T002; A7 no task (read only) |

## Implementation strategy

There is no partial delivery: the fix is one change to two files that must move together, and every RED rides its commit. If the capture in T002 cannot produce the expected history (SG-3), the feature stops there with nothing under `src/` touched.

**Totals**: 9 tasks — setup 1, US1 RED 2, US2 RED 2, US1+US3 RED/PIN 1, the change 1, docs and verification 2. Four commits (baseline; the change with its tests and fixture; the doc bullet; verification).
