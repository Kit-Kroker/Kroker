# Quickstart: validating 009 in the dev container

All commands run in `kroker-dev` with the feature worktree (`D:\own\Kroker-007`) mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`, do not add another. Capture with `> <log> 2>&1; echo RC=$?`. Never run alongside a live pipeline run. Never set `SDLC_CAPTURE_HISTORIES`.

## Prerequisites

- Worktree on branch `009-research-retain-path`, based on main `d51eef5`. No credentials, no network and no model calls needed.
- Read `.workspace/tasks/` for host hazards before any tier run.

## 1. The retain function is pure and still drops unverified findings

```bash
pytest tests/research/test_research_grounding.py
```

Expect: a brief with one verified and one unfetched finding yields one item; a result naming a finding drops it even with its page on disk; an empty result keeps every finding with today's text and metadata; the same items come back with file access made to fail; calling without a result is a `TypeError`.

## 2. The step retains what was verified

```bash
pytest tests/research/test_research_retain_pairing.py
pytest tests/research/test_research_workflow_purity.py
```

Expect: the step retains with the verifier's file helpers made to fail; the retain function receives the brief and the list the verify activity returned for it; a refine round that fails keeps the first brief's findings; a brief with violations retains nothing and records FAIL; `step.py` and `retain.py` name no file helper.

## 3. A research run replays without its pages

```bash
pytest tests/replay/test_research_retain_replay.py
```

Expect: three replay rows green (`present`, `absent`, `overwritten`) and the fixture-shape test green (one `gate_feedback` and two `research_finding` retains). The capture test is deselected.

Baseline, for reference (recorded once at exec, before the source change): `present` passes; `absent` and `overwritten` fail with a nondeterminism error. E5 shows the same.

## 4. Nothing else moved

```bash
pytest tests/research
pytest tests/replay
pytest -m temporal tests/replay
pytest -m temporal tests/research/test_research_e2e.py
git status --short tests/replay/histories tests/replay/golden
git diff d51eef5 --stat -- src/sdlc/stages/research/verify.py src/sdlc/stages/research/stage.py src/sdlc/stages/research/models.py src/sdlc/workflows src/sdlc/memory src/sdlc/grounding.py tests/replay/scenarios.py tests/replay/harness.py tests/replay/golden tests/research/test_research_slice_contract.py docs/reports/external-ideas-2026-09.md pyproject.toml uv.lock
```

Expect: all green; under `histories/` the only change is the one added file `research_retain_grounded.json`; nothing under `golden/`; the last diff is empty.

## 5. Whole feature

```bash
pytest
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
```

Expect: fast tier green, pass count = baseline + this feature's new tests; lint, format, types and file-size gates clean (mypy: no new errors against the baseline).

## Reference: capturing the fixture (once, at exec, before any source edit)

```bash
git diff --quiet d51eef5 -- src; echo RC=$?
SDLC_CAPTURE_RESEARCH_RETAIN=1 pytest -m temporal tests/replay/test_research_retain_replay.py::test_capture_research_retain_history
```

Expect: the first command prints `RC=0`; the second writes `tests/replay/histories/research_retain_grounded.json`. This is not part of validation and is never repeated after the source change.

## Reference: the baseline, already measured

E5: `.workspace/tmp/research-retain-path-e5.md`.
