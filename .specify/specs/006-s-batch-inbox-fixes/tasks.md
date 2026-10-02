# Tasks: S-batch — six small inbox items

**Input**: `.specify/specs/006-s-batch-inbox-fixes/` (spec.md, plan.md, research.md, quickstart.md)

**Tests**: required for B1, B2, B3 (spec FR-014). Every behaviour task is preceded by its RED test task.

## Standing rules for every task

- All test and lint runs happen in `kroker-dev` (see quickstart.md). Never the host venv. One pytest per command; do not add `-q` (already in `addopts`). Capture with `> <log> 2>&1; echo RC=$?`.
- Read `src/sdlc/stages/code/AGENTS.md` before T002–T003 and `src/sdlc/stages/research/AGENTS.md` before T011.
- RED tasks are written by the qa seat and must be seen failing for the stated reason before the paired fix task starts. A RED task's tests are committed in the commit of the task that turns them green, so no commit on the branch is red and each item reverts as one commit. The reviewer gate still applies to the RED diff on its own.
- Commit: subject + body only, **no attribution trailers of any kind**. `git commit -F <msgfile>`; one path per `git add`.
- Reviewer gate is per task and blocking: task N+1 does not start until the reviewer has replied approve on task N.
- No edit to `src/sdlc/stages/code/step.py`, `pyproject.toml`, `uv.lock`, `docs/superpowers/`, earlier `.specify/specs/*`, or any `docs/reports/external-ideas-*.md`. No retry, budget or timeout value is changed.
- Line numbers in plan.md and research.md are as of main `817f819`; re-locate by symbol, not by number.

## Stop-guards (stop, diagnose, report; clearance only from the orchestrator)

- **SG-1** The regenerated fleet fixture (T010) differs from the committed one, compared as parsed data, in anything other than the five additions in plan D3's table: a removed key, a changed value, or an addition not listed. Root keys moving into model field order in the raw diff (`closed_marks` after `open_errors`) is expected and is not a difference.
- **SG-2** `python scripts/check_ui.py` fails after T010, or passing it would need an edit to `http.test.ts` / `client.test.ts` (FR-009).
- **SG-3** A dependency change or an edit to `src/sdlc/stages/code/step.py` appears necessary (FR-015).
- **SG-4** An existing test outside the four test modules this batch edits (`tests/code/test_coding_task_checkpoint.py`, `tests/test_notify_routes.py`, `tests/doctor/test_doctor_checks_delegated.py`, `tests/doctor/test_doctor_checks_binaries.py`) goes red after T003, T005 or T007.
- **SG-5** A B4 gotcha candidate turns out to describe a live defect that the executor is tempted to fix. Document it, list it in the final report, do not fix it.

## Phase order

The six items are independent. Phases run in the order below only to keep one reviewer gate open at a time; any phase can be dropped or reverted without touching another.

| Phase | Item | Story | Plan | Commits |
|---|---|---|---|---|
| 1 Setup + baseline | — | — | — | 1 |
| 2 Checkpoint warning | B1 | US1 | D1 | 1 |
| 3 Notify drop warning + doctor | B2 | US2 | D2 | 2 |
| 4 Fleet fixture | B3 | US3 | D3 | 2 |
| 5 Research gotchas | B4 | US4 | D4 | 1 |
| 6 Register-row drafts | B5, B6 | US5 | D5 | 0 (git-ignored) |
| 7 Verification | — | — | — | 1 |

---

## Phase 1: Setup and baseline on unmodified main (no source edits)

- [ ] T001 Create branch `006-s-batch-inbox-fixes` from main `817f819` in a worktree, confirm `kroker-dev` syncs (`uv sync --frozen --extra dev`), run `pytest` and `mypy` once each, and record the base sha, the fast-tier pass count, any pre-existing failures and the mypy error count in `.specify/specs/006-s-batch-inbox-fixes/baseline.md`

**Checkpoint**: baseline.md holds base sha, pass count, mypy count.

---

## Phase 2: User Story 1 — a failed checkpoint commit is visible (B1, P1)

