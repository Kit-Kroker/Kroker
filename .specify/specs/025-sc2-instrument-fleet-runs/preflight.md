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


