# Implementation Plan: S-batch — six small inbox items

**Branch**: none (spec directory `006-s-batch-inbox-fixes`) | **Date**: 2026-10-03 | **Spec**: [spec.md](spec.md)

**Status**: Reviewer-validated 2026-10-03 (plan: `.workspace/tmp/reviewer-006-plan-1.md`, fixes-needed, F1–F5 applied; tasks: `.workspace/tmp/reviewer-006-tasks-1.md`, fixes-needed, one blocking, F1–F4 applied; see research.md). Awaiting GATE 2

**Input**: approved spec (GATE 1: Q1 doctor half rides; Q2 taught rows + `project_key` omission list, no sidecar; Q3 drafts stay in the inbox files) plus post-GATE-1 amendments A1–A5. Design inputs: advisor `.workspace/tmp/advisor-006-1.md`, skeptic `.workspace/tmp/skeptic-006-1.md`; every adopted claim re-checked in code (see [research.md](research.md), "Consult disposition").

## Summary

Six unrelated small items, one ceremony, no shared code. B1 adds a WARNING when the checkpoint commit fails. B2 adds a WARNING when a notify route is dropped for an unset `$VAR`, and teaches the doctor's notify-routes check to list those targets before a run. B3 makes the fleet-snapshot fixture generator testable and complete (taught rows, `project_key` omission list, repo-root anchoring), regenerates the fixture once on purpose, and adds a freshness test. B4 adds a Gotchas section to the research slice's `AGENTS.md`. B5 and B6 append a draft register row to their own inbox task files. Items are independent: any one can land or be reverted without the others.

## Technical Context

**Language/Version**: Python 3.13 (dev container; the host venv is not a verification environment). TypeScript/vitest for the unchanged frontend API tests.

**Primary Dependencies**: none added or changed. stdlib `logging`; existing PyYAML, pydantic, pytest.

**Storage**: N/A.

**Testing**: pytest fast tier (`pyproject.toml` `addopts`); `python scripts/check_ui.py` for the frontend gate. One pytest invocation per command; do not add `-q`. Ruff, mypy (`src/` only), `scripts/check_file_size.py`.

**Target Platform**: Linux container (`kroker-dev`).

**Project Type**: single repo, Temporal worker + workflows + dashboard.

**Performance Goals**: none. The new freshness test imports the dashboard models (~1.5 s once); acceptable for the fast tier, same as the sibling graph-fixture test.

**Constraints**:
- `src/sdlc/stages/code/step.py` (991/1000) is not edited. No edit to `pyproject.toml` or `uv.lock`. No retry, budget or timeout value changes.
- Historical docs (`docs/superpowers/`, earlier `.specify/specs/*`) are not edited. `docs/reports/external-ideas-*.md` is not edited or created.
- B4 changes exactly one file (FR-011). The stale research docstrings stay (A5).
- Read `src/sdlc/stages/code/AGENTS.md` before B1 and `src/sdlc/stages/research/AGENTS.md` before B4. `notify/`, `doctor/` and `scripts/` have no local `AGENTS.md`; the root one applies.
- All runs in `kroker-dev`. Commits: `git commit -F <msgfile>`, one path per `git add`, no attribution trailers. RC capture `> log 2>&1; echo RC=$?`.
- TDD: RED tests are written by the qa seat and seen failing before the fix task starts. Reviewer gate is per task and blocking.
- Base: main `817f819`.

**Scale/Scope**: 4 source files edited (`activities.py`, `routes.py`, `checks.py`, `dump_dashboard_fixtures.py`), 1 fixture regenerated, 1 new test module, 4 existing test modules edited, 1 `AGENTS.md`, 2 git-ignored inbox files. 14 tasks.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/006-s-batch-inbox-fixes/
├── spec.md
├── plan.md          # this file
├── research.md      # R1-R6 decisions, B3 drift table, B4 candidate list, consult disposition
├── quickstart.md    # dev-container validation runbook
├── checklists/
└── tasks.md         # /speckit-tasks
```

No `data-model.md` and no `contracts/`: the batch adds no entity and no external interface. The one new public function (`unset_env_targets`) is specified in D2.

### Source Code (repository root)

```text
src/sdlc/stages/code/activities.py       # B1: else-branch warning on the checkpoint commit
src/sdlc/doctor/checks.py                # B1: check_git_identity FAIL wording (text only)
tests/doctor/test_doctor_checks_binaries.py   # B1: git-identity wording test re-pinned + docstring
tests/code/test_coding_task_checkpoint.py # B1 tests (extend)

