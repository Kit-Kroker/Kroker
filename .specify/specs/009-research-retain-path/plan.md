# Implementation Plan: Research Retain Path

**Branch**: `009-research-retain-path` (cut in the `D:\own\Kroker-007` worktree at exec) | **Date**: 2026-10-04 | **Spec**: [spec.md](spec.md)

**Status**: Plan reviewer-validated 2026-10-04 (`.workspace/tmp/reviewer-009-plan-1.md`: fixes-needed, two blocking findings and four nits, all applied; `reviewer-009-plan-2.md`: approve). Tasks reviewer-validated 2026-10-04 (`.workspace/tmp/reviewer-009-tasks-1.md`: approve, two nits applied; it also confirmed one wording fix made to D4 after the plan approval). Waiting for GATE 2.

**Input**: approved spec (GATE 1, 2026-10-04: Q1 the verification result is a required argument; Q2 no patch marker, fixture recorded before the change; Q3 the failure path changes nothing; Q4 `verify_brief` stays; FR-009 pre-approved, bounded) plus consult amendments A1-A7. Design inputs: advisor `.workspace/tmp/advisor-009-1.md`, skeptic `.workspace/tmp/skeptic-009-1.md`, probe E5 run in the dev container. Every adopted claim was re-checked in code (see [research.md](research.md), "Consult disposition").

## Summary

The research stage decides what to write to memory by re-running the verifier in workflow code, which reads page files from the local disk. A replay on a host without those files, or with changed files, fails with a nondeterminism error (measured, E5). This feature makes the retain function pure: it takes the verification result the activity already returned and drops the findings that result names. The step binds each verification result to the brief it was returned for and retains from that pair. One replay history with grounded findings and memory on is recorded from the unchanged workflow code and replayed with the pages present, absent and overwritten. Two source files edited, no new source module, no new activity, no wire change.

## Technical Context

**Language/Version**: Python 3.13 (dev container; the host venv is not a verification environment).

**Primary Dependencies**: none added or changed. Uses installed `temporalio` (`Replayer`, the sandboxed runner) and `pydantic-ai-slim` 2.51 in test fakes only.

**Storage**: none changed. Page files under `$SDLC_RUNS_ROOT/<run_id>/research/pages/` keep their format and are read by the verify activity only. One new committed test fixture: `tests/replay/histories/research_retain_grounded.json`.

**Testing**: pytest. The new unit tests and the three replay rows run in the fast tier (the replayer needs no server, like `tests/replay/test_feature_replay.py`). The capture test is `temporal`-marked and runs only on demand. One pytest invocation per command; do not add `-q`. Ruff, mypy (`src/` only), `scripts/check_file_size.py`.

**Target Platform**: Linux container (`kroker-dev`, bound to `D:\own\Kroker-007`).

**Project Type**: single repo, Temporal worker + workflows.

**Performance Goals**: no measurable change. The step does less work (no file reads). New tests add a few seconds to the fast tier (three replays of one short history).

**Constraints**:
- Workflow-side change: the command sequence of every ordinary run MUST stay identical. No activity is added, removed, reordered or given different arguments. `verify_brief_activity` keeps its name, arguments, options and return (FR-011).
- No edit to `R/verify.py`, `R/stage.py`, `R/models.py`, `src/sdlc/workflows/`, `src/sdlc/memory/`, `src/sdlc/grounding.py`, `pyproject.toml`, `uv.lock`, or the register file.
- No edit to `tests/replay/scenarios.py`, `tests/replay/harness.py`, any existing file under `tests/replay/histories/` or `tests/replay/golden/`, `tests/replay/test_fixtures_present.py`, `tests/replay/test_notify_registration_chaos.py`, or `tests/research/test_research_slice_contract.py`.
- The capture of the new history runs exactly once, before any source edit, through its own environment switch. `SDLC_CAPTURE_HISTORIES=1` is never set: it re-records every existing fixture.
- `AGENTS.md` edits are pre-approved for exactly one bullet in `src/sdlc/stages/research/AGENTS.md` (the last "Verifier rules" bullet) and for the `R/retain.py` module docstring. Nothing else in any `AGENTS.md`.
- The user's uncommitted files are not touched: `agents/dev/agent.yaml`, `agents/devops/agent.yaml`, `src/sdlc/core/models.py`, `docs/reports/2026-09-22-neon-welcome-session-retro.md`, the two `Pipeline Canvas` HTML files. (`CLAUDE.md` and `.specify/feature.json` are spec-kit pointer updates, not user work; no implementation task edits them.)
- File ceilings: 1000 lines. `R/step.py` 387, `R/retain.py` 32, `tests/replay/scenarios.py` 906 (not edited), `tests/research/test_research_grounding.py` 84 today.
- Read `src/sdlc/stages/research/AGENTS.md`, `src/sdlc/workflows/AGENTS.md` and the root `AGENTS.md` before editing.
- All runs in `kroker-dev`; never the host venv; never alongside a live pipeline run. Commits: `git commit -F <msgfile>`, one path per `git add`, subject and body, no attribution trailers. RC capture `> log 2>&1; echo RC=$?`. Host shell is PowerShell 5.1 (no heredocs).
- TDD: RED tests are written by the qa seat and seen failing on the unmodified source before the fix task starts. No commit on the branch is red. Reviewer gate is per task and blocking.
- Read `.workspace/tasks/` for known host hazards before any tier run.
- Base: main `d51eef5`.

