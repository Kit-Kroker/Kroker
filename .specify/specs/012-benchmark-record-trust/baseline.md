# Baseline: round 012 (T001)

Date: 2026-10-07. Executor: implementer seat. All evidence taken in this
worktree at the base commit.

## Environment

- Worktree `D:\own\Kroker-wt012`, branch `012-benchmark-record-trust`,
  HEAD `7f5191d0` (`git rev-parse --short HEAD`). T001's branch-creation
  step was already satisfied by the orchestrator; verified here.
- `main` is still at `7f5191d0` — it has NOT moved past the base, so the
  `git diff --stat 7f5191d0 HEAD -- …` report of the task text does not
  apply (nothing to report).
- Working tree clean apart from the pre-copied spec set
  (`.specify/specs/012-benchmark-record-trust/`, untracked).
- `kroker-dev` is bound to THIS tree: md5 of
  `src/sdlc/benchmarks/models.py` is `2c318b98ead3b785ef12a240cc57ca23`
  on the host and `2c318b98ead3b785ef12a240cc57ca23` in the container
  (`docker exec kroker-dev md5sum /app/src/sdlc/benchmarks/models.py`).
- The primary checkout's `runs/` is mounted at `/app/runs` (43 entries
  under `/app/runs/benchmarks`). In-container git is non-functional for
  `/app` (`fatal: not a git repository: /app/D:/own/Kroker/.git/worktrees/Kroker-wt012`
  — the worktree pointer file names a host path), the same condition the
  011 baseline recorded.

## Gates (each command run once, one per shell call)

| Where | Command | Result |
|---|---|---|
| container | `uv run pytest` | **13 failed, 5674 passed, 11 skipped, 255 deselected** in 902.93 s. See "Fast-tier failures" below. |
| container | `uv run pytest -m temporal tests/replay` | 32 passed, 21 skipped, 171 deselected in 148.91 s |
| container | `uv run pytest -m slow tests/test_grade_oracle.py` | 1 passed, 6 deselected in 29.82 s (a slow test exists; not "no tests ran") |
| container | `uv run ruff check .` | All checks passed |
| container | `uv run ruff format --check .` | 1684 files already formatted |
| container | `uv run mypy` | Success: no issues found in 387 source files (0 errors) |
| host | `python scripts/check_file_size.py` | exit 0, no output (no file over the ceiling) |
| host | `python scripts/check_clauses.py` | exit 0; "202 clauses declared, 10 untested, 0 dangling" — the 10 untested lines are pre-existing: ARCH-1.4, CODE-1.6, CODE-1.7, MERGE-1.6, MERGE-1.7, MERGE-1.8, MERGE-1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6 |
| host | `python scripts/aggregate_benchmarks.py --runs D:/own/Kroker/runs/benchmarks --out <temp file outside repo>` | exit 0; summary line: `runs=41  with_data=41  passed=19  records=1249`; output kept at `C:/Users/start/AppData/Local/Temp/opencode/012-t001-aggregate.txt` for T011 |

### Fast-tier failures (STOP-GUARD reported to the orchestrator)

The three expected git-reading failures, same reason as the 011 baseline
(in-container git cannot read the bind-mounted worktree pointer):

1. `tests/test_plans_are_tracked.py::test_superpowers_scratch_is_still_ignored`
   — `AssertionError: assert False` at :48 (reads git state).
2. `tests/test_prompt_gate.py::test_unchanged_prompt_passes_without_calling_a_model`
3. `tests/test_promptfoo_provider.py::test_resolve_instructions_git_ref_reads_from_git`
   — `FileNotFoundError: agents/clarify/instructions.md does not exist at ref 'HEAD':
   fatal: not a git repository: /app/D:/own/Kroker/.git/worktrees/Kroker-wt012`
   (`src/sdlc/eval/promptfoo/provider.py:79`).

**Ten further failures the exec brief did not name — reported, awaiting
clearance before the T001 commit:**

    tests/research/test_research_registry.py::test_research_tree_loads_and_carries_tool_paths
    tests/review/test_deep_review_agent.py::test_registry_without_deep_review_still_validates
    tests/test_agent_folders.py::test_agent_py_without_build_rejected
    tests/test_agent_folders.py::test_duplicate_agent_names_rejected
    tests/test_agents_registry.py::test_complete_registry_helper_is_itself_valid
    tests/test_agents_registry.py::test_shipped_registry_models_are_the_005_targets
    tests/test_agents_registry.py::test_different_family_accepted
    tests/test_agents_registry.py::test_directory_registry_loads_and_validates
    tests/test_registry_ignores_fixtures.py::test_load_registry_ignores_a_fixtures_dir
    tests/test_registry_mirror.py::test_mirror_error_names_the_role_and_both_values