src/sdlc/notify/routes.py                # B2: logger, drop warning, _env_ref, unset_env_targets
src/sdlc/doctor/checks.py                # B2: check_notify_routes lists unset targets
tests/test_notify_routes.py              # B2 tests (extend)
tests/doctor/test_doctor_checks_delegated.py  # B2 doctor tests (extend + one isolation patch)

scripts/dump_dashboard_fixtures.py       # B3: build()/main(), ROOT anchor, taught rows, omission list
interfaces/dashboard/frontend/src/api/__fixtures__/fleet-snapshot.json  # B3: regenerated once
tests/test_fleet_fixture_fresh.py        # B3: new

src/sdlc/stages/research/AGENTS.md       # B4: "Gotchas" section

.workspace/tasks/2026-09-07-flaky-provider-import-test.md      # B5 draft (git-ignored)
.workspace/tasks/2026-09-10-benchmark-lens-outcome-records.md  # B6 draft (git-ignored)
```

**Structure Decision**: no new package or directory. Tests extend the module that already covers each surface; only B3 gets a new test module, mirroring `tests/test_graph_fixtures_fresh.py`.

## Design

### D1 — B1 checkpoint-commit warning (FR-001, FR-002)

In `run_coding_task`, the existing `if commit.returncode == 0:` gains an `else:` that calls `_log.warning` (the module logger is `_log`, `activities.py:29`) with the worktree and `commit.stderr.strip() or commit.stdout.strip()`. Message states that the test-freeze anchor will not advance. No behaviour changes: no raise, `commit_sha` stays unset.

One sentence elsewhere becomes false with this change and is corrected in the same commit: the doctor's `check_git_identity` FAIL detail (`src/sdlc/doctor/checks.py`) says every checkpoint commit "will fail SILENTLY" and cites `activities.py:197-202`. It is reworded to say the failure is logged at WARNING by `run_coding_task` and not raised, without a line range. One existing test pins the old wording: `test_identity_unresolvable_reports_fail_naming_the_silent_consequence` in `tests/doctor/test_doctor_checks_binaries.py` asserts `"silently" in r.detail.lower()`. It is renamed (`…_naming_the_logged_consequence`) and re-pinned in the RED task to the new wording ("warning" present, "silently" absent, "anchor" kept), and that module's docstring is updated. The check's logic and FAIL status are untouched.

Tests, in `tests/code/test_coding_task_checkpoint.py`, reusing its `_StubHarness` / `git_repo` / worktree scaffold. The failure is produced by monkeypatching `sdlc.stages.code.activities._git` with a passthrough that returns a non-zero `CompletedProcess` for `commit` only (a real broken identity is machine-dependent). `caplog` on logger `sdlc.stages.code.activities`:
1. non-zero commit with stderr → exactly one WARNING containing the worktree path and the stderr text; `commit_sha` falsy; no exception.
2. stderr empty, stdout set → message carries stdout; both empty → still exactly one WARNING.
3. zero return (real `_git`) → no WARNING from that logger; `commit_sha` equals `rev-parse HEAD`.

Case 3 passes before the fix; it is the control and is labelled so. Visibility is the worker log only (A3).

### D2 — B2 notify drop warning and doctor half (FR-003, FR-004, FR-005)

`src/sdlc/notify/routes.py`:
- `log = logging.getLogger(__name__)`. `sdlc.notify.routes` is a child of the `sdlc.notify` logger `notifiers.py` uses, so one handler or `caplog` scope covers both.
- `_env_ref(raw: str) -> str | None`: the variable name when a route string's target starts with `$`, else None. One definition of "a `$VAR` target", used by both callers below.
- `_parse_route`: on the existing drop branch, `log.warning` naming `where` and the variable name. Never a value (there is none to leak: the variable is unset or empty). Still returns None.
- `unset_env_targets(path=None) -> list[tuple[str, str]]`: re-reads the asset via `_resolve_path`, walks `default` then `gates.*`, tiers `primary` then `fallback` (the loader's order), and returns `(where, variable)` for each `$VAR` target whose variable is unset or empty. Non-string tier values are skipped, not raised: the loader owns structural errors. It does not log.

No de-duplication (A4). `load_routes()` runs per notification and per doctor run; each warning is a real dropped route.

`src/sdlc/doctor/checks.py` `check_notify_routes`: after `load_routes()` succeeds, call `unset_env_targets()` inside the same `try`. Non-empty → `CheckResult.warn(name, …)` listing each `where ($VAR)`. Empty → the existing `ok`. The `Check("notify routes", check_notify_routes, False)` row and both `except` branches are unchanged, so severity class and the unloadable-asset result are unchanged. `unset_env_targets` is imported into `checks` by name so tests can patch it there.

Known and accepted: `sdlc doctor` on an asset with unset targets shows the WARN row and also the loader's log line on stderr. Not a defect; do not suppress.

Tests:
- `tests/test_notify_routes.py`: unset variable → one WARNING containing `gates.merge.primary` and the variable name, route still absent, load succeeds; empty-string variable → same; both tiers unset → two WARNINGs; variable set → no WARNING; `log`-only asset → no WARNING. `unset_env_targets`: M of N unset → exactly those M in loader order; none unset → `[]`; shipped `policy/notifications.yaml` → `[]`.
- `tests/doctor/test_doctor_checks_delegated.py`: tmp asset via `SDLC_NOTIFY_ROUTES` with M unset → WARN whose detail names each location and variable; all set → PASS. `test_notify_routes_ok_reports_pass` gains `monkeypatch.setattr(checks, "unset_env_targets", lambda: [])` — an isolation edit so the test stops depending on the ambient asset; its assertion is unchanged. The two other existing tests raise inside `load_routes` and never reach the helper. One new fail-soft case: `load_routes` succeeds and `unset_env_targets` raises → the check returns WARN and does not raise.

### D3 — B3 fleet-snapshot generator, regeneration, freshness test (FR-006..FR-009)

`scripts/dump_dashboard_fixtures.py`:
- `ROOT = Path(__file__).resolve().parents[1]`; `OUT` anchored on it (today it is CWD-relative, which would make the test pass only from the repo root).
- `build() -> dict`: constructs the snapshot from the real models and returns the parsed JSON object (`json.loads(snap.model_dump_json())`), then applies the omission list. Single object, not a `{relpath: obj}` map: there is one file and no stray check.
- `main()`: writes `build()` to `OUT / "fleet-snapshot.json"` with the existing formatting (`indent=2`, trailing newline, utf-8).
- Taught rows: `graph-run-live` (open, with `stage_marks` and `graph_sha`), `graph-run-closed` (closed), `closed_marks["graph-run-closed"]`, `project_key="kroker"` on `feature-add-sso` and `feature-dark-mode`, `total_open_runs=3`. The 18 stage names and the `graph_sha` value are module literals copied from the committed file, with a comment; no coupling to the graph-fixture script.
- `_PROJECT_KEY_OMITTED = ("feature-unpriced", "fix-payment-retry", "feature-flag-cleanup")` with a comment stating the R-2 intent (pins the mapper's absent → null path next to the explicit-null rows). The pop looks each id up across `runs` and `closed` and raises if an id is missing or the key is already absent, so a renamed run cannot turn the pin into a silent no-op.

Regeneration is deliberate and lands in the same commit as the taught rows. Expected diff of the committed fixture, complete list (research.md R3):

| # | Change | Where |
|---|---|---|
| 1 | `stage_marks: null`, `graph_sha: null` added | open runs `feature-add-sso`, `feature-unpriced` |
| 2 | `graph_sha: null` added | all four closed rows |
| 3 | `thaw_tests: false` added | the one decision on `feature-add-sso` |
| 4 | `parent_run_id: null` added | all four pending (inbox) rows |
| 5 | `open_errors: []` added | snapshot root |

Nothing is removed and no existing value changes, judged on parsed data. The raw git diff also shows root keys in model field order (`closed_marks` moves after `open_errors`); that block move is expected and is not a difference. Any other parsed difference is a stop-guard (SG-1). The frontend mapper reads none of the added keys and maps absent and null alike (`http.ts:71,80,101`), so `http.test.ts` and `client.test.ts` pass unedited (FR-009).

`tests/test_fleet_fixture_fresh.py` (new, fast tier, importlib-loads the script like the graph test):
1. `build()` equals the committed file parsed (`json.loads`, so CRLF-safe); failure message names the file and the regenerate command.
2. Exactly the three omission-list runs lack `project_key`; every other run row carries the key; the two set and two explicit-null states are as ruled.

No tamper/chaos tests: one file, an `==` on parsed data.

Order inside B3: (a) refactor to `build()`/`main()` + `ROOT` with output unchanged from today's script; (b) RED freshness tests against the current committed file; (c) taught rows + omission list + regenerate, turning them green.

### D4 — B4 research Gotchas (FR-010, FR-011)

One new `## Gotchas` section in `src/sdlc/stages/research/AGENTS.md`, three sub-heads: fail-and-continue (E-29), verifier rules, budget enforcement. Source: the candidate list in research.md R5 (advisor-derived, 23 candidates with file:line). The executor re-reads each cited line and keeps a candidate only if it is true on the branch and is not already a WHAT-level clause in `research.md` (the stage doc). Target 12–18 bullets; each is a trap plus its consequence, with a `file.py` pointer but no line numbers (they rot). One bullet warns about two stale docstrings (A5): `deps.py` describes the persisted budget counter as a future, unwired "Task 8 concern" and `toolset.py` calls it "(deferred)", while `budget_store.py` implements it. Candidates that could only be verified by reading are marked as such.

