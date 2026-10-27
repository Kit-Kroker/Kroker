# Research: glm-5.2 Arm Retirement (round 019)

Decisions D-1 to D-9, each checked in the tree at branch head `6ba483a6`.
Sources: advisor `D:\own\Kroker\.workspace\tmp\advisor-019-1.md`, skeptic
`D:\own\Kroker\.workspace\tmp\skeptic-019-1.md`, and the planner's own
probes, recorded below. `B/` = `src/sdlc/benchmarks/`.

## D-1 — Live catalog and the pair

- **Decision**: strong arm `zai-coding-plan-glm-5.3` (dev, test and devops
  all `zai-coding-plan/glm-5.3`). The weak arm is the existing
  `zai-coding-plan-glm-5.3-flash`, kept byte-for-byte (GATE 1 Q0 = A).
- **Evidence**: `kroker-worker-1:/root/.cache/opencode/models.json`
  (2026-10-26 17:28), provider `zai-coding-plan`. Deprecated: glm-4.7,
  glm-5-turbo, glm-5.2, glm-5.2-highspeed. Live: glm-5.3, glm-5.3-flash,
  glm-5.3-highspeed.
- **Naming**: `_arms_for` (`B/matrix.py:29–40`) desugars a `models:`-only
  case to `<family>-<model id>`. A re-paired case therefore gets the same
  arm and cell id as a case the importer would create with only `models:`
  (FR-004).
- **Alternatives**: `glm-5.3-highspeed` as a weak arm was rejected. It is
  almost certainly the same weights as glm-5.3, so it gives no capability
  gradient.

## D-2 — Kept and dropped case fields

- **Decision**:
  - `models:` becomes `[zai-coding-plan/glm-5.3, zai-coding-plan/glm-5.3-flash]`.
  - The `extra_args_by_model` key is deleted (only cat-cafe and
    theatre-box-office have it).
  - `arms:` lists the strong arm first, then flash.
- **Rationale**:
  - When `arms` exist, `models` does not drive expansion (`matrix.py:29–40`).
    It is still a required field (`CaseSpec.models` has no default), and the
    FR-001 sweep reads it, so it mirrors the arm model set.
  - `workflow.py:105` reads `extra_args_by_model.get(model, [])`, so an
    absent key is safe. The glm-5.3 family declares no opencode variants
    (todo-api comment, `case.yaml:31–34`).
- **Trap**: `tests/test_benchmark_corpus.py:107–108` claims the base cell id
  comes from `models:`. It actually comes from arm names
  (`matrix.py:136`). Fix the comment when that test is rewritten.

## D-3 — Acceptance semantics of an arm swap (FR-005, FR-007)

- **Oracle identity is untouched.** `oracle_identity()` hashes `oracle/`
  files only (`B/oracle_id.py:13`).
- **The arm link breaks.** `separation()` (`B/acceptance.py:80`) selects
  graded runs by `oracle_id` and then by arm name. glm-5.2 runs fall into
  `not_comparable`.
- **Flash runs carry into the weak slot.** They have the same arm name and
  the same oracle. Runs group by `run_id`, so the proposer-stage
  `#proposer#zai_glm-5.3.jsonl` records inside glm-5.2 run ids belong to the
  glm-5.2 run (`B/runs.py:187–200`, `_arm_of` `:321`).
- **No stored run carries the new strong name.** Grep over
  `D:\own\Kroker\runs` for the exact arm `zai-coding-plan-glm-5.3` outside
  todo-api found 0 files.
- **Expected `decide()` walk** under the new arms:

| Case | Reference/floor (today) | Separation after swap | Expected verdict |
|---|---|---|---|
| cat-cafe-monitoring | pass / pass | strong: no scores; weak: flash 0.833 | `not_assessed`, note "no strong arm runs" (`acceptance.py:186`) |
| deveval-geotext | pass / pass | strong: no scores; weak: flash 0.222 | `not_assessed`, "no strong arm runs" |
| deveval-readtime | pass / pass | strong: no scores; weak: flash 0.250 | `not_assessed`, "no strong arm runs" |
| theatre-box-office | pass / pass | strong: no scores; weak: flash 0.0179 | `not_assessed`, "no strong arm runs" |
| deveval-lice | **reference fails** 30/31 | (not reached) | `rejected reference` (`:175`) |
| deveval-hone / -pso / -stocktrends | parked | sentinel "not assessed for parked case" | `not_assessed` (`:183`) |

