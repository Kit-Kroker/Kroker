# Pre-flight evidence — round 025 Part B (T020, 2026-11-16)

Fleet commit candidate: `b55773ff` (HEAD, tree clean; includes the
orchestrator's I001 import-sort fix `b55773ff` on top of T014 `c98cfcf2`).
All commands from the primary checkout at that commit.

## Checklist (spec B.2)

### 1. CLI verbs/flags re-read (`src/sdlc/benchmarks/cli.py`) — PASS

- `benchmark run --case <case.yaml> --arm <name> --gate-policy soft`
  (`--arm` names an arm; corpus cases refuse a multi-arm matrix without
  `--arm`/`--all-arms`, cli.py:328); arm for the fleet:
  `zai-coding-plan/glm-5.3` (declared in every case's `models:`).
- `benchmark smoke --gate-policy soft` (no arm filter — both todo-api arms
  run; `check_smoke` needs rubric scores on clarify+architecture).
- `benchmark score --all --out <dir>`; `benchmark verify-case --case <id>`
  (dispatch_verify_case, cli.py:700).

### 2. Doctor — PASS with two recorded notes

`uv run python -m sdlc.cli doctor`: 10 passed, 1 warning, 2 failed.

- PASS: provider keys `ANTHROPIC_API_KEY, EXA_API_KEY, ZAI_API_KEY` set
  (judge / research-provider / z.ai respectively); `GH_TOKEN` set;
  temporal connected (localhost:7233); board db; containment policy;
  notify routes.
- FAIL `gh` not on PATH — doctor's own note: benchmark runs have no remote
  and skip the PR step (merge/step.py:521); ignorable for this fleet.
- Warning git identity unset on host — merge commits carry the compose
  worker's GIT_AUTHOR/COMMITTER env; the C2 anchor warning does not apply
  to benchmark runs. Recorded.

### 3. Pools overlay + harness cap — FIXED DURING PRE-FLIGHT, then PASS

- Found: `docker compose ps` showed a single worker (`ai-sdlc`), the
  overlay services never started — the stack predates 024's overlay use.
- `docker compose -f docker-compose.yml -f docker-compose.pools.yml
  config -q` → PASS (config valid).
- One-time host fix: the `harness-sessions` volume lacked its subpath
  dirs (`mkdir -p /data/claude /data/opencode` via the worker image);
  then `up -d worker worker-harness` → both pools Up
  (`kroker-worker-1` core, `kroker-worker-harness-1` harness,
  `KROKER_HARNESS_CAP` default 2 from the overlay).

### 4. R7 — the worker image question — RESOLVED, then a STOP finding

- Found: the running image `ghcr.io/kit-kroker/kroker-worker:latest`
  (id `04df682a4560`) was built ~2026-11-11 — a baked copy predating
  round 025 entirely. That is the T020 stop-guard's literal condition.
- Fix applied (host-side, documented compose path): `up --build -d
  worker worker-harness` rebuilt the image from THIS checkout (build
  context `.`, target `runtime`; new image `e571e9941dae`, created at
  pre-flight). Verified in-container on BOTH pools:
  `python -c "import sdlc.benchmarks.operator_time as m;
  print(m.ENGAGEMENT_CAP_S)"` → `600` — a module that does not exist in
  the old image. The compose stack runs the checkout's code when built
  with `--build`; the running stack now does. R7 settled.
- **STOP FINDING (infra, FR-023):** the freshly built CORE worker
  crash-loops at boot: `ValueError: Activity paths_exist is not async so
  an activity_executor must be present` (worker.py Worker(...) passes no
  `activity_executor`; `paths_exist` is a sync `@activity.defn` added by
  023 FR-205, cbbf6f02 — after the last working image; no Worker anywhere
  in src or tests passes an executor, so no test boots this path — the
  H7 blind spot). The harness pool boots (its activity set excludes
  paths_exist). Without a core worker no workflow can run: **the fleet
  cannot start.** A code fix is required, which is tree-editing: per the
  fleet host rules it needs a fresh orchestrator go (and moves the fleet
  commit candidate). THE SEQUENCE STOPS HERE for the owner's ruling.

### 5. Credentials — PASS

`.env` (key names only, values not recorded): `ANTHROPIC_API_KEY` +
`ANTHROPIC_BASE_URL` (judge: `anthropic:claude-sonnet-5` per case.yaml), `EXA_API_KEY` (research provider: cat-cafe, todo-api),
`ZAI_API_KEY` (author arm), `GH_TOKEN`, `HINDSIGHT_API_LLM_*`,
`SDLC_MEMORY_*`.

### 6. `adversarial_review_enabled` — PASS (resolves False)

`PipelineConfig.adversarial_review_enabled: bool = False`
(core/models.py:465); no `SDLC_*ADVERSARIAL*` or config override in
`.env` or the environment; the agents/adversary registration stays off.

### 7. `SDLC_RUNS_ROOT` — PLAN, one action still required

Unset today; the fleet will use a fresh dedicated directory. **Required
before runs (host-side):** the worker container writes records to
`/app/runs` (named volume `worker-runs`) while the CLI scores from
`SDLC_RUNS_ROOT` on the host — they must be the SAME tree. Set
`KROKER_RUNS_BIND=<fleet runs dir>` in `.env` (docker-compose.yml
documents this switch), recreate the workers, and run the CLI with
`SDLC_RUNS_ROOT=<the same dir>`. To be executed together with the
post-ruling rebuild; evidenced in the T022/T023 updates of this file.

## Status

STOPPED at the T020 infra finding (core worker boot regression). No paid
run has started; no scored run exists; the tree at `b55773ff` is
untouched. Awaiting the orchestrator's ruling on the tree fix.

**Update (same day, after the ruling):** fresh go granted; the repair
landed as `26481ae3` (activity_executor at both Worker sites via
_build_workers, RED boot test first, battery 8059/2-pre-existing/0,
reviewer approve). Both pools rebuilt from the fixed checkout and verified
live by Temporal pollers: `core@…` workflows+activities on `ai-sdlc`,
`harness@…` activities on `ai-sdlc-harness`, restarts=0. The stop is
cleared.

## T021 — seeding (2026-11-16)

- Scratch repos live on the HOST at `/home/maksim/work/scratch-repos`
  (writable; `/srv` itself is root-owned) and reach the workers as
  `/srv/scratch-repos` via the per-machine
  `docker-compose.override.yml` (gitignored, the documented mechanism) —
  mounted into BOTH pools. Five repos seeded per the cat-cafe plan's
  protocol (a non-bare repo, single empty `init` commit on `main`):
  todo-api-greenfield, deveval-readtime, deveval-lice, deveval-geotext,
  cat-cafe-monitoring — all `mode: greenfield`.
- Runs root: `.env` gains `KROKER_RUNS_BIND=/home/maksim/work/
  kroker-fleet-runs-025` (fresh, empty, dedicated); the CLI side sets
  `SDLC_RUNS_ROOT` to the same path. Both workers recreated with the
  three-file compose; pollers re-verified.
- Reference-env deps (readtime needs beautifulsoup4/pyquery/markdown2/
  lxml; `network_required: false` so they must pre-exist; no provisioning
  path exists — reference_env is E-80/E-81 scope): installed into BOTH
  worker containers' venvs and the host venv. CAVEAT: container installs
  live in the writable layer — they survive restarts/reboots but NOT a
  recreate; no recreate is planned between the freeze and the last run
  (the commit freeze forbids rebuilds), and any unplanned recreate is an
  infra event anyway.
- `sdlc benchmark verify-case` results: deveval-readtime PASS,
  deveval-lice PASS, deveval-geotext PASS, cat-cafe-monitoring PASS.
  todo-api-greenfield FAIL is a tool-shape mismatch, not a seeding
  failure: verify-case runs an IMPORTED case's oracle against its
  `reference/`, and the hand-written smoke case has none — its validation
  is the smoke stamp itself (B.9, T023).
- **cat-cafe conditionality resolved POSITIVE**: scratch repo seeded and
  passing verify-case, research-provider key present (`EXA_API_KEY`).
  cat-cafe runs as planned (run 4); no lice repeat needed.
- opencode harness auth: no host auth.json exists to bind (the override
  example's optional bind); the workers carry `ZAI_API_KEY` via env_file.
  The smoke stamp is the proof this resolves; an auth failure there is
  infra-class.

## T022 — the freeze (2026-11-16)

- Dedicated checkout: `git worktree add ../kroker-fleet 93120693` —
  **fleet commit `93120693`** (`93120693f48c2599da23b86fe1d4647d1cabdfe0`,
  "T021: scratch repos seeded..."). `git -C ../kroker-fleet status
  --short` is empty. All runs dispatch from this checkout (provenance is
  stamped from the CLI's tree).
- Image rebuilt FROM the dedicated checkout
  (`docker build -f ../kroker-fleet/Dockerfile --target runtime`):
  `sha256:ad0b46f248a6`; both workers recreated onto it, restarts=0.
  In-container: `operator_time.ENGAGEMENT_CAP_S == 600` on both pools;
  readtime reference deps re-installed after the recreate (the T021
  caveat executed once, pre-smoke — no recreate remains between now and
  the last run).
- Pollers re-verified on the new containers: `core@…` activity+workflow
  on `ai-sdlc`; `harness@…` activity on `ai-sdlc-harness` (cap 2).
- `/srv/scratch-repos` (5 cases) and `/app/runs` (empty, the dedicated
  fleet root) confirmed inside both containers.
- **FREEZE ANNOUNCED: fleet commit `93120693`; no commit lands between
  the smoke stamp and the last scored run.**

## Infra stop #1 — smoke attempt 1 (2026-11-16, ~17:40 UTC)

Announced paid smoke (both arms, soft, fleet commit `93120693`) ran from
the frozen checkout. It completed dispatch — harness routing held
(`measure_code_axis` executed on the harness queue) — but the run died in
setup and the smoke verdict was FAIL on all four conditions
(`rubric_scores`, `commit_on_records`, `one_file_per_cell`,
`oracle_all_pass`). Failed stamp retained at
`../kroker-fleet/runs/ops/smoke/unknown.json` (cwd-relative ops root;
`runs/` is gitignored, the checkout stays clean). Run evidence kept and
labelled at `kroker-fleet-runs-025-evidence/infra-1-smoke-…` (quarantined
out of the runs root so `score --all` cannot ingest it). **Spend $0.00**
— no model or judge call ran.

Three independent defects, one run:

1. **git dubious ownership (infra, host/container)** —
   `setup_integration_branch` runs `git worktree add` as container root
   against `/srv/scratch-repos/todo-api-greenfield`, owned by host uid
   1000; git's `safe.directory` check refused (rc=128). Three retries,
   then the child `GraphWorkflow` failed at 3.4 s. Fix (non-tree):
   `GIT_CONFIG_COUNT/KEY/VALUE` `safe.directory` entries for the five
   repos via the gitignored compose override on both pools (git 2.47 in
   image; survives recreate), or an in-container `git config --global`
   (writable layer, recreate-fragile). Override env preferred.
2. **`kroker_commit: unknown` on every record (infra, image build)** —
   `resolve_provenance` falls back to the `KROKER_COMMIT` env when /app
   carries no `.git`; the runtime image was built without
   `--build-arg KROKER_COMMIT=<sha>` (Dockerfile:126-127), so the env is
   the literal `unknown` and `commit_on_records` can never pass. Fix
   (non-tree): rebuild the image from the fleet checkout WITH the
   build-arg.
3. **flash arm rejected at the boundary (case/registry config, needs a
   tree edit)** — todo-api's backward-compat arms assign
   dev/test/devops per `models:` entry while proposer roles keep the
   registry default; `agents/reviewer/agent.yaml` (and qa, merge_verdict,
   deep_review) default to `zai:glm-5.3-flash`, the same model id as the
   flash arm's dev → ADR-6 (loader `check_adr6_families`) correctly
   rejects the cell ("a judge must not run the weights it judges"). The
   glm-5.3 arm is unaffected (reviewer=flash ≠ dev=glm-5.3). With the
   flash cell rejected, `one_file_per_cell` (n_cells=2) can never pass —
   the smoke cannot pass at this commit, by design surfacing the
   collision. Candidate fixes (both tree edits → fleet restart at the new
   commit + fresh owner go, B.4 rule 3):
   (a) todo-api `case.yaml`: drop `zai-coding-plan/glm-5.3-flash` from
   `models:` — smoke matrix becomes the strong arm alone (scored runs are
   strong-arm only per B.3; the case has no separation object, so no
   acceptance/stale coupling; cheapest smoke);
   (b) add explicit `arms:` overriding `reviewer`/`qa`/`merge_verdict`
   to `zai-coding-plan/glm-5.3` for the flash arm — keeps both arms in
   the smoke at ~2× judge cost.

Classification per B.5: infra — "(a) no stage produced a valid artifact"
and "(b) a verifiable host error outside harness task execution"
(defect 1 killed the run; defects 2–3 would each have failed the smoke on
their own). The 13:11 casualty remains pre-smoke per the owner's ruling;
this is **infra stop 1 of 2** — a second infra stop ends the delegation.
Per FR-023 the sequence halts here; nothing below runs until the owner
clears it.

## Fleet restart — fix (a) applied under the owner's fresh go (2026-11-16)

- Tree fix `ce3a36f8` (reviewer: fixes-needed on `1da893fa` for one ruff
  I001 import-order nit → fixed → **approve** on the amend; amended rather
  than follow-up-committed so the fleet commit set stays exactly one):
  flash model dropped from the smoke case's `models:`; new RED-first test
  pins the matrix to one strong cell AND replays the boundary's exact
  judge-role map (`STAGE_MODELS` defaults over arm overrides →
  `validate_run_roles`); `test_todo_api_case_loads` updated to match.
  Battery in CI-equivalent env (routing vars blank): **the two known
  baseline failures only, nothing new**. Host-env caveat, disclosed to
  the reviewer: with this host's routing-enabled `.env` the full battery
  shows 43 PRE-EXISTING failures — verified identical with the diff
  stashed; 024's `require_harness_poller` guard reaches stale
  `_DummyClient` doubles missing `.namespace` in the run-gate tests, plus
  order-dependent maintenance/graph flakes; CI (no `.env`) sees none of
  them; 024 test debt, out of this round's authorized scope.
- Non-tree defect 1 fix: `docker-compose.override.yml` carries tight
  `GIT_CONFIG_COUNT/KEY/VALUE` `safe.directory` entries for the five
  repos on BOTH pools (survives recreate; no writable-layer fragility).
  Pre-proofed in-container before and after the recreate: `worktree add`
  as container root, git ops inside the linked worktree, clean removal —
  the per-repo entry is sufficient, no wildcard needed.
- Non-tree defect 2 fix: image rebuilt FROM the fleet checkout WITH
  `--build-arg KROKER_COMMIT=ce3a36f88d08e54892e8a72c96ceb6165ba4bc13`
  → `sha256:c939ff6bc5e6…`; both workers recreated (restarts=0); readtime
  deps re-provisioned post-recreate.
- Verified in-container on BOTH pools: `KROKER_COMMIT` env = full sha;
  `resolve_provenance()` returns the sha (pre-proof of
  `commit_on_records`); `ENGAGEMENT_CAP_S=600`; deps import;
  `expand_matrix(smoke_case)` = exactly 1 strong cell (pre-proof of the
  corrected `one_file_per_cell`); pollers re-verified (ACT-type probe:
  `core`→`ai-sdlc`, `harness`→`ai-sdlc-harness`).
- **FLEET RESTARTED at commit `ce3a36f8`.** The worktree `../kroker-fleet`
  moved to it; status clean; `.env` + `runs/` are untracked survivors and
  `.dockerignore` excludes both from the image build. Quarantines
  unchanged: the 13:11 casualty and infra-1 stay in
  `kroker-fleet-runs-025-evidence/`, unscored, outside the runs root.

## Infra stop #2 — smoke attempt 2 concluded (2026-11-17 ~00:39–01:39 UTC)

The run executed end-to-end under the attendant (research gate approved
by the operator at 21:0xZ; 8 clarify answers + architecture + plan gates
+ T-01..T-05 task-escalation approvals by the automated attendant;
parent closed 00:39Z; server-side finalize wrote 54 records + reports at
01:39Z). **True conditions over the real records** (re-evaluated with
`SDLC_BENCHMARKS_ROOT` pointing at the runs root): rubric_scores PASS
(clarify 0.955 / architecture 0.95, `staged_rubric`), commit_on_records
PASS (every record carries `ce3a36f88d08…`), one_file_per_cell PASS
(1/1) — all three restart fixes verified in production.
**oracle_all_pass FAIL** (case-level oracle graded the produced code
0.0). Measured judge cost: **$0.45976** ($0.0356938 + $0.42406664) —
the T024 input for whenever a passing smoke exists.

**Root cause of the oracle fail — harness credential gap (infra):**
every one of the 15 opencode invocations (3 attempts × 5 dev tasks)
exited **1 at 2.2–2.3 s with zero input/output tokens and empty stderr**
— the CLI died at provider resolution; no model turn ever ran.
`harness/base.py` `ENV_ALLOWLIST` deliberately forwards only toolchain
vars, and `provider_env()` injects only `ANTHROPIC_*` — the design
expects opencode to authenticate from **its own auth.json**
(`docker-compose.override.example.yml` documents binding a host
`~/.local/share/opencode/auth.json`). This host has no auth.json (T021
finding) and the env-file `ZAI_API_KEY` route cannot reach the child
through the curated environment. The T021 pre-flight pre-registered
exactly this: "an auth failure there is infra-class." Classification
per B.5: infra — credential failure in the harness runtime, outside
task execution (nothing executed). **Infra stop 2 of 2 — the delegation
ends here; no further run starts without a fresh owner go.**

Evidence hygiene:
- The attendant's finalize had its own bug (it read the records root via
  `_root()` without `SDLC_BENCHMARKS_ROOT` set → 0 records → a bogus
  all-four-FAIL stamp at `runs/ops/smoke/unknown.json`). Disclosed; the
  faithful stamp is `runs/ops/smoke/ce3a36f88d08….json`
  (`passed=false, failed_conditions=[oracle_all_pass]`), written with the
  same `write_stamp` code over the real records. Both files retained.
- The run dir is quarantined unscored at
  `kroker-fleet-runs-025-evidence/infra-2-smoke-…` (B.5: kept, labelled,
  listed apart). Runs root is empty again.
- Attendant ledger (full disclosure): 16 interactions total — 1 human
  (research gate), 15 automated (8 clarify with suggested answers,
  architecture r1, plan r1, T-01..T-05 task-escalation approvals). The
  five escalation approvals approved work the harness never did — with a
  working harness those escalations would not exist; the history stands
  as recorded.

**Staged fix for the owner's fresh go (non-tree):** generate a host
`~/.local/share/opencode/auth.json` from the existing `ZAI_API_KEY`
(opencode api-key format `{"zai": {"type": "api", "key": …}}`) or run
`opencode auth login`; bind it read-only into BOTH pools via the
gitignored override per the documented example; recreate; prove auth
in-container (one `opencode run` probe or the smoke itself); rerun the
smoke (announced). No tree edit; fleet commit stays `ce3a36f8`.

## Owner fresh go — auth fix applied (2026-11-17 ~23:00Z)

New tripwire (replaces the two-stop budget, which is spent): ANY further
infra stop, whatever the count, halts everything and reports to the
owner before another cent.

- Host `~/.local/share/opencode/auth.json` generated from `.env`'s
  `ZAI_API_KEY` (entries for both `zai` and `zai-coding-plan`; mode 600)
  and bound **read-only into both pools** via the override — the exact
  documented mechanism (`docker-compose.override.example.yml`). HOME is
  on the harness env allowlist, so the curated child resolves
  `/root/.local/share/opencode/auth.json`.
- Containers recreated (the stack had bounced with the host minutes
  earlier; temporal restarted too). Readtime deps re-provisioned
  post-recreate.
- **Auth proven by a real API round-trip** inside the harness container,
  same invocation shape the harness uses (`opencode run … --pure --auto
  --format json -m zai-coding-plan/glm-5.3`): model replied, tokens
  input=267/output=3, cost $0 (flat subscription). Not just file
  presence.
- Post-recreate verification battery, all green on BOTH pools: image
  `sha256:c939ff6bc5e6` (the `ce3a36f8` build), restarts=0;
  `KROKER_COMMIT=ce3a36f88d08…` and `GIT_CONFIG_COUNT=5` baked;
  `ENGAGEMENT_CAP_S=600`; deps import; `resolve_provenance()` returns
  the fleet commit; smoke matrix = 1 strong cell; ACT-type pollers
  `core`→`ai-sdlc`, `harness`→`ai-sdlc-harness`; no running workflows
  (clean slate after the bounce).
- Attendant v3: auto-discovers the new bench id (no hardcoded id);
  handles all four PendingDecision kinds; its finalize now reads records
  via `SDLC_BENCHMARKS_ROOT` (set in every launch env — the CLI's own
  post-processing too; that env gap caused the bogus attempt-2 stamp).
- Smoke attempt 3 announced and launched below; fleet commit unchanged
  `ce3a36f8`.