Several candidates describe behaviour that may be a defect (spend under-reported on exhaustion, partial work discarded, non-atomic budget write). This batch documents them; it fixes none. The executor's final report lists them for the orchestrator to triage into the inbox.

### D5 — B5/B6 register-row drafts (FR-012, FR-013)

Each inbox file gets an appended `## Draft register row` section: a suggested register section (B5 "C. Verification and quality", B6 "D. Learning and the quality cycle"), no file name, no row id, and the row text in the register's existing table style (the executor reads `docs/reports/external-ideas-2026-09.md` for the column layout; read-only). Citations are current-main file paths and function names.

- B5 content: test `test_provider_imports_fast_enough_for_the_promptfoo_worker` asserts < 8.0 s wall-clock around a spawned interpreter; load-sensitive on a multi-agent workstation; remedies: measure import cost directly, or mark load-sensitive / move to the slow tier.
- B6 content: `LensOutcome` landed with C8 but the benchmark corpus still gets a reviewer or adversary record only when that lens runs; candidate: emit lens-outcome-derived records for both lenses, presence included.

`.workspace/` is git-ignored (A2): these two tasks produce working-tree edits, not commits. The reviewer gate is the reviewer reading the two files. `git status --short docs/reports/` showing no `external-ideas` entry is the FR-013 evidence.

