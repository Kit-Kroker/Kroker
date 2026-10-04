# Verification: 009 research retain path

Recorded by T009 on 2026-10-04, in `kroker-dev` (bound to
`D:\own\Kroker-007`, venv `kroker-007-venv`), branch
`009-research-retain-path`, quickstart §1–§5 run as separate commands.
Logs: `/tmp/009-t009-*.log` inside the container (not committed).

## §1 The retain function is pure and still drops unverified findings

    pytest tests/research/test_research_grounding.py
    → RC=0, 8 passed in 21.28 s

## §2 The step retains what was verified

    pytest tests/research/test_research_retain_pairing.py
    → RC=0, 7 passed in 21.61 s
    pytest tests/research/test_research_workflow_purity.py
    → RC=0, 6 passed in 21.96 s

## §3 A research run replays without its pages

    pytest tests/replay/test_research_retain_replay.py
    → RC=0, 4 passed, 1 deselected, 1 warning in 44.21 s

The three replay rows and the fixture-shape PIN pass; the capture test is
deselected (and has not run again since the single pre-change capture —
SG-7 held throughout).

**Before (RED evidence, `.workspace/tmp/009-red.txt`, unmodified source):**
`present` passed; `absent` and `overwritten` failed with
`NondeterminismError: [TMPRL1100] Activity type of scheduled event
'retain' does not match activity type of activity command
'recall_snapshot'`; the PIN passed; the capture test was deselected.
**After:** all three rows pass.

## §4 Nothing else moved

    pytest tests/research              → RC=0, 181 passed, 6 deselected (35.33 s)
    pytest tests/replay                → RC=0, 168 passed, 52 deselected (84.73 s)
    pytest -m temporal tests/replay    → RC=0, 32 passed, 20 skipped, 168 deselected (160.55 s)
    pytest -m temporal tests/research/test_research_e2e.py
                                       → RC=0, 3 passed (52.10 s)
    git status --short tests/replay/histories tests/replay/golden
                                       → empty (everything committed; the
                                         committed diff vs d51eef5 shows
                                         exactly one added file:
                                         tests/replay/histories/
                                         research_retain_grounded.json;
                                         golden/ untouched)
    git diff d51eef5 --stat -- <all forbidden paths>
                                       → empty, RC=0 (verify.py, stage.py,
                                         models.py, src/sdlc/workflows,
                                         src/sdlc/memory, grounding.py,
                                         scenarios.py, harness.py, golden/,
                                         test_research_slice_contract.py,
                                         external-ideas doc, pyproject.toml,
                                         uv.lock)

## §5 Whole feature

    pytest                    → RC=1: 5557 passed, 11 skipped, 252
                                deselected; 2 failed — both the
                                pre-existing baseline failures in
                                tests/test_grade_oracle.py (see
                                baseline.md; reproduced on unmodified
                                main before any change; unrelated to this
                                feature)
    ruff check .              → RC=0, all checks passed
    ruff format --check .     → RC=0, 1608 files already formatted
    mypy                      → RC=0, no issues in 379 source files
    python scripts/check_file_size.py → RC=0

**Pass-count delta vs baseline.md:** 5557 − 5536 = **+21**, exactly this
feature's new tests (T003: 3 rows + 1 PIN = 4; T004: +4 new grounding
cases; T005: +6 purity tests; T006: +7 pairing tests). Deselected
251 → 252 (+1: the capture test). Skips unchanged (11). Failures
unchanged (the two baseline grade_oracle rows). **mypy:** 0 errors in 379
files, same as baseline.

## The fixture

- File: `tests/replay/histories/research_retain_grounded.json` (new
  content; the only change under `histories/` and `golden/` vs `d51eef5`).
- `source_commit`: `9e51acc9601a6b45a3a21dd1c852a17d80853fef` (40 chars);
  `git diff d51eef5 9e51acc -- src` is **empty** — the fixture was
  recorded once, from workflow code whose `src/` is identical to main
  `d51eef5`, before any edit under `src/`.
- `workflow`: `FeatureWorkflow`.
- Decoded `retain` inputs, in order: `gate_feedback`, `research_finding`,
  `research_finding` (exactly one gate feedback and two finding retains —
  SG-3; the two captures inside the capture test agreed on the commands
  projection).
- The capture test listens only to `SDLC_CAPTURE_RESEARCH_RETAIN`;
  `SDLC_CAPTURE_HISTORIES` was never set at any point in this feature.

## Line counts

- `src/sdlc/stages/research/step.py`: 387 → **393**
- `src/sdlc/stages/research/retain.py`: 32 → **39**

## Per-task commits

| Task | Commit |
|---|---|
| T001 spec set + baseline | `9e51acc` |
| T002–T007 fixture, scenario, RED tests, the change | `b1d0ecd` |
| T008 AGENTS.md bullet | `eb1392e` |
| T009 verification + task-list close-out | (this commit) |

## Deviations and rulings

- **T007 / SG-2 (orchestrator clearance 2026-10-04):** D2 implemented as
  an inline one-statement binding instead of the _verify helper
  (orchestrator clearance 2026-10-04, SG-2); the plan-letter names (FR-003
  map row, D2 text) refer to this binding. Both call sites read
  `verified_brief, violations = (brief, await
  workflow.execute_activity(verify_brief_activity, args=[brief,
  run_id_val], **VERIFY_ACT))`; the binding rule (one statement, `brief`
  evaluated before the await, the pair survives any later rebinding) is
  preserved, and every unmodified suite — including
  `test_research_stage_wiring.py`, whose function-scoped source grep
  fired the guard — stays unmodified and green. Full record:
  `.workspace/tmp/009-sg2-report.md`.

## Stop-guards

One fired: **SG-2** during T007's first battery (the wiring pin described
above). Halted, diagnosed, reported; cleared by the orchestrator as
option 1; the battery was re-run from the top after the amendment. No
other guard fired at any point; in particular SG-7 held (the capture test
never ran after any edit under `src/`, and `SDLC_CAPTURE_HISTORIES` was
never set), SG-5 held (three of three replay rows green after the
change), and SG-6 held (every RED seen failing for its stated reason
before T007; every PIN green throughout).