- **Corpus tally**: 1 of 8 before, 0 of 8 after.
- **Cross-commit confounder (skeptic L1, accepted)**:
  - The carried-over flash runs were graded on older commits. For example,
    cat-cafe's flash run predates the backoff in `dea09d36`.
  - A future glm-5.3 run on a newer commit would measure pipeline drift as
    well as model difference.
  - `acceptance.yaml`'s `kroker_commit` stamps the commit that **wrote the
    record**, not the commit of the evidence (`cli.py:502`, existing
    semantics).
  - Mitigation, in the FR-011 follow-up card: the re-proving reruns run
    **both** arms on one commit, n ≥ 3 each, as `accepted` already requires
    (`MIN_RUNS_PER_ARM`). Carried flash runs then only add to the pool and
    never stand alone.
- **Saturated, degenerate and stalled branches** all need
  `separation.strong.scores` to be non-empty (`:189`). With an empty strong
  arm they are never reached, so the branch at `:186` fires first.

## D-4 — Re-label mechanics

- **Decision**:
  - Per case: edit `case.yaml`, run the real `benchmark accept <case>`
    (online), compare the printed `<case>: <verdict> (<reason>)` line
    against D-3, then check `separation.strong.arm` is the new name and
    `run_ids` is empty.
  - Commit only when every case matches.
  - On a mismatch, restore the file with
    `git checkout -- <case>/acceptance.yaml` and stop (SG-2).
  - No prediction step.
- **Rationale**: `decide()` needs the reference and floor results, which
  are the expensive part. A dry run would repeat them. git revert gives the
  same guard.
- **Gate on verdict and reason only.** `oracle_tests`, reference counts and
  floor counts may move. They are logged in the round's verification.md and
  never stop the round.
- **Infra-failure guard**: a failed oracle venv writes `passed=False` with
  "oracle environment failed: …" (`offline_checks.py:101–106`). A timeout or
  a missing junit also yields `passed=False` (`:115–135`). For lice that
  reproduces the expected verdict silently. So a re-label whose
  `reference.detail` starts with `oracle environment failed`, or whose
  `tests_total` is 0, is never committed (SG-3).
- **Capture first**: before any accept, record each case's old verdict,
  reason, note and separation means from `git show HEAD:<path>` into
  `baseline.md`. FR-006's notes are written from those values.

## D-5 — Where accept runs

- **Fact**: `kroker-kroker-dev-1` binds `D:/own/Kroker` (the main tree) at
  `/app`, not this worktree. `docker inspect` shows mounts `D:/own/Kroker → /app`,
  runs at `/app/runs` and private cases at `/srv/private-cases`.
- **Decision**: a throwaway container from the same `kroker-dev:latest`
  image, with these mounts:
  - the worktree at `/app`, read-write;
  - the `kroker-verify-venv` volume at `/app/.venv`;
  - `D:/own/Kroker/runs` at `/app/runs`, **read-only**;
  - `D:/own/sdlc-private-cases/cases` at `/srv/private-cases`, read-write;
  - environment `SDLC_PRIVATE_CASES_ROOT=/srv/private-cases`;
  - environment `KROKER_COMMIT=<host git rev-parse --short=8 HEAD>`. The
    worktree's `.git` file points at a Windows path
    (`gitdir: D:/own/Kroker/.git/worktrees/...`), so `git rev-parse` fails
    inside the container. `resolve_repo_status` (`B/smoke.py:146–191`) then
    falls back to `KROKER_COMMIT`. Without it every re-labelled record
    would stamp `kroker_commit: unknown`.
  - No `uv sync` runs inside it, because the venv volume is shared with
    `kroker-dev` (venv lock-drift note). Commands use
    `/app/.venv/bin/python -m ...` or `uv run --no-sync`. The editable
    install resolves `/app/src`, which is the worktree.
- **Rationale**:
  - A read-only runs mount turns FR-008 from a check into a guarantee:
    accept physically cannot write records. The manifest is still taken.
  - The live `kroker-dev` is not rebound, because changing run
    infrastructure is the user's call.
  - Precedent: "verify main in a throwaway container" (runs-unified-layout
    note).
- **Alternative**: host-side `uv run` with
  `SDLC_BENCHMARKS_ROOT=D:/own/Kroker/runs/benchmarks` (`B/recorder.py:24`).
  Kept as fallback only: the dev container is the run environment (user
  directive 2026-09-30).

## D-6 — Arm-drift staleness rule (FR-009)