**Goal**: a non-zero checkpoint commit logs one WARNING with the worktree and git's text; nothing else changes (FR-001, FR-002).

**Independent test**: `pytest tests/code/test_coding_task_checkpoint.py`, then `pytest tests/doctor`.

- [ ] T002 [US1] RED: in `tests/code/test_coding_task_checkpoint.py`, reusing the module's `_StubHarness` / `git_repo` / worktree scaffold, add the three plan-D1 cases with `caplog` on logger `sdlc.stages.code.activities`: (1) `activities._git` monkeypatched with a passthrough returning a non-zero `CompletedProcess` with stderr for `commit` only → exactly one WARNING containing the worktree path and the stderr text, `commit_sha` falsy, no exception; (2) same with stderr empty and stdout set → message carries stdout, and with both empty → still exactly one WARNING; (3) control, real `_git` → no WARNING from that logger and `commit_sha` equals `git rev-parse HEAD`. Also in this task, in `tests/doctor/test_doctor_checks_binaries.py`: rename `test_identity_unresolvable_reports_fail_naming_the_silent_consequence` to `test_identity_unresolvable_reports_fail_naming_the_logged_consequence`, and replace its `assert "silently" in r.detail.lower()` with `assert "silently" not in r.detail.lower()` plus `assert "warning" in r.detail.lower()`; keep the FAIL status, `auto-detect email address` and `anchor` assertions; reword the module docstring's "swallows that" sentence (line 4) to match. Confirm (1) and (2) fail because no warning is logged, (3) passes, and the renamed doctor test fails on the two new assertions
- [ ] T003 [US1] In `src/sdlc/stages/code/activities.py` `run_coding_task`, add the `else:` branch on the checkpoint commit's return code: `_log.warning` naming `inp.worktree`, stating the test-freeze anchor will not advance, with `commit.stderr.strip() or commit.stdout.strip()`. No raise, no other behaviour change. In the same commit, correct the now-false sentence in `src/sdlc/doctor/checks.py` `check_git_identity`'s FAIL detail ("will fail SILENTLY -- the failure is swallowed at stages/code/activities.py:197-202") to say the failure is logged at WARNING by `run_coding_task` and not raised, with no line range; keep the words "warning" and "anchor" in the detail and drop "silently"; text only, the check's logic and FAIL status are untouched. T002 (both test modules) goes green; run `pytest tests/code/test_coding_task_checkpoint.py`, then `pytest tests/doctor`; commit T002 + T003 together

**Checkpoint**: US1 acceptance scenarios 1–2 pass.

---

## Phase 3: User Story 2 — an unset `$VAR` notify target is visible (B2, P1)

**Goal**: the drop is logged at load time and listed by `sdlc doctor` (FR-003, FR-004, FR-005).

**Independent test**: `pytest tests/test_notify_routes.py`, then `pytest tests/doctor`.

