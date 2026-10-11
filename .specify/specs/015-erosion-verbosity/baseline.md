# Round 015 baseline — erosion and verbosity

Branch `015-erosion-verbosity`, worktree `D:/own/Kroker-wt015-axis`,
base main `13a3093c` (spec set commit; code base is `c3f6319c` —
`git diff --stat c3f6319c HEAD -- src/sdlc/benchmarks src/sdlc/worker.py
BENCHMARK.md pyproject.toml uv.lock` prints nothing, so the plan's
base facts hold unchanged).

Container: `kroker-dev-axis` (image `kroker-dev:latest`), worktree at
`/app`, venv volume `kroker-verify-venv-axis` (snapshot of
`kroker-verify-venv`, taken 2026-10-11 ~13:45), `runs/` bind from the
primary tree. The sibling container `kroker-dev` stays bound to the
other in-flight worktree (`015-corpus-acceptance`, a separate round
that also claims the 015 number — numbering collision flagged to the
orchestrator; not resolved here).

Python in the container: 3.13.15. uv 0.12.21 at `/usr/local/bin/uv`.

## §1 Gates (container, one command per call)

| Command | Result |
|---|---|
| `uv run pytest` | 3 failed, 6047 passed, 12 skipped, 263 deselected, 249 warnings in 733.30s (0:12:13) |
| `uv run pytest -m temporal tests/replay` | 32 passed, 21 skipped, 171 deselected, 138 warnings in 121.22s (0:02:01) |
| `uv run pytest -m temporal tests/test_benchmark_workflow_sequence.py` | 5 passed in 29.37s |
| `uv run ruff check .` | All checks passed (0 issues) |
| `uv run ruff format --check .` | 1731 files already formatted |
| `uv run mypy` | Success: no issues found in 394 source files |

### Fast-tier failures (environmental, pre-existing at base)

The 3 failures are the container-git worktree limitation, identical to
the parallel round's baseline recorded the same day from the same
image (their baseline: same 3 test ids, same messages):

- `tests/test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`
  — `git check-ignore` in the container fails: the worktree `.git`
  pointer resolves a Windows host path
  (`fatal: not a git repository: /app/D:/own/Kroker/.git/worktrees/...`).
- `tests/test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`
  — `git show` fails, same `.git` link error.
- `tests/test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`
  — `git show` fails, same `.git` link error.

All three pass in trees whose `.git` the container's git can follow;
they are unchanged by this branch (worktree content = base). They are
the baseline the round's exit criterion compares against.

### Replay flake note

The first full replay run failed
`test_graph_golden.py::test_graph_workflow_reproduces_the_golden_trace[arch_revise_final-unsandboxed]`
— the known golden-tick flake (open inbox item since round 012). The
single test re-run passed (1 passed in 43.47s) and the second full
suite run above is clean. No `tests/replay/` file was touched.

## §2 Host gates

| Command | Result |
|---|---|
| `python scripts/check_file_size.py` | exit 0 (no file over 1000 lines) |
| `python scripts/check_clauses.py` | exit 0; 202 clauses declared, 10 untested, 0 dangling. Untested (pre-existing): ARCH-1.4, CODE-1.6, CODE-1.7, MERGE-1.6, MERGE-1.7, MERGE-1.8, MERGE-1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6 |

## §3 Records fingerprint (stored corpus, read-only)

```
111 2a32da9727fb624601fed84172f1b595bb69476a86ee5b8e323edec0d0e56831
```

`git ls-files runs/` prints nothing. Re-run before every commit; must
print the same line (the smoke run's own new bench dir excepted, T012).

## §4 Name check (data-model §8)

`git grep -nE "AxisBag|AxisInput|measure_code_axis|measure_files|axis_record|AXIS_EROSION_THRESHOLD|RULESET_VERSION|axis_measured|axis_not_measured|mean_erosion|mean_verbosity|015-quality-axis" -- src tests interfaces scripts`
→ exit 1, zero hits. Clean; no SG-1.

## §5 Verify items (file:line evidence, branch = base content)

- **(a)** `B/workflow.py:456-458` calls `finalize_benchmark_report`
  last, immediately before `return report_path`. Between the
  cell-record write (`workflow.py:411-424`) and it sits only the
  pre-012 `elif spec.language:` replay block (`workflow.py:425-452`)
  and a comment — nothing deletes the integration branch or a
  worktree. Holds.
- **(b)** `B/oracle.py:269` `branch = f"sdlc/{inp.run_id}/integration"`;
  `B/oracle.py:273` `_git(["worktree", "add", "--detach", wt, branch],
  inp.repo_url)`; failure at 274-277 returns
  `"no produced code (integration branch absent)"`. The checkout
  pattern T006's activity mirrors. Holds.
- **(c)** `tests/test_benchmark_workflow_sequence.py:106-107`
  `@activity.defn(name="grade_oracle")` stub; registered in the stub
  worker's activity list at `:186-187` beside `stub_record_benchmark`.
  The pattern T006's `stub_measure_code_axis` follows. Holds.
- **(d)** `src/sdlc/worker.py`: benchmark activity imports at
  `:63` (`summarize_cell`), `:65` (`grade_oracle`), `:68`
  (`finalize_benchmark_report`); the registration list at `:177-189`.
  The two places T006 edits. Holds.
- **(e)** Readers of the totals line (`runs started:`):
  `B/report.py:162` (the writer itself) and tests only
  (`tests/test_aggregate_benchmarks.py:304,389` — synthetic input
  strings the test builds itself, not `render_markdown` output;
  `tests/test_benchmark_report.py:390,530,538`). Readers of
  `grid.json`: `B/grid.py`, `B/score.py` (the writer/renderers the
  plan names) and tests only (`test_benchmark_cli.py`,
  `test_benchmark_grid.py`, `test_benchmark_report.py`,
  `test_benchmark_score.py`). No hit outside `B/` and `tests/` —
  no SG-2.
- **(f)** `tests/test_judge_literal.py:15-28` `EMITTED_JUDGES` =
  contract, llm_judge, human_override, error, oracle, deep_review,
  adversary, handoff, staged_rubric. `"axis"` absent today. Holds.
- **(g)** Corpus grep `"scope": "axis"` over
  `runs/benchmarks/**/*.jsonl`: exit 1, zero files. The negative
  proof's premise holds (R-10).
- **(h)** Container, venv python: `import radon` →
  `ModuleNotFoundError: No module named 'radon'`;
  `import ast_grep_py` → `ModuleNotFoundError: No module named
  'ast_grep_py'`. Both absent at base; T002 lands them.

## §6 Line counts (files this round touches)

| File | Lines at base |
|---|---|
| `B/models.py` | 463 |
| `B/runs.py` | 496 |
| `B/grid.py` | 400 |
| `B/workflow.py` | 459 |
| `B/report.py` | 314 |
| `src/sdlc/worker.py` | 298 |

All below SG-3's 800 with the plan's projected headroom.

## §7 Contradictions with research.md

None. Every verified fact of research.md reproduced at this base.