**Scale/Scope**: 2 source files edited (`retain.py`, `step.py`), 1 existing test module edited, 4 new test modules, 1 new history fixture, 1 doc bullet.

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo rules from `AGENTS.md` are carried as constraints above. Post-design re-check: no violation; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
.specify/specs/009-research-retain-path/
├── spec.md
├── plan.md          # this file
├── research.md      # R1-R6 decisions, consult disposition, residuals
├── quickstart.md    # dev-container validation runbook
├── checklists/
└── tasks.md         # /speckit-tasks
```

No `data-model.md` and no `contracts/`: the feature adds no entity, no wire field and no external interface. The one changed interface is an in-process function signature, specified in D1.

### Source Code (repository root)

```text
src/sdlc/stages/research/retain.py   # pure: takes the verification result; docstring
src/sdlc/stages/research/step.py     # _verify helper; retain from the verified pair

tests/research/test_research_grounding.py         # edited: two calls pass the result; new cases
tests/research/test_research_retain_pairing.py    # NEW: the step retains what was verified
tests/research/test_research_workflow_purity.py   # NEW: static pin on step.py and retain.py
tests/replay/research_retain.py                   # NEW: the scenario, its fakes, page staging
tests/replay/test_research_retain_replay.py       # NEW: three replay rows, fixture shape, capture
tests/replay/histories/research_retain_grounded.json  # NEW fixture (new content)