Diagnosis (all ten share one root cause, reproduced standalone): the base
commit `7f5191d0` ("feat: add core models and devops agent configuration")
changed `src/sdlc/core/models.py` `PipelineConfig.roles` defaults
`dev`/`devops` to `zai-coding-plan/glm-5.3` and updated
`agents/dev/agent.yaml` + `agents/devops/agent.yaml` to match, but did not
update the tests that pin the old assignment. Each failing test builds a
fixture registry (or asserts a pin) with the whole harness trio on
`zai-coding-plan/glm-5.2`, and `validate_registry`'s pipeline-mirror check
(`src/sdlc/agents/loader.py:331-358`) then raises:

    RegistryError: PipelineConfig.roles['dev'] does not mirror the agents/
    registry …: registry has (… model=zai-coding-plan/glm-5.2 …);
    PipelineConfig default has (… model=zai-coding-plan/glm-5.3 …)

This is a pre-existing breakage of main's own fast tier at `7f5191d0`
(reproduced in isolation; the registry itself loads consistently with the
new assignment when loaded directly). It is not caused by the worktree, the
container binding, or anything in this round. None of the ten is named by
tasks.md or plan.md "Existing tests changed on purpose" — SG-9/exec-brief
territory; clearance requested from the orchestrator before any commit.

## Records fingerprint (standing rule; re-run before every commit)

Computed in the container at `/app` (one-liner of the standing rules, run
via a byte-identical script file because PowerShell cannot pass the inline
quotes through) and independently on the host from the primary checkout —
both print the same line:

    108 7d335188d0a0a47e0234a9a3cea64f3e42d80e958996a4e3fb89e2bb76a4306c

`git ls-files runs/` prints nothing (exit 0).

## Name check (data-model §5)

`rg -n "kroker_commit|tree_dirty|CellStatus|cell_key|arm_label|is_pre012|NOT_EVALUATED|check_case_assets|MISSING_CASE_ASSET|resolve_provenance|summarize_cell|prompt_sha_for" src tests interfaces scripts`
→ no hits in `src/`, `tests/`, `interfaces/`, `scripts/` (searched each
root). Clean: none of the round's names already exists with another
meaning.

## Verify items

### (a) R-4 — stage sets of stored runs (read-only, `D:/own/Kroker/runs/benchmarks`)

- Stopped before code: `bench-cat-cafe-monitoring-1791120640` — 2 records:
  stages `{research: 1, oracle: 1}` (the oracle record despite the abort is
  finding F2). Also `bench-cat-cafe-monitoring-1791138008` — 3 records:
  `{research, clarify, oracle}`. No post-code stage (`analyze`, `merge`,
  `deploy`) appears in either.
- Reached merge: `bench-cat-cafe-monitoring-1791062646` — 71 records;
  stages include `analyze: 1` and `merge: 1` (post-code stages present).
  Runs `…1791166352` and `…1791179273` additionally carry `deploy: 1`.
- The rule "code finished ⇔ a post-code stage record exists" separates the
  two groups on the stored data. Item (a) holds.

### (b) R-4 — every way a code-finished run can end without a post-code record

Read: `workflows/graph_nodes/postplan.py`, `workflows/build.py`
(`run_tasks`), `stages/analyze/step.py`, `workflows/graphs/default.graph.yaml`.

First, what "code finished" is not: `run_tasks` returns a failure string —
`failed:dependency-cycle` (build.py:84), a merge conflict
(build.py:93/:112), `failed:quarantined-tasks` (build.py:114-117), or an
exception propagating out of `run_one` (build.py:43-52) — and `code_node`
then returns `port="halt"` (postplan.py:57-58). In every such case the code
stage did NOT finish (no `results` port), the run ends with no post-code
record, and the round's rule reads the cell as not graded — which matches
the spec edge case "dies part-way through the code stage with some tasks
integrated". Note this refutes research R-4's verify-(b) premise as
written ("the analyze stage runs after the code stage even when a task was
quarantined"): a quarantined task halts the code node itself, so analyze
never runs. A plain `failed` task (not quarantined) does NOT halt the loop
(build.py:89-93 merges only `done` tasks, the loop continues), so a code
stage with failed-but-not-quarantined tasks still finishes and analyze runs.

For a run whose code stage did finish (`code_node` → `port="results"`):
`default.graph.yaml:32-34` wires `code.results → analyze` and
`analyze.analysis → merge` unconditionally — no gate, no config skip. The
remaining ways it can end with NO analyze/merge/deploy record are all
abnormal terminations of the child after code and before the analyze
record's write (`analyze/step.py:153-167` writes the record only after the
analyst role call returns):