## Requirement coverage

| Requirement | Design | Evidence |
|---|---|---|
| FR-001, FR-002, SC-001 | D1 | three test cases in `test_coding_task_checkpoint.py` |
| FR-003, FR-004, SC-002 | D2 | `test_notify_routes.py` warning cases |
| FR-005 | D2 | `unset_env_targets` cases + doctor WARN/PASS cases |
| FR-006 | D3 | `build()` importable; test 1 calls it without writing |
| FR-007 | D3 | test 2; regenerated fixture diff matches the table |
| FR-008, SC-004 | D3 | test 1 |
| FR-009, SC-003 | D3 | `python scripts/check_ui.py`; second regeneration is a no-op |
| FR-010, FR-011, SC-005 | D4 | reviewer spot-check of every bullet; one-file diff |
| FR-012, FR-013, SC-006 | D5 | reviewer reads both files; register untouched |
| FR-014 | all | one commit per tracked-file task; B5/B6 per A2 |
| FR-015 | constraints | empty `git diff 817f819 --stat` over `step.py`, `pyproject.toml`, `uv.lock`, `docs/superpowers/`, `docs/reports/` |
| SC-007 | — | full fast tier green vs baseline; 14 tasks |

Edge cases: B1 empty-output and crew path → D1 cases 2 and the A3 note; B2 empty string, both tiers, literal/`log` targets → D2 tests; B3 key-absence and wider drift → D3 omission guard and the diff table.

## Complexity Tracking

Empty — no constitution gates, no deviations.
