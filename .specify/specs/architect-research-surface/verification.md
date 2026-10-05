# Verification: architect-research-surface

Recorded 2026-10-05, T013, quickstart.md sections 1-7 run as separate
commands in `kroker-dev` (worktree `D:\own\Kroker-007` at `/app`). Logs
under `.workspace/tmp/` in the primary checkout (`c12-q-*.txt` unless
named). Base: `e5c8ef8`; branch `architect-research-surface`.

## Commits (per task)

| Task(s) | Commit | Subject |
|---|---|---|
| T001 | `ac6bd09` | chore(spec): set the architect-research-surface spec set and record the branch baseline |
| T005+T006+T007 | `7f7502c` | feat(observability): add the sub-run usage report, its reader and add_spend |
| T002+T008 | `590ade1` | feat(research): the architect tool reports its inner spend, is limited, and degrades cleanly |
| T003+T009 | `7632c68` | feat(architecture): the architect's research deps carry the configured run ceiling and request limit |
| T004+T010 | `0711ba2` | feat(workflows): harvest sub-run usage reports at the single model-egress point |
| T011 | `ee884ee` | feat(replay): capture the architect-research-usage history once and pin the harvest sequence |
| T012 | `0ba3f25` | docs: living docs for the architect research surface |
| T013 | (this commit) | verification + task-list closure |

Eight commits, as planned. Every task passed the blocking reviewer gate
(verdicts: APPROVE on T001-T012; T005 needed one fixes-needed round — a
ruff I001 import-block sort — addressed and re-approved).

## Section 0 — the channel holds (T001 evidence)

Probes re-run on the branch base, recorded in `baseline.md` (commit
`ac6bd09`): E1 metadata workflow-side / model-visible content identical
modulo the metadata field; E2 durable round-trip True; E3 limit text
carries advice + URL, caller-owned usage non-zero after the limit,
`part_kind` `tool-return`. SG-1 did not fire.

## Sections 1-7 (each command separate)

| # | Command | Result | Log |
|---|---|---|---|
| 1a | `pytest tests/test_sub_run_usage.py` | 18 passed | c12-q-1a |
| 1b | `pytest tests/test_role_usage.py` | 10 passed | c12-q-1b |
| 2a | `pytest tests/architecture/test_architect_research_report.py` | 12 passed | c12-q-2a |
| 2b | `pytest tests/architecture/test_architect_research_tool.py` | 4 passed | c12-q-2b |
| 3 | `pytest tests/architecture/test_architect_research_deps.py` | 3 passed | c12-q-3 |
| 4a | `pytest tests/test_run_role_sub_run_harvest.py` | 8 passed | c12-q-4a |
| 4b | `pytest tests/test_run_role_guard.py` | 5 passed | c12-q-4b |
| 5a | `pytest tests/durability/test_sub_run_usage_wire.py` (layer 2) | 2 passed | c12-q-5a |
| 5b | `pytest -m temporal tests/durability/test_sub_run_usage_wire.py` (layer 1) | 1 passed | c12-q-5b |
| 5c | `pytest -m temporal tests/durability/test_provider_payload_parity.py` | 1 passed | c12-q-5c |
| 6a | `pytest tests/replay/test_architect_research_usage_replay.py` | 3 passed, 1 deselected (the capture switch, permanently off) | c12-q-6a |
| 6b | `pytest tests/replay` | 171 passed | c12-q-6b |
| 6c | `git status --short` over histories/golden/fixtures ×2 | empty (clean; the one added file is committed) | c12-q-6c |
| 7a | `pytest` | **5607 passed**, 11 skipped = baseline 5559 + 48 new | c12-q-7a |
| 7b | `pytest -m temporal tests/durability` | 18 passed | c12-q-7b |
| 7c | `pytest -m temporal tests/research` | 4 passed, 1 skipped, 1 xfailed (pre-existing) | c12-q-7c |
| 7d | `pytest -m temporal tests/replay` | 31 passed + the documented pre-existing golden flake (below) | c12-q-7d |
| 7e | `pytest tests/graph_workflow` | 255 passed | c12-q-7e |
| 7f | `ruff check .` | All checks passed | c12-q-7f |
| 7g | `ruff format --check .` | 1637 files already formatted | c12-q-7g |
| 7h | `mypy` | Success, no issues in 380 files (baseline 0 errors) | c12-q-7h |
| 7i | `python scripts/check_file_size.py` | clean | c12-q-7i |