1. `analyze_node`'s `get_task_diff` activity exhausts its 3 attempts
   (postplan.py:69-73) → exception → run fails.
2. An exception inside `analyze.step` before `ctx.record` — practically the
   `ctx.run_role` analyst call failing (analyze/step.py:136-149); the
   internal diff fallback (:78-83) is unreachable in the graph path because
   `analyze_node` passes `diff`.
3. Cancellation / timeout / termination of the child between code
   completion and the record write (parent timeout, worker restart,
   external kill) — the spec's "killed from outside" edge case.
4. Defensive assertion failures in `analyze_node` (input models or
   `RunFacts.integration` unset, postplan.py:63-68) — not reachable in a
   well-formed graph.

Conclusion: no NORMAL path lets a code-finished run end without a post-code
record; the abnormal paths are exactly the ones the spec already classifies
as not graded. The rule stands as designed. (The refuted research premise
about quarantine is noted above for the record; it does not change the
rule — a quarantined run is not graded, per the spec edge case.)

### (c) R-5 — consumers of the stage-ended event's `outcome` string

The emitter: `BenchmarkHost._record` → `RunEventKind.STAGE_ENDED` with
`outcome=record.outcome.value` (`workflows/benchmark_host.py:96-113`).

- `src/sdlc/observability/summary.py:20-35` `_stage_outcome` — carries the
  raw string verbatim into `StageOutcome.outcome`
  (`src/sdlc/core/models.py:429-434`, plain `str`, comment "BenchmarkOutcome
  value"; no closed set, no mapping).
- `src/sdlc/observability/export.py:32, :80, :84` — renders `st.outcome`
  HTML-escaped; display only.
- `src/sdlc/dashboard/*` — every `outcome` hit is a different concept:
  `GateOutcome` (gate decisions, api.py:62/:204), run-level outcome
  summaries in fleet.py, `RunOutcomeWire` (graph_wire.py:465+). None reads
  the stage-ended outcome string.
- `interfaces/` — `GateOutcome` (gate decision UI, e.g.
  `interfaces/dashboard/frontend/src/api/types.ts:14`), `RunOutcomeWire`
  (run-level, `graph-types.ts:151-183`), `closedStatus()` over run-level
  outcome strings (`http.ts:36-43`). None maps the stage-ended outcome
  string to a closed set.

Item (c) holds: no consumer maps the stage-ended `outcome` string to a
closed set; a new `not_evaluated` value passes through unmapped.

### (d) R-7 — writer inventory: every `role=` passed to `stage_record` / `_stage_record`

Mechanism note: registry prompt text lives in `agents/<role>/instructions.md`;
the loader requires it for proposer-kind roles and forbids it for
kind=harness roles (`src/sdlc/agents/loader.py:177-204`); `REGISTRY[role].instructions`
is the prompt string or None (`src/sdlc/agents/roles.py:243-252` builds
`_STAGE_PROMPTS`/`PROMPT_SHAS` from it).

| Call site | stage | role | registry entry | instructions |
|---|---|---|---|---|
| `stages/analyze/step.py:155-158` | analyze | analyst | yes | yes |
| `stages/architecture/step.py:256-259` | architecture | architect | yes | yes |
| `stages/clarify/step.py:247-250` | clarify | clarify | yes | yes |
| `stages/code/step.py:207-210` | tool_approval | human | NO registry role | — |
| `stages/code/step.py:246-249` | tool_approval | human | no | — |
| `stages/code/step.py:448-451` | handoff | handoff | yes | yes |
| `stages/code/step.py:780-783` | code | `task.role` ∈ {dev, test, devops} | yes (all three) | None (kind=harness) |
| `stages/code/step.py:807-810` | qa | qa | yes | yes |
| `stages/deploy/step.py:168-171, :194-197, :239-242` | deploy | devops | yes | None (kind=harness) |
| `stages/merge/step.py:500-503, :596-599` | merge | reviewer | yes | yes |
| `stages/plan/step.py:150-153` | plan | planner | yes | yes |
| `stages/research/step.py:284-287, :362-365, :378-381` | research | research | yes | yes |
| `stages/review/step.py:146-152` | review | reviewer | yes | yes |
| `stages/review/step.py:214-220` | adversary | adversary | yes | yes |
| `stages/review/step.py:330-336` | deep_review | deep_review | yes | yes |
| `workflows/task_host.py:234-237` | tool_approval | human | no | — |
| `workflows/feature.py:242-245` | handoff | handoff | yes | yes |

Distinct writer roles: analyst, architect, clarify, human, handoff, dev,
test, devops, qa, reviewer, adversary, deep_review, planner, research.
Distinct record stages: research, clarify, architecture, plan, code,
tool_approval, qa, review, adversary, deep_review, handoff, analyze,
merge, deploy — exactly `CELL_STAGE_ORDER` of data-model §2.3 (14 stages;
intake and retro emit trace events only, intake/step.py:48,
retro/step.py:63-64, and write no record).

For T006's `PROMPTED_ROLES` expected value, two sets are on record here:

- writer roles that have a registry prompt (10): adversary, analyst,
  architect, clarify, deep_review, handoff, planner, qa, research,
  reviewer;
- the registry's full prompted set (14): those ten plus devops_planner,
  discover, merge_verdict, risk (prompted registry roles that never appear
  as a record writer).

`human` is not a registry role at all. data-model §2.2 says `PROMPTED_ROLES`
is "built from the registry at import"; T006's test pins it against this
list — the implementation should derive the set from the registry (the
14-role set) and this inventory proves every prompted writer role (the 10)
is inside it; which of the two the pin asserts is flagged to the
orchestrator for the T006 reviewer's attention.

### (e) R-9 — `_now()`, the qa step, the qa record

- `_now()` (`stages/code/step.py:79-83`): `try: return workflow.now()`
  with a wall-clock fallback outside a workflow context — confirmed, it
  wraps `workflow.now()` (deterministic in workflow code).
- The qa step (`stages/qa/step.py:117-187`) returns the qa proposer's
  `QAReport` (with `issues`). There is no "qa lens disabled" state at
  base: no `qa_enabled` flag exists (only `review_enabled`
  core/models.py:390, `deep_review_enabled` :393,
  `adversarial_review_enabled` :395), `qa_step` is called unconditionally
  in the fix loop (code/step.py:749-759), and a None `qa_agent` would fail
  `agent.run` in `RoleHost._run_role` (role_host.py:190-192) rather than
  skip. So the qa record (code/step.py:805-821) is written on EVERY
  attempt, with `started=_attempt_started` (:811 — the attempt start, F4)
  and `outcome=task_passed` (:815 — the task's combined verdict, F7's qa
  part). Contrast: the review step returns None when disabled or agentless
  (review/step.py:123-124) and then writes no record — §5.8's review half
  already holds at base; its qa half has no trigger at base (T017's
  FR-022 guard is for a state that cannot occur through config today).

### (f) R-6 — `_ensure_python_env`

`_ensure_python_env(worktree, timeout_s)`
(`stages/qa/activities.py:128-204`):

- creates the venv at `<worktree>/.sdlc-venv` (`_VENV_DIR_NAME` :116,
  venv_dir :152, created idempotently :158-163 with `sys.executable -m
  venv`; reused across calls);
- installs, in order: uv into the venv (:175); the produced project via
  `uv pip install -e ".[dev]"` when `uv.lock` exists (:176-181) else
  `pip install -e ".[dev]"` + `pip install -e <worktree>` (:182-184); each
  present file of `_REQUIREMENTS_FILES` (:193-195); then unconditionally
  `pytest pytest-cov ruff` (:196-198). Venv-creation failure returns
  `(None, "venv creation failed: …")`; install failures are tolerated;
- returns `(env, None)` where `env = dict(os.environ)` (:200) — a FULL,
  otherwise-unfiltered copy of the worker environment — with the venv's
  script dir prepended to `PATH` (:201), `VIRTUAL_ENV` set (:202) and
  `PYTHONHOME` popped (:203). `PYTHONPATH` and everything else from the
  worker passes through: the oracle must not hand this dict to its test
  command unfiltered (research R-6 confirmed).

`.sdlc-venv` and the produced repos' git — what is actually true:

- The produced projects' own `.gitignore` does NOT list `.sdlc-venv`
  (e.g. cat-cafe task branch T01 `.gitignore`: `__pycache__/`,
  `*.py[cod]`, `.pytest_cache/`, `.venv/`).
- Neither oracle-case scratch repository's `.git/info/exclude` nor a
  global exclude covers it (checked `D:/own/sdlc-scratch-repos/{cat-cafe-
  monitoring,todo-api-greenfield}/.git/info/exclude` and the container's
  `/root/.gitconfig` + `/root/.config/git/ignore`).
- Empirically (a temp git repo inside the container), a plain
  `git add -A` DOES sweep an untracked `.sdlc-venv` into a commit.
- However, no branch of either scratch repository ever committed a
  `.sdlc-venv` path — `git rev-list --all --objects | grep sdlc-venv`
  matches nothing in either repo — so a FRESH WORKTREE of an integration
  branch never contains a committed `.sdlc-venv`, which is the fact
  research R-6's verify needed. Residual risk noted: a fix-loop attempt's
  checkpoint (`git add -A`, `stages/code/activities.py:180`) that follows
  a venv provisioning in the same task worktree would commit it; on the
  stored history this never happened (multi-attempt checkpoint pairs show
  empty diffs). T016's oracle provisioning removes a pre-existing
  `.sdlc-venv` in its fresh worktree first, per its task text.

### (g) tests referencing `_CASES_DIR`, `_cases_dir` or `_CALIB_DIR`

None. `grep` over `tests/` finds no reference to any of the three names
(checked before any edit). T003's "move every test listed in T001(g)" is
therefore the empty set at this base. Source sites of the three names (all
in `src/sdlc/benchmarks/`, for T003's map): `calibration.py:240` (def
`_CALIB_DIR`, used :262), `cli.py:167, :173`, `judge.py:221` (def
`_CASES_DIR`, used :236), `oracle.py:161` (def `_cases_dir`, used :195),
`report.py:11` (imports `_CASES_DIR`), `report.py:115`, `tasks.py:75` (def
`_cases_dir`, used :89) — plus the module-path cases derivations at
`cli.py:265` and `:297`. `B/score.py:17` and `B/experiments.py:38` derive
the repository root (not the cases location) and stay.

## Line counts (physical lines)

| File | Lines |
|---|---|
| `src/sdlc/stages/code/step.py` | 991 (budget ≤ 997; SG-3 at 1000) |
| `src/sdlc/stages/merge/step.py` | 630 |
| `src/sdlc/benchmarks/workflow.py` | 334 |
| `src/sdlc/benchmarks/oracle.py` | 279 |
| `src/sdlc/benchmarks/models.py` | 282 |
| `scripts/aggregate_benchmarks.py` | 625 |
| (`src/sdlc/stages/analyze/step.py` | 187) |
| (`src/sdlc/stages/review/step.py` | 367) |

All match the plan's expectations.

## Context recorded for later tasks (no action)

- `runs/pipeline/` holds only `bf-e2e-*` runs — no export exists for
  benchmark children (T019 premise confirmed at base).
- `runs/ops/` holds flat `bench-*-console.log` / `bench-*-stderr.log`
  files (cat-cafe run1/run2, w1r1..w1r3 seen; full listing at T019) —
  evidence source (1) of T019 exists.
- Scratch-repo shape: `cat-cafe-monitoring`'s `main` (base) branch tree is
  EMPTY (init commit only; `git ls-tree main` prints nothing) — the F3
  empty-tree phenomenon is visible in the scratch repo itself. Task and
  integration branches exist per run under `sdlc/<run_id>/…`.

## Verdict of the Verify items

(a) holds; (b) holds with the quarantine-premise refutation noted (the
rule it guards is unaffected — see the analysis); (c) holds; (d) recorded
above (with the 10-vs-14 PROMPTED_ROLES question flagged); (e) recorded
(no qa off-switch exists at base; qa record always written); (f) recorded
(env dict is unfiltered os.environ + venv vars; fresh integration worktrees
provably never contain a committed `.sdlc-venv`); (g) empty set. No item
contradicts research.md's rule in a way that re-opens the design; the two
nuances (b's premise wording, d's 10-vs-14 set question) are reported with
this baseline.

**Open stop-guard:** the ten registry-mirror fast-tier failures at base
(main's own tests, broken by `7f5191d0` itself). Clearance requested from
the orchestrator before the T001 commit lands.