- [ ] T004 [US2] RED: in `tests/test_notify_routes.py` add warning cases with `caplog` on logger `sdlc.notify`: variable unset → one WARNING containing the route location (`gates.merge.primary`) and the variable name, the route still absent from the table, `load_routes` succeeds; variable set to `""` → same; both tiers of one gate unset → two WARNINGs; variable set → no WARNING and the route resolves; a `log`-only asset → no WARNING. Assert no WARNING text contains a target value. Confirm the warning cases fail because nothing is logged
- [ ] T005 [US2] In `src/sdlc/notify/routes.py`: add `log = logging.getLogger(__name__)`; factor `_env_ref(raw) -> str | None` (variable name when the route string's target starts with `$`); in `_parse_route`'s drop branch call `log.warning` with `where` and the variable name, then return None as today; update the `_parse_route` docstring to say the drop is logged. T004 goes green; commit T004 + T005 together
- [ ] T006 [US2] RED: (a) in `tests/test_notify_routes.py` add `unset_env_targets` cases — an asset with N `$VAR` targets, M unset → exactly those M as `(where, variable)` in loader order (`default` then `gates.*`, `primary` then `fallback`); none unset → `[]`; the shipped `policy/notifications.yaml` → `[]`; a non-string tier value is skipped, not raised. (b) in `tests/doctor/test_doctor_checks_delegated.py` add: a tmp asset via `SDLC_NOTIFY_ROUTES` with M unset → `check_notify_routes()` is WARN and its detail names each location and variable; all set → PASS; `load_routes` stub succeeds and `unset_env_targets` stub raises → WARN, no exception. Add `monkeypatch.setattr(checks, "unset_env_targets", lambda: [])` to the existing `test_notify_routes_ok_reports_pass` (isolation only; its assertion is unchanged). Confirm the new cases fail on the missing name
- [ ] T007 [US2] Add public `unset_env_targets(path=None) -> list[tuple[str, str]]` to `src/sdlc/notify/routes.py` (re-reads via `_resolve_path`, uses `_env_ref`, does not log) and export it; in `src/sdlc/doctor/checks.py` import it by name beside `load_routes` and, in `check_notify_routes`, call it after `load_routes()` inside the existing `try`: non-empty → `CheckResult.warn` listing each `where ($VAR)`, empty → the existing `ok`. Leave both `except` branches and the registry row unchanged. T006 goes green; run `pytest tests/doctor`; commit T006 + T007 together

**Checkpoint**: US2 acceptance scenarios 1–3 pass; a clean checkout's doctor result for notify routes is unchanged.

---

## Phase 4: User Story 3 — the fleet snapshot fixture is regenerable and guarded (B3, P2)

**Goal**: generator complete and testable, fixture regenerated once, freshness test in the fast tier (FR-006..FR-009, spec A1).

**Independent test**: `pytest tests/test_fleet_fixture_fresh.py`, then `python scripts/check_ui.py`.

- [ ] T008 [US3] Refactor `scripts/dump_dashboard_fixtures.py` with no change to what it emits: add `ROOT = Path(__file__).resolve().parents[1]` and anchor `OUT` on it; move construction into `build() -> dict` returning `json.loads(snap.model_dump_json())`; `main()` writes `build()` with the existing `indent=2` + trailing newline + utf-8 and prints the path. Do NOT run it against the repo yet. Verify by calling `build()` from a different working directory and confirming it returns 2 open runs, 3 closed, 1 inbox run. Commit
- [ ] T009 [US3] RED: create `tests/test_fleet_fixture_fresh.py` (fast tier; importlib-load the script the way `tests/test_graph_fixtures_fresh.py` does): (1) `build()` equals `json.loads` of the committed `interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json`, failure message naming the file and `python scripts/dump_dashboard_fixtures.py`; (2) in `build()`'s `runs` + `closed`, exactly `feature-unpriced`, `fix-payment-retry`, `feature-flag-cleanup` lack `project_key`, `feature-add-sso` and `feature-dark-mode` carry `"kroker"`, `graph-run-live` and `graph-run-closed` carry explicit null. Confirm both fail against the T008 generator
- [ ] T010 [US3] In `scripts/dump_dashboard_fixtures.py` `build()`: add the taught rows from plan D3 (`graph-run-live`, `graph-run-closed`, `closed_marks`, the two `project_key="kroker"` values, `total_open_runs=3`) with the 18 stage names and the `graph_sha` as commented module literals copied from the committed fixture; add commented `_PROJECT_KEY_OMITTED` and the guarded pop (raise if an id is missing or the key already absent). Run the generator; compare the old and new `fleet-snapshot.json` as parsed data against plan D3's five-row table (SG-1 on any other difference; the `closed_marks` block moving in the raw diff is expected); run it a second time and confirm no further change; run `python scripts/check_ui.py` (SG-2). T009 goes green; commit T009 + T010 + the regenerated fixture together, with the five additions listed in the commit body

**Checkpoint**: US3 acceptance scenarios 1–4 pass.

---

## Phase 5: User Story 4 — research-stage gotchas have a living home (B4, P3)

**Goal**: a verified Gotchas section in the slice's editing guide (FR-010, FR-011, spec A5).

**Independent test**: reviewer spot-checks every bullet against the code.

- [ ] T011 [US4] Add `## Gotchas` to `src/sdlc/stages/research/AGENTS.md` with three sub-heads (fail-and-continue E-29; verifier rules; budget enforcement). Take the candidates from research.md R5; re-read each cited location on the branch and keep a candidate only if it is true now and is not already a WHAT-level clause in `src/sdlc/stages/research/research.md`. 12–18 bullets, each a trap plus its consequence, naming the file but not line numbers; include the warning about the two stale docstrings (`deps.py` "Task 8 concern", `toolset.py` "(deferred)") per research.md R5; mark any bullet verified by reading only. No other file changes. List in the task report every kept candidate with the line that proves it, every dropped candidate with the reason, and any candidate that looks like a live defect (SG-5). Commit

**Checkpoint**: `git diff 817f819 --stat -- src/sdlc/stages/research/` shows one file.

---

## Phase 6: User Story 5 — two register rows are ready to paste (B5 + B6, P3)

**Goal**: a finished draft row at the end of each inbox file; the register untouched (FR-012, FR-013, spec A2).

**Independent test**: reviewer reads both files; `git status --short docs/reports/` shows no `external-ideas` entry.

These two files are git-ignored: the deliverable is the working-tree edit in the primary checkout's `.workspace/tasks/`, there is no commit, and the reviewer gate is the reviewer reading the file.

- [ ] T012 [P] [US5] Append `## Draft register row` to `.workspace/tasks/2026-09-07-flaky-provider-import-test.md`: suggested section "C. Verification and quality", no register file name, no row id; the row in the column layout of `docs/reports/external-ideas-2026-09.md` (read-only); content per plan D5/B5, with the test re-read at `tests/test_promptfoo_provider.py` and cited by test name
- [ ] T013 [P] [US5] Append `## Draft register row` to `.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md`: suggested section "D. Learning and the quality cycle", no register file name, no row id; same column layout; content per plan D5/B6, with `src/sdlc/stages/review/step.py`, `src/sdlc/stages/review/lenses.py` and `src/sdlc/benchmarks/agreement_matrix.py` re-read and cited by function name; cover both lenses

**Checkpoint**: both files end with the draft section; the register has no change.

---

## Phase 7: Verification

- [ ] T014 Run quickstart.md §5 as separate commands (`pytest`; `ruff check .`; `ruff format --check .`; `mypy`; `python scripts/check_file_size.py`; `python scripts/check_ui.py`; the FR-015 `git diff 817f819 --stat` over the forbidden paths) and record each result, the pass-count delta against baseline.md, the SG-5 defect-candidate list from T011, and the per-item commit shas in `.specify/specs/006-s-batch-inbox-fixes/verification.md`. Commit

---

## Dependencies

- T001 first; T014 last.
- Within an item: T002→T003; T004→T005→T006→T007; T008→T009→T010. T007 needs T005's `_env_ref`.
- Across items: none. T011, T012, T013 depend on nothing but T001.
- `[P]`: T012 and T013 touch different files and need no gate between them.

## Requirement → task map

| Requirement | Tasks |
|---|---|
| FR-001, FR-002, SC-001 | T002, T003 |
| FR-003, FR-004, SC-002 | T004, T005 |
| FR-005 | T006, T007 |
| FR-006 | T008 |
| FR-007 | T009, T010 |
| FR-008, SC-004 | T009, T010 |
| FR-009, SC-003 | T010, T014 |
| FR-010, FR-011, SC-005 | T011 |
| FR-012, FR-013, SC-006 | T012, T013, T014 |
| FR-014 | all (commit pairing in Standing rules) |
| FR-015 | T014 |
| SC-007 | T001, T014 |

## Implementation strategy

There is no MVP ordering: each phase is a complete, shippable item. If time runs out, whatever phases are done can be fast-forwarded; the rest stay in the inbox. Phases 2–4 carry behaviour and go first; 5–6 are documents.

**Totals**: 14 tasks — setup 1, US1 2, US2 4, US3 3, US4 1, US5 2, verification 1. Eight commits (baseline, B1, B2 ×2, B3 ×2, B4, verification).