## SC-001 — red before, green after

| Defect | Red evidence (on base, unmodified source) | Green |
|---|---|---|
| 6.2 (harvest) | `c12-red-62.txt`: harvest test 1 — one report in the messages tracked nothing as research | 4a test 1 |
| N2 (ceiling) | `c12-red-n2.txt`: deps test 1 — `assert 4.0 == 1.5` | 3 test 1 |
| N3 (limit degrade) | `c12-red-n3.txt`: report test 8a — the `UsageLimitExceeded` escapes `research_subquery` at toolset.py:58 | 2a (8a green) |

## The fixture

- `tests/replay/histories/architect_research_usage.json` — the **graph
  partial capture WAS produced** (no FeatureWorkflow fallback, no
  SG-9): `GraphWorkflow`, `source_commit` =
  `0711ba23577fe3e6c4a85d9dc0268d8c305d7131` (the harvest commit;
  captured once, after the harvest was green), 98 events.
- Decoded research `price_usage` input (c12-t013-decode.txt):
  `model='fake:research-answer' input_tokens=11 output_tokens=2
  cache_read_tokens=3 cache_write_tokens=4` — exactly `REPORT`; the
  architect's own is `zai:glm-5.3` 523/48.
- Capture ran ONCE (`c12-t011-capture.txt`), double capture agreed
  (SG-6 clear); `SDLC_CAPTURE_HISTORIES` was never set (SG-7 clear).

## Negative control — committed fallback (orchestrator ruling)

The orchestrator ruled: do NOT re-bind kroker-dev to a detached base
worktree; use the committed fallback — the fixture-shape check applied
to the existing report-less history. That is test 4
(`test_pin_rejects_an_unharvested_history`, green in 6a): the same
identification rule on `architect_research_tool.json` finds the
architect's own `price_usage` and NO research one after it — the shape
pin has teeth. Reason recorded: the mount was declined for this run.

## Forbidden paths and fixtures

- `git diff e5c8ef8 --stat -- <every forbidden path>` (models.py,
  research stage/step/budget_store/models, report_host.py, pricing.py,
  scenarios.py, harness.py, the named tests, pyproject.toml, uv.lock,
  the register file, earlier specs): **empty**.
- Fixture directories: zero existing files changed; the only change is
  the one added `architect_research_usage.json`.

## Line counts (all edited/new files, ceiling 1000)

`sub_run_usage.py` 87, `usage.py` 71, `toolset.py` 143, `deps.py` 131,
`architecture/step.py` 313, `role_host.py` 379, `agents/architect/
agent.py` 41, `test_sub_run_usage.py` 236, `test_role_usage.py` 158,
`test_architect_research_report.py` 426, `test_architect_research_
deps.py` 136, `test_architect_research_tool.py` 93,
`test_run_role_sub_run_harvest.py` 526, `_http_stub.py` 172,
`test_sub_run_usage_wire.py` 390, `architect_research_usage.py` 126,
`test_architect_research_usage_replay.py` 177.

## Pre-existing flake observed in 7d (for the orchestrator)

`test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[budget_arch_reject-…]`
failed intermittently under this session's back-to-back tier load:
`SG-3: command projection differs — At index 11 diff:
'activity:publish_artifact_version' != 'timer'` — byte-identical to the
documented load-dependent golden-tick race (`.workspace/tasks/
2026-10-02-golden-graph-trace-flake.md`, reproduced 3/3 on main
`2196438`, re-attributed to load, never fixed). Today it flickered
across the sandboxed/unsandboxed variants across three runs and passed
solo (c12-q-7d-rerun). The same full tier passed 32/32 on this branch
at T010 (c12-t010-6). The scenario's architect fake carries no research
tool, so no report and no harvest command can reach it; the golden is
untouched. Not this branch's defect; reported for a ruling.

## Deltas vs baseline.md

- Fast tier: 5559 → **5607** (+48; every new test green).
- mypy: 0 errors → 0 errors (380 files, +1 module).
- Lint/format/file-size: clean.