- **Decision**: in `corpus_status()`, after the `record is None` branch and
  the oracle check, mark the record stale when all of these hold:
  - the case is `spec.role == CORPUS`;
  - `record.separation is not None`;
  - `(sep.strong.arm or None, sep.weak.arm or None) != (spec.strong_arm, spec.weak_arm)`.

  The value is `True`, the same as oracle drift.
- **Sub-rules**:
  - `separation is None` (offline, no oracle, or lice's record) means no
    arm claim, so no drift.
  - The role comes from the case, not the record, so parked rows stay
    `stale is False`.
  - None on either side counts as a claim, so "weak absent → weak declared"
    is drift.
- **Rationale**: FR-009 says "exactly as oracle drift". The tally already
  excludes anything that is not `False`. A string value would add a
  rendering path with no action attached.
- **Readers**: `CorpusRow.stale` is read only in `B/corpus.py` (build, render
  and tally) and `tests/test_benchmark_corpus.py`. `cli.py:471–476` passes
  rows through. No dashboard or scoring reader.
- **Known limits (skeptic L2, accepted, written into BENCHMARK.md)**:
  1. The rule compares arm **names**. If an arm keeps its name but its
     `role_models` change, the record does not go stale. Catching that would
     need a new record field, an arm-definition hash, which is out of this
     round. This round renames every changed arm, so it never hits the case.
  2. Records with `separation: null` (offline accepts, such as lice's
     current record) are never stale on arms. A null-separation record's
     verdict never read the arms, so nothing it claims is invalidated. After
     the online re-label, lice's record carries a computed separation
     (data-model §2) and the normal rule applies to it.
- **Today's rows**: every current record's arms equal its case's arms, so
  the rule flips no row before the round's edits (checked in D-3 inputs:
  each `acceptance.yaml` separation names `…-glm-5.3-flash` / `…-glm-5.2`,
  the same as `case.yaml`). Lice has `separation: null`.

## D-7 — Test role flip (FR-003)

- **Decision**: these three change in one commit:
  - `agents/test/agent.yaml:3`;
  - `S/core/models.py:375`;
  - the `tests/conftest.py:175–182` mirror fixture.

  Their tests are updated in the same commit:
  - `tests/test_agents_registry.py:15–18`;
  - `tests/test_registry_mirror.py:58, 86`.
- **Checks**:
  - `check_adr6_families` (`S/agents/loader.py:219–241`) covers only dev,
    reviewer and deep_review.
  - `check_adversary_model` (`:244–267`) compares the adversary with dev and
    reviewer. Its id `glm-5.3-flash` differs from dev's `glm-5.3`.
  - No check forbids test == dev.
  - The mirror is enforced by `_validate_pipeline_mirror` (`:331–343`).
- **Replay**: `PipelineConfig()` is built inside the workflow when no config
  is passed (`S/workflows/feature.py:285, 341`), so run the `-m temporal`
  replay gate after the flip.
- **Memo**: `content_key` includes the model id
  (`S/memoization/cache.py:42–47`). A changed model misses the cache and
  never serves a stale hit, and the memo is off by default.
- **Recorded risk**: dev and test are now the same model (Q3 = A was a
  knowing choice). Plain pipeline runs put three roles on the full glm-5.3
  quota. Backoff landed in `dea09d36`.

## D-8 — Tests pinned to repo cases

- **Must change**:
  - `tests/test_benchmark_corpus.py:18–26` (`CORPUS_BASE_CELL_IDS`) and
    `:107–125`, which name the glm-5.2 cells and arms on real cases;
  - `tests/test_golden_case_loads.py:48–50`, which names the cat-cafe cell
    ids.
- **Not affected**: synthetic arm strings in `test_benchmark_acceptance`,
  `_runs`, `_root_cause`, `_stored_scores` and `_judge_none_readers`;
  `test_private_leak.py:290–310`, which uses its own YAML;
  `tests/durability/fixture_agents/*` (`anthropic:glm-5.2`, out of scope).

## D-9 — Manifest (FR-008)

- **Decision**: sha256 every file under `D:\own\Kroker\runs\benchmarks\**`
  (017 precedent), sorted by forward-slash relative path, into
  `baseline-records.sha256`. Taken before the first accept and re-checked
  before the closing commit.
- **Rationale**: accept writes only `<case>/acceptance.yaml`
  (`acceptance.py:255–262`, `cli.py:515, 567`). `_all/` and `_case/` are
  written only by score and report. Hashing the whole tree catches stray
  writes. No `benchmark score` or `report` runs in the round.
