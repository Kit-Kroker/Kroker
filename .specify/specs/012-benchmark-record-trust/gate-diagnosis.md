# Gate diagnosis (T019, FR-023)

Subjects: every stored todo-api run that scored a full 6/6 on the held-out
oracle and still ended merge-rejected — `bench-todo-api-greenfield-1790982758`,
`-1791009988`, `-1791032445`, `-1791051721` — and two cat-cafe runs that
reached merge: `bench-cat-cafe-monitoring-1791062646` (12/12 oracle) and
`-1791166352` (10/12).

## Evidence sources, and which were used

1. **Stored exports/logs: nothing.** `runs/pipeline/` holds only `bf-e2e-*`
   runs — no export exists for benchmark children. The `runs/ops/bench-*`
   console logs are 64-byte stubs containing only the report.md path; the
   stderr logs are empty. Used for: ruling the cheap source out.
2. **Re-running the deterministic merge checks on the stored result** (the
   main evidence). The checks the merge step itself calls —
   `prepare_base_worktree`, `run_integration_checks` (scoped tests + lint),
   `measure_coverage`, `scoped_security_scan`, then `evaluate_gate` over the
   absolute + security checks — were invoked directly, from a throwaway
   script kept outside the repository, against a detached temporary worktree
   of each run's `sdlc/<run_id>/integration` branch in a docker-cp copy of
   the scratch repository (this container has no /srv/scratch-repos bind —
   same deviation as T014; the originals untouched, every worktree removed
   afterwards). One methodological note, honestly recorded: the script's
   first pass reused one base-worktree id across runs, which made todo-api's
   base checkout fail inside a cat-cafe worktree; corrected with per-run ids
   and re-run — all numbers below are from the corrected pass.
3. **Analyze, from code and stored record shapes.** The analyst's own report
   and the run's plan (the authoritative criteria set) are not stored for
   benchmark children, so which criteria were untraced cannot be
   established; what the mechanism is, can (below).

## Finding: the merge gate

| run | oracle | absolute blockers (re-run) | detail |
|---|---|---|---|
| todo-api 1790982758 | 6/6 | `build_integration_green`, `lint_clean` | 1 introduced failing test file (`tests/test_app.py`); 1 introduced lint (I001, unsorted import in the same file) |
| todo-api 1791009988 | 6/6 | `lint_clean` | 1 introduced (RUF007) |
| todo-api 1791032445 | 6/6 | `lint_clean` | 2 introduced (RUF100 ×2, unused noqa) |
| todo-api 1791051721 | 6/6 | `lint_clean` | 5 introduced (incl. BLE001 blind-except) |
| cat-cafe 1791062646 | 12/12 | `build_integration_green`, `lint_clean` | head test run exits 4 with no parseable JUnit (collection failure in the produced tests); 27 introduced lint (F401 unused imports, produced tests) |
| cat-cafe 1791166352 | 10/12 | **none** | tests green, lint clean, coverage 99.0%, security clean — NOT an absolute rejection |

**Cause (merge, five of six subjects):** the absolute `lint_clean` check —
and, in two runs, the scoped test check — fail on genuine defects in the
produced code. The greenfield implementations trip the repository's own
ruff configuration (I001/RUF007/RUF100/BLE001/F401) and, in two runs, ship
test files that fail or cannot be collected. The held-out oracle passing
6/6 says the functionality is there; the merge gate holds produced code to
the repo's own lint and test bar. **These are right-reasoned rejections of
the produced code, not benchmark-mode conditions** — no remote, no human
gate, no network, nothing a benchmark run cannot have is involved.

**Cause (merge, sixth subject 1791166352):** every absolute check passes;
its stored analyze record is FAIL (quality 0.0 ⇒ untraced criteria
existed) and its merge record carries outcome `revise` with quality 1.0 —
the advisory path. The advisory rejection is traceability-driven (see
analyze below); it is the merge gate acting on the analyze result, again
not a benchmark-only condition.

## Finding: the analyze gate

Every stored analyze record of the audited runs is FAIL with quality 0.0
and no error text. The enforcement — `untraced_criteria`
(S/analyze/models.py:36-51) — is workflow-side, not the LLM's verdict: a
criterion counts as traced only when the analyst's report contains a
`CriterionTrace` carrying that EXACT `(task_id, criterion)` text from the
plan AND a non-empty `tests` list. Anything the analyst omits, paraphrases,
or maps to zero tests is untraced.

**What can be established:** the mechanism, and that the produced trees are
not test-deserts — 1791166352's integration branch ships twelve test files
with 99.0% diff coverage, so untraced criteria with genuinely missing tests
are not in evidence. The plausible reading is citation gaps (the analyst
not reproducing every criterion verbatim) — **but this is inference**.

**What cannot be established without the analyst's report (not stored, and
the plan's authoritative criteria are not stored either):** which criteria
were untraced in any given run, and whether a test existed for each. Filing
the storage gap (no pipeline export / no analyst report for benchmark
children) as a follow-up candidate; out of this round's scope.

## Proposed per-gate decision (ruling R2; for the orchestrator)

- **Merge — absolute checks (tests, lint): stay rejections.** They inspect
  the produced code; the rejections above are right-reasoned. No repair, no
  not-evaluated. The audit's "every run rejected" is the produced code
  failing the repo's own bar — visible on the record from T020 on (the
  blocking check names and details in the record's error).
- **Analyze — traceability (and merge's advisory path acting on it): stays.**
  It inspects the produced tests against the plan's criteria; no
  benchmark-only dependency was found in any evidence source. From T020 on
  the record names the untraced count and the first three.
- **No not-evaluated gate is proposed**: neither gate depends on something
  a benchmark run cannot have (checked: no remote, no human-decided gate in
  these paths, no network — the absolute/advisory rejections above are all
  code-inspecting).

If the orchestrator answers "no code change for either gate", T021 is the
contract §6.5 line and the `.md` lines only.
