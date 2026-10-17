# Verification: Decomposition Case (round 016)

**Branch** `016-decomposition-case`, worktree `D:\own\Kroker-016`,
code base main `b01f9b07` (see `baseline.md` for the SG-2 rebase history).
**Part 1 = the code half (T001 to T013).** Part 2 (run batches, verdict)
is appended after R1 per the plan; aggregates only throughout — no
private case content in this file.

## 1. Full gates at T013 (vs the T001 baseline)

Container (`kroker-dev`, worktree at `/app`, one command per call):

| Command | T001 baseline | T013 seen | Delta |
|---|---|---|---|
| `uv run pytest` | 22 failed / 6229 passed / 12 skipped / 272 deselected | 22 failed / 6331 passed / 13 skipped / 273 deselected | the SAME 22 pre-existing failures (16 stale stored-score pins, 3 DevEval parked-role drift, 3 container-git worktree-pointer — baseline.md §2); +102 passed = the round's added tests; +1 skipped = the REAL_PRIVATE_ROOT opt-in leak test |
| `uv run pytest -m slow tests/test_benchmark_offline_checks.py` | (not in T001's list) | 2 passed / 13 deselected | the two real-environment cases (reference+floor, tree mode), both green |
| `uv run pytest -m temporal tests/replay` | 32 passed / 21 skipped | **31 passed / 1 failed** / 21 skipped | DEVIATION, see §1.1 |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 9 passed | 9 passed | none |
| `uv run ruff check .` | 0 issues | All checks passed (0 issues) | none |
| `uv run ruff format --check .` | clean | 1782 files formatted | none |
| `uv run mypy` | 0 errors / 405 files | Success, 0 errors / 405 files | none |

Host: `check_file_size.py` RC 0; `check_clauses.py` 202 declared /
10 untested / 0 dangling; the records manifest `baseline-records.sha256`
851/851 byte-identical; `git ls-files runs/` empty; `pre-commit run
--all-files`: every hook Passed on the committed content — NOTE: the
whitespace fixer hooks auto-"fix" ~90 PRE-EXISTING tracked files (agents/
instructions, deveval case references) on an --all-files run; that
collateral is outside this round's scope (forbidden paths) and was
reverted to HEAD both times it occurred; every actual commit of the
round passed all hooks unmodified, including the new
`check-private-leak` guard (skipping with its note — no store exists
on the machine yet).

### 1.1 Replay deviation (recorded, exonerated, NOT this round's diff)

`test_graph_golden[budget_arch_reject-sandboxed]` fails on the ordering
of a budget gate timer vs `activity:publish_artifact_version`, with the
golden's appended `activity:cleanup_run_worktrees` unreproduced in the
same run. Diagnosis evidence: the IDENTICAL failure reproduces on the
pristine base `b01f9b07` with every round-016 change stashed (checkout
verified), i.e. the golden-tick race the orchestrator's T001 ruling
already names ("2 transient failures on one run were the known
golden-tick race flake, green on rerun" — on this machine, this
evening, the param failed consistently across ~6 runs and 40 minutes;
T001's 32-passed snapshot predates the drift). `tests/replay/` is a
forbidden path for this round; the reviewer ruled the T009 diff
exonerated and the deviation accepted for the record. Flagged to the
orchestrator: if the param is still red at merge time, the fix belongs
to main, not to 016.

## 2. T008 — the offline judge proof (ruling R3; paid, pre-cleared at GATE 2, cap USD 1)

Run in `kroker-dev` through the T007 production code path
(`generate_steps` then the scoring call, `Agent(model_settings=
ModelSettings(max_tokens=judge_max_tokens()))`) on the two stored 015
R2 cat-cafe plan artifacts with `rubric-planner.md`, judge
`anthropic:claude-sonnet-5`, host `.env` keys (copied into the
container for the run, removed after; throwaway script under
`.workspace/tmp/`, never committed):

- strong `plan-v25.json`: `judge == "staged_rubric"`, **score 0.95**
- weak `plan-v24.json`: `judge == "staged_rubric"`, **score 0.92**
- 3 model calls total (the second artifact's step call served from the
  production step cache by design); every call ran at
  `max_tokens=16000` with `finish_reason="stop"` — no truncation
- tokens 15,473 in / 10,128 out; the provider's cost field is null via
  the proxy, so spend is estimated at Sonnet list pricing (3/15 USD per
  M tokens) ≈ **USD 0.20**, within the USD 1 cap

The value 16000 works, so `DEFAULT_JUDGE_MAX_TOKENS` stands and no
commit followed (T008's "else" branch). Corroborating record: the
strong run's own research-stage record carries the pre-fix failure text
`"Model token limit (provider default) exceeded before any response was
generated"` — exactly the V1 mechanism the budget removes.

## 3. V6 — plan shape reproduced (T011)

`uv run python scripts/decomposition_report.py --baseline-plan
<plan-v25.json> --baseline-plan <plan-v24.json>`:

- strong: tasks 10, edges 18, longest chain 7 nodes, dangling 0
- weak: tasks 10, edges 16, longest chain 6 nodes, dangling 0

Exactly the reviewer-recomputed figures the spec quotes.

## 4. Line counts (physical, at T013)

| File | T001 | T013 | Guard |
|---|---|---|---|
| `B/paths.py` | 63 | 164 | 900 |
| `B/cli.py` | 662 | 692 | 800 (SG-3) |
| `B/corpus.py` | 167 | 196 | 900 |
| `B/offline_checks.py` | 137 | 182 | 900 |
| `B/judge.py` | 317 | 351 | 900 |
| `B/tasks.py` | 152 | 173 | 900 |
| `B/report.py` | 345 | 345 | 900 (reader swap only) |
| `src/sdlc/artifacts/capture.py` | 55 | 83 | 900 |
| `tests/conftest.py` | 345 | 353 | 900 |
| `scripts/check_private_leak.py` | — | 253 | new |
| `scripts/decomposition_report.py` | — | 242 | new |

All under the ceilings (`B/cli.py` under its 800 guard; everything else
under 900). Two test files were split along process seams when the 016
additions crossed the 1000-line ratchet: `tests/test_benchmark_cli_
private_root.py` (parent kept at exactly 1000) and
`tests/test_benchmark_judge_budget.py` (parent returned byte-identical
to its pre-T007 state).