src/sdlc/stages/research/AGENTS.md   # one Gotchas bullet (pre-approved)
```

**Structure Decision**: no new source module. The scenario lives in its own test module, outside `tests/replay/scenarios.py` and outside `SCENARIOS` (FR-010, A6): `scenarios.py` is at 906 lines, and list membership would force a golden file and edits to two existing pin tests.

## Design

### D1 — The retain function takes the verification result (FR-001, FR-004, FR-005, FR-006; Q1 = A)

In `R/retain.py`:

- Signature: `verified_findings_to_retain(brief, violations, bank="project:default")`. `violations` is the `list[Violation]` returned by `verify_brief_activity` for `brief`. It is required: no default. `run_id` is removed.
- Body: build the set of `(source, quote)` named by `violations`; skip a grounded finding whose `(source_url, quote)` is in it; otherwise build the same `RetainItem` as today, in the same order.
- Imports: `Violation` from `...grounding`; the import of `verify_brief` from `.verify` is removed. The module imports nothing from `.verify`.
- Module docstring (FR-009): keep the invariant ("verified grounded findings only"), and add who supplies the verification and what an empty result means: the caller passes the result the verify activity returned for this same brief; an empty list is the caller's claim that the brief was verified clean, and this function cannot check that claim.

Rules that are part of the contract:

- **No default for `violations`.** A caller without a result cannot call the function by leaving it out (US2 scenario 4).
- **Item content and order unchanged** (FR-006): `kind`, `bank`, `text = f"{claim} — {source_url}"`, `metadata = {"stage": "research", "source_url": ...}`.
- **Identification by `(source, quote)`**, as today (EC6).

### D2 — The step retains the brief that was verified (FR-001, FR-002, FR-003; A1, A2)

In `R/step.py`:

- A module-level coroutine `_verify(brief, run_id)` that returns `(brief, violations)`, where `violations` is the result of the existing `workflow.execute_activity(verify_brief_activity, args=[brief, run_id], **VERIFY_ACT)` call. It schedules exactly the command the two call sites schedule today and nothing else.
- Both verification call sites (first brief, refine round) become `verified_brief, violations = await _verify(brief, run_id_val)`. Everything that reads `violations` afterwards is unchanged.
- The retain call becomes `verified_findings_to_retain(verified_brief, violations, bank=cfg.memory.project_bank)`: the result is the second positional argument, `bank` stays a keyword (A2).
- `Violation` is imported in the existing passed-through import block, for the helper's annotation.
- Nothing else in the step changes: the digest, the judge call, the records and the returned outcome all keep using `brief` as today.

Rules:

- **The pair is bound at the call.** `verified_brief` and `violations` are assigned by one statement from one call, so no later rebinding of `brief` can separate them (EC2, A1).
- **Replay-neutral.** `_verify` is a plain coroutine awaited in place: the same activity, arguments, options and await order. An ordinary old history replays unchanged (Q2 = A).
- **The guard stays.** The retain step still runs only when `brief_digest_val` is non-empty (FR-003).

### D3 — The replay fixture and its test (FR-007, FR-008, FR-010; Q2 = A; A3, A5, A6)

**`tests/replay/research_retain.py`** (new, not a test module):

- Constants: the scenario name `research_retain_grounded`; two `(url, quote, claim)` findings; `page_text(quote)`, the one function that builds a page body, used both by the fake at record time and by the test when staging "present".
- Three fake activities registered under the production names `plan_research` (one sub-question), `research_subquestion` (writes the two pages with the real `write_page` under the run id it receives in its deps, returns a finding carrying the brief) and `synthesize_brief` (returns the brief with zero usage). Lifted from E5's script.
- `cfg()`: research on, research/architecture/plan gates off as in the existing research replay config, and **memory on explicitly with the fake backend** (A5).
- `activities()`: the registrations the run needs up to `awaiting:clarify`: the real `verify_brief_activity`, `retain`, `recall_snapshot` and `capture_watermark`, the three fakes, and the supporting registrations of the `research_greenfield` scenario filtered by activity name: any registration named `plan_research`, `research_subquestion` or `synthesize_brief` is dropped, so no name is registered twice (E5's measured filter, `research-retain-path-e5.py:62-66`).
- `SCENARIO`: a `Scenario` object in `partial` mode with `golden=False`, driven to `awaiting:clarify`. It is **not** added to `SCENARIOS`.
- `stage_pages(wf_id, how)`: for `present` writes each page with `write_page` and `page_text`; for `overwritten` writes other text for the same URLs; for `absent` writes nothing.

**`tests/replay/test_research_retain_replay.py`** (new):

1. `test_retain_decisions_do_not_depend_on_page_files[present|absent|overwritten]` (fast tier). Loads the committed history, points `SDLC_RUNS_ROOT` at the test's own `tmp_path`, stages pages for the history's workflow id, replays with the suite's replayer (`tests.replay.test_feature_replay.replayer`, sandboxed, production plugin) and asserts no replay failure. The `absent` row also asserts the pages directory does not exist. **`absent` and `overwritten` fail on unmodified source** (E5); `present` passes on both.
2. `test_fixture_holds_the_grounded_retain_path` (fast tier, PIN). From the committed history: the command projection contains `activity:verify_brief_activity` once, `activity:research_subquestion` once and `activity:retain` three times; the decoded inputs of the three `retain` activities carry kinds `gate_feedback`, `research_finding`, `research_finding` in that order (A3, A5). The file's `source_commit` is 40 characters and its `workflow` is `FeatureWorkflow`.
3. `test_capture_research_retain_history` (`temporal`-marked, skipped unless `SDLC_CAPTURE_RESEARCH_RETAIN=1`). Captures the scenario twice with the sandboxed runner through `harness.capture`, asserts the two command projections agree, and writes the history file only, in the same JSON shape `write_fixtures` produces. It does not call `write_fixtures` (that also writes a golden, and the golden directory's file set is pinned).

Rules:

- **Recorded once, from unchanged source.** The capture runs on the branch while `git diff d51eef5 -- src` is empty. The fixture's `source_commit` is the branch tip at that moment, a commit whose `src/` equals `d51eef5`'s. After the source change the capture is never run again.
- **Its own switch.** The capture test does not listen to `SDLC_CAPTURE_HISTORIES`.
- **Isolated root.** Every row sets `SDLC_RUNS_ROOT`; none relies on the default `runs/` directory.

### D4 — Tests

**`tests/research/test_research_grounding.py`** (edited; assertions kept, GATE 1 approved):

1. `test_only_verified_findings_are_retained`: obtains the result from `verify.verify_brief(brief, "r1")` and passes it. Same four assertions.
2. `test_recalled_lead_in_grounded_fails_verification`: passes the `vios` it already computes. Same assertions.
3. New: a result naming a finding drops it even though its page is on disk (the result decides, not the disk).
4. New: an empty result retains every grounded finding, in order, with today's exact `kind`, `bank`, `text` and `metadata` (FR-006).
5. New: with `verify.pages_dir` (every verifier read goes through it) and `Path.is_file`, `Path.exists`, `Path.read_text`, `Path.open` patched to raise for the duration of the call, the items equal those computed without the patches (SC-004).
6. New: the signature's parameters are exactly `brief`, `violations`, `bank`, and `violations` has no default (this assertion is the one that fails on unmodified source); calling without a verification result raises `TypeError` (US2 scenario 4, FR-005).

Cases 1-6 **fail on unmodified source** (the old function treats the second argument as a run id, or reads files). The two activity tests in the module are untouched.

**`tests/research/test_research_retain_pairing.py`** (new, fast tier). The step driven with a stub context and a mocked `workflow.execute_activity`, in the style of `test_research_slice_contract.py`, with the real retain function unless stated.

1. The step calls no verifier of its own: with `verify.pages_dir` patched to raise (patching `verify.verify_brief` would not reach the name `retain.py` imported), a verified brief with two grounded findings yields two retained items. **Fails on unmodified source.**
2. The retain function receives the brief and the very list the verify activity returned for it (spy on the function). **Fails on unmodified source** (it receives a run id).
3. Refine round whose synthesis raises after a verified first brief: exactly the first brief's findings are retained (EC5). **Fails on unmodified source** (no page files exist in this test, so the old re-read drops them).
4. Refine round in which an error is raised after the new brief is assigned and before it is verified (`_fold_research_usage` wrapped so that it raises only when called with the usage object the refine round's `synthesize_brief` returned; every earlier fold, including the first synthesis's, runs as normal — a call counter is not used, because the planner and finding folds come first): the retained items come from the first, verified brief, not from the new one (EC2, A1). **Fails on unmodified source** (the old step re-verifies the new brief against pages that do not exist and retains nothing).
5. First brief with violations: nothing retained, FAIL row with `rejected:research.grounding:` (US3 scenario 1, PIN).
6. Refine round with violations: nothing retained, FAIL row with `rejected:research.grounding (refine)` (US3 scenario 2, PIN).
7. Verified brief with no grounded findings: nothing retained, PASS row (EC4, PIN).

**`tests/research/test_research_workflow_purity.py`** (new, fast tier, A4). Parses `R/step.py` and `R/retain.py` into an AST and fails on any identifier (a `Name`, an `Attribute` name or an imported name, compared whole, never by substring) equal to one of `verify_brief`, `pages_dir`, `page_filename`, `write_page`, `open`, `Path` or `os`, and on any import from `.verify` in `retain.py`. `step.py` importing `brief_digest` and `verify_brief_activity` from `.verify` is allowed by name. A self-test runs the same check on a temporary file that uses a banned name and expects it to be caught. `step.py` is not added to `tests/graph_workflow/test_determinism_lint.py`.

**Unmodified suites that are the regression check**: all of `tests/research/` (in particular `test_research_slice_contract.py`, `test_research_stage_wiring.py`, `test_research_verify.py`, `test_research_refine_round.py`, `test_research_e2e.py`), all of `tests/replay/` including every existing history and golden, and `tests/test_hindsight_retain.py`.

### D5 — Living docs (FR-009)

- `src/sdlc/stages/research/AGENTS.md`, exactly one bullet, the last under "Verifier rules" ("Retention re-runs the verifier ..."): rewrite to what is now true — retention does not verify; `retain.py` takes the violations list `verify_brief_activity` returned for that brief and reads no file; the step retains the brief that was verified.
- `R/retain.py` module docstring: in D1.
- Docs describe main: the bullet lands in the feature branch, last.

## Requirement coverage

| Requirement | Where |
|---|---|
| FR-001 retain from the activity's result, no second verification | D1, D2; pairing tests 1, 2 |
| FR-002 no read reachable from the retain path (as read by A4) | D1 imports; grounding test 5; pairing test 1; purity test |
| FR-003 result belongs to the brief retained; guard kept | D2 `_verify`; pairing tests 2, 3, 4 |
| FR-004 only verified findings, enforced where items are built | D1; grounding tests 1, 2, 3 |
| FR-005 name and place kept, no unused parameter | D1; grounding test 6; unmodified `test_research_stage_wiring.py`, `test_research_slice_contract.py` |
| FR-006 item content and order unchanged | D1; grounding test 4 |
| FR-007 replay test, fails on `d51eef5`, new fixture | D3; replay rows `absent`, `overwritten`; fixture shape test |
| FR-008 existing histories and the failure path unchanged | D2 rules; unmodified `tests/replay/`; pairing tests 5, 6 |
| FR-009 notes corrected | D1 docstring; D5 |
| FR-010 ceilings; where the scenario lives | Structure Decision; D3; `scripts/check_file_size.py` |
| FR-011 verify activity untouched | Constraints; no edit to `R/verify.py` |
| SC-001 | replay row `absent` red on unmodified source, green after |
| SC-002 | the three replay rows |
| SC-003 | unmodified `tests/replay/` |
| SC-004 | grounding test 5 |
| SC-005 | grounding tests 1, 2 |
| SC-006 | quickstart steps 4, 5; the only edited existing test is `test_research_grounding.py` (cases 1, 2), assertions kept |
| SC-007 | `scripts/check_file_size.py` |
| US1 scenarios 1-3 / 4 | replay rows / unmodified `tests/replay/` |
| US2 scenarios 1-4 | grounding tests 1, 2, 5, 6 |
| US3 scenarios 1, 2 / 3 | pairing tests 5, 6 / no new test: the rejection branch is not edited and the change schedules no different command before it |
| EC1 | replay row `overwritten` |
| EC2 | D2; pairing test 4 |
| EC3 memory off | unchanged (`ctx.retain` returns early); pairing test 1 covers "no file read"; no new test for the activity count |
| EC4 | pairing test 7 |
| EC5 | pairing test 3 |
| EC6 | unchanged identification by `(source, quote)`; grounding test 3 |
| EC7, N2 | accepted as not replayable (Q2 = A); named residuals; no test |

## Stop-guards (binding; clearance from the orchestrator only)

1. Any change seems to need an edit to a path the Constraints forbid, a new activity, or a change to `verify_brief_activity`: stop.
2. Any existing test fails after a change and the plan does not name it as an intended edit: stop. Do not edit the test to pass. Never re-record or edit an existing history or golden file.
3. The new history, captured from unmodified source, does not hold exactly one `gate_feedback` and two `research_finding` retains, or the two captures disagree: stop. Fix the scenario, not the projection.
4. On unmodified source the `absent` or `overwritten` replay row passes, or the `present` row fails: stop; the test does not test the defect. The output of that run is kept as the SC-001 evidence in `.workspace/tmp/009-red.txt`.
5. After the source change any of the three rows fails: stop. Do not re-capture.
6. A test this plan marks as failing on unmodified source passes there, or a PIN test is red: stop.
7. `SDLC_CAPTURE_HISTORIES` is about to be set for any command: stop.

## Residuals (accepted, reported at GATE 2)

From research "Residuals": an old history of the N2 or EC7 shape no longer replays (Q2 = A); for new runs N2 changes from "retain what still matches the disk" to "retain what was verified"; a caller can pass an empty result for a brief nobody verified (Q1 = A); on the path A1 closes for retention the stage still returns the new brief with the old digest; no GraphWorkflow parity is claimed for the new scenario; the new history is in `partial` mode and ends at `awaiting:clarify`; why the sandbox does not block the read is not established; the other fail-and-continue behaviours of the slice are untouched.

## Complexity Tracking

Empty: no constitution violations.
