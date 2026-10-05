# Kroker

Idea → deployed feature pipeline. Temporal orchestrates; Pydantic AI agents
think (clarify, architect, plan, QA, quality gate, devops); coding harnesses
do (`claude -p`, `opencode run`) inside isolated git worktrees.

> **Alpha — your own repositories only, localhost only.** The pipeline
> executes the target repository's code (dependency installs, builds, tests)
> as the user the worker runs as, with that user's network access and
> credentials. A git worktree is not a sandbox. There is no authentication,
> no tenant isolation and no network egress control. Do not point it at a
> repository you do not trust, and do not expose its ports beyond loopback.
> The threat model and how to report a vulnerability are in
> [`SECURITY.md`](SECURITY.md).

## Roles
Governed by the versioned registry in `agents/` (`agents/registry.yaml` +
one `agents/<role>/` folder per role) and validated at worker boot
(`src/sdlc/agents/loader.py`) — 3 harness + 8 required proposer + 4 optional
proposer roles.

| Role | Kind | Runs as |
|---|---|---|
| clarify | Pydantic AI | activity via TemporalDurability |
| architect | Pydantic AI | activity via TemporalDurability |
| planner | Pydantic AI | activity via TemporalDurability |
| dev / test / devops executor | coding harness | long-running heartbeating activity in a git worktree |
| qa analyst | Pydantic AI + test-suite activity | activities |
| quality gate | `DeterministicQualityGate` (pure code) + advisory `MergeVerdict` (Pydantic AI, soft-gate only) | `evaluate_gate` activity + TemporalDurability |
| reviewer | coding harness (different model/harness than dev) | activity |
| analyst | Pydantic AI, clean-context | activity via TemporalDurability |
| research *(optional, `research_enabled`)* | Pydantic AI, fans out (`plan_research` → `research_subquestion` × N → `synthesize_brief`) | activities; provider `fake` (CI) / `tavily` / `exa` (ExaSearch + Harness `run_code`, needs `EXA_API_KEY`) |
| deep_review *(optional, `deep_review_enabled`)* | Pydantic AI, reads the scrubbed harness transcript | activity via TemporalDurability, advisory only |
| handoff *(optional, `handoff_enabled`, FR-805)* | Pydantic AI, extracts task→task claims from the scrubbed session | activity via TemporalDurability, best-effort |
| adversary *(optional, `adversarial_review_enabled`)* | Pydantic AI, decorrelated second opinion (different model identity than dev+reviewer) on the approving path | activity via TemporalDurability, advisory, fail-open |

## Human-in-the-loop
Gates: clarify, architecture, plan, merge, deploy — each `hard` / `soft` /
`off` per project (`PipelineConfig.gates`). Humans interact through signals:

```
python -m sdlc.cli start --title "Add SSO" --mode brownfield --repo git@...
python -m sdlc.cli status  --id feature-add-sso
python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
python -m sdlc.cli approve --id feature-add-sso --gate architecture
python -m sdlc.cli benchmark --case cat-cafe   # run the eval harness (see BENCHMARK.md)
python -m sdlc.cli doctor            # diagnose this environment's setup
python -m sdlc.cli doctor --json     # the same results, for machines
python -m sdlc.cli doctor --strict   # exit non-zero on warnings too
```

> Run it before the first `start` on a new machine, and whenever a run fails in a way that smells like configuration. It reports every finding at once rather than dying on the first, and it writes nothing.
>
> Notification routes in `policy/notifications.yaml` may take `$VAR` targets (for example `webhook:$SDLC_NOTIFY_WEBHOOK`). A route whose variable is unset or empty is dropped, not sent to the literal string; the loader logs one WARNING per dropped route, and doctor's `notify routes` check lists each unset target as a WARN.


Scoring stored benchmark runs needs no running Temporal (it reads records on disk):

```
# score everything on disk (seconds, no Temporal needed)
python -m sdlc.cli benchmark score --all

# one matrix run, re-weighted
python -m sdlc.cli benchmark score --bench <bench_run_id> --weights 0.7,0.2,0.1

# one case across its whole history
python -m sdlc.cli benchmark score --case cat-cafe-monitoring
```

## Run

### Quickstart (Docker Compose)

The supported environment is the container: the worker image carries
Python 3.13, the pinned `opencode` and `claude` CLIs, `gh` and `git`, and
`docker-compose.yml` puts Temporal and a
[Hindsight](https://github.com/vectorize-io/hindsight) memory backend next
to it. You need Docker and the accounts below; nothing else is installed on
the host.

**See it run first — one command, no keys.** A dry run of the whole
pipeline with scripted agents and activities:

```bash
git clone https://github.com/Kit-Kroker/Kroker.git && cd Kroker
docker compose run --rm demo
```

That builds the image (a few minutes the first time), starts Temporal and
runs the real workflow from intake to deploy in about fifteen seconds. It
stops at each human gate, prints the command a real run would wait for, and
answers it itself. Nothing calls a model, runs a coding CLI or touches a
repository, so it needs no `.env`, no account and no login — and it proves
only the orchestration, not your keys. Without Docker:
`python -m sdlc.demo` against any reachable Temporal.

**Then a real run.**

```bash
cp .env.example .env                                   # then fill in the keys
cp docker-compose.override.example.yml docker-compose.override.yml   # then edit the paths
docker compose up -d --build
docker compose exec worker python -m sdlc.cli doctor   # every line should PASS
```

What you have to bring:

| What | Where it goes | Needed for |
|---|---|---|
| z.ai key | `ZAI_API_KEY`, `ANTHROPIC_API_KEY` in `.env` | every proposer role; the worker does not start without them |
| Exa key | `EXA_API_KEY` in `.env` | the research role; the worker does not start without it, even if no run uses research |
| An LLM key for Hindsight | `HINDSIGHT_API_LLM_API_KEY` in `.env` | the memory backend container |
| An `opencode` login | `opencode auth login` on the host, mounted through `docker-compose.override.yml` | the coding roles (`dev`, `test`, `devops`) |
| A repository to work on | a host directory mounted through `docker-compose.override.yml` | any run |
| GitHub token, `repo` scope | `GH_TOKEN` in `.env` | only the last step of a run against a GitHub repository (push + pull request) |

`doctor` checks the provider keys, `GH_TOKEN`, the CLIs, the git identity
and the Temporal connection, and reports every problem at once. It does not
check the Hindsight key, the `opencode` login or your mounts. Then start a
run and answer its gates:

```bash
docker compose exec worker python -m sdlc.cli start \
    --title "Add a health endpoint" --mode brownfield --repo /srv/scratch-repos/<your-repo>
docker compose exec worker python -m sdlc.cli inbox
```

A real run spends tokens from the first stage; the dry run above is the
only mode that does not. Read [`SECURITY.md`](SECURITY.md) before pointing
it at a repository: the pipeline executes that repository's build and tests
with the worker's environment.

**Published image.** Each `v*` tag publishes
`ghcr.io/kit-kroker/kroker-worker:<version>` (and `latest`) from the same
Dockerfile target, so from the first release after `v0.0.1` you can
`docker compose pull worker` and drop `--build`. Set `KROKER_IMAGE_TAG` to
pin a version.

### Without Docker

For working on Kroker itself rather than running it. Requires Python 3.13
and, on `PATH`, `git`, `gh`, the Temporal CLI and the `opencode` and
`claude` CLIs at the versions the Dockerfile pins.

1. `temporal server start-dev`
2. `uv sync --frozen --extra dev` (or `pip install -e ".[dev]"`), copy
   `.env.example` to `.env`, then `python -m sdlc.worker`
3. `python -m sdlc.cli doctor`, then `python -m sdlc.cli start ...`

The repository also ships a dev container (`.devcontainer/`) built from the
same Dockerfile.

**Agent board API.** Optional, read-mostly service over the board the pipeline
writes as it runs (`$SDLC_BOARD_DB`, default `runs/board.sqlite3`):

```bash
uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500
```

`GET /projects/{p}` for artifacts + task rollup, `/artifacts/{key}` for version
lineage, `/tasks?status=`, `/events` for the change log, `/stats` for board
counters. Agents claim work with `POST /projects/{p}/tasks/{id}/claim` and an
`If-Match: <row_version>` header.

For humans rather than agents, `/artifacts/{key}/current/markdown` and
`/artifacts/{key}/versions/{id}/markdown` render `requirements`,
`architecture` and `plan` as Markdown generated from the stored typed
artifact — the same data the JSON routes serve, readable without a
dashboard. An artifact that no longer matches its model returns 422 rather
than a partial render; the JSON route stays available as the escape hatch.

**Dashboard.** The same process mounts the operator console's API under
`/api` (live run state read from Temporal) next to the board routes. The
Vue frontend in `interfaces/dashboard/frontend/` is built from the
`@kroker/ui` design system (`interfaces/ui/`) and organised by screen: the
fleet, the run page, the graph editor, and the decision inbox. The inbox
lists everything waiting on a person across runs and lets the operator
answer questions, decide gates, override or send back a merge, and retry
or quarantine an escalated task.
The run page is a tab host — Graph | Board | Gates | Cost, with Gates and
Cost not built yet. The tab is kept in the URL (`#/runs/<id>?tab=board`).
The Board tab is a read-only view of the run's tasks, their evidence and
event timeline, and the artifact versions the run published. It reads the
`/projects/*` routes above, keyed by the run's `project_key`. A run with no
project, or a project with no board, shows a banner instead. The screen
map and import rules are in [`interfaces/AGENTS.md`](interfaces/AGENTS.md).

```bash
cd interfaces/dashboard/frontend
npm run dev                  # proxies /api and /projects to 127.0.0.1:8500
VITE_API=mock npm run dev    # in-memory data, no backend needed
```

Checks never call `npm` directly: `python scripts/check_ui.py` runs
install, typecheck, both Vitest suites and both Playwright tiers.

**Bind to localhost** — there is no auth yet, and the `X-Actor` header
identifying a writer is self-asserted (OQ-11,
[`docs/roadmap/pipeline-as-data.md`](docs/roadmap/pipeline-as-data.md)).
The dashboard sends no `X-Actor`, so a decision taken there is recorded as
`human:unknown`; closing that is PRD FR-1004.
Anyone who can reach the port can start a run and answer its gates, the
merge gate included. The Markdown URLs are designed to be pasted into a chat
or a ticket, which makes this easier to forget: pasting one shares a link
that only works inside the trusted network, and anyone who reaches that
network can read it. See [`SECURITY.md`](SECURITY.md).

**Deploy (stage 13).** Off by default. Enable per project with
`PipelineConfig.deploy` — `adapter: compose` (reference) or `script`
(`make deploy` / `make rollback` / `make version`). The stage applies a
frozen `DeployPlan`, runs its smoke checks, and auto-rolls-back on any check
that is not `passed`, then opens a `deploy_failed` gate. A check that could
not be evaluated is `errored` and never counts as a pass.

## Develop
- `uv sync --frozen --extra dev` (or `pip install -e ".[dev]"`) then
  `python -m pytest`. Python 3.13; needs `git` on PATH.
- Importing the workflow/agents currently requires `ANTHROPIC_API_KEY` /
  `OPENAI_API_KEY` / `EXA_API_KEY` / `ZAI_API_KEY` set (agents are
  constructed at import, including the shipped research role's
  `provider: exa` ExaSearch client, and the glm proposer roles resolve
  `zai:glm-5.3` models); `tests/conftest.py` sets dummy values for
  import-only, so `pytest` needs no real keys.
- Added a new module and hit `ModuleNotFoundError`? Re-run `pip install -e .`
  (setuptools' editable wheel doesn't auto-discover new files).
- Prompt changes are gated (E-82):
  `SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval` A/B-scores each changed
  `agents/<role>/instructions.md` against its committed baseline via promptfoo
  (`pip install -e .[eval]`; needs Node ≥ 22.22; spends tokens). Deterministic
  checks — output validates as the role's `output_type`, per-case rubric
  **vetoes** (`benchmarks/cases/<case>/vetoes-*.yaml`), cost/latency budgets —
  are absolute and gate; the cross-family judge is staged (rubric → evaluation
  steps → score) and advisory, failing only on a regression past a noise-aware
  floor. Sensitivity is proven by the mutation suite:
  `SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval -k mutations`. Ad hoc:
  `python -m sdlc.cli eval clarify --case add-login-greenfield --gate`. Results land in `runs/prompt_evals/` and
  join the benchmark record stream by `prompt_sha` **only** — they are never
  merged into the heatmap, matrices, or SC rollup.
- See [`docs/reference/foundation.md`](docs/reference/foundation.md) for the contracts, activities,
  and the deterministic gate, and
  [`docs/reference/architecture-review-2026-07.md`](docs/reference/architecture-review-2026-07.md)
  for the design decisions and implementation status.
- See [`BENCHMARK.md`](BENCHMARK.md) for the benchmark & evaluation design — the four measurement axes (harness / model×role / memory / case), how success criteria SC-1..6 get their numbers, and the E-30…E-37 increments.
- Generated documentation site — built from the living sources on every push
  (`mkdocs build --strict` in CI, published to GitHub Pages at
  https://kit-kroker.github.io/Kroker/). Local preview: `pip install -e ".[docs]"`
  then `mkdocs serve`. Nothing on it is hand-maintained.

## Notes
- Payloads through Temporal stay small (claim-check for specs/diffs/logs). Proposer prompts are also guarded at runtime: a payload over 1 MiB raises the non-retryable `ProposerPayloadTooLarge` before the activity is scheduled (see ARCHITECTURE.md §11).
- Agent names / toolset ids are activity names — never rename in prod.
- Harness sessions are resumed across fix-loop attempts (claude `--resume`,
  opencode `-s`), so the fixer keeps its context.
- Every harness run also emits a **canonical `HarnessSession`** — a
  normalised, scrubbed, claim-checked transcript (ADR-16) — so *how* a diff
  was reached is a first-class signal, not just the diff. The default
  reviewer never reads it; the opt-in `deep_review` lens does (ADR-6).
- The **agent board** (ADR-21) persists what only Temporal history used to
  hold: `requirements` / `architecture` / `plan` versioned per project with
  lineage, plus task status and an append-only change log. Two status columns —
  the workflow writes `authoritative_status`, agents may only move the live
  `status`. Stats and scoring read the former, so a confused agent corrupts the
  live view and nothing else, and replay stays the source of truth.
- Cross-harness review: configure `roles["reviewer"]` with a different
  harness/model family than `roles["dev"]`.
- Per-run model overrides: `--role-model role=model` (repeatable). Harness
  roles (`dev`, `test`, `devops`) take their own grammar verbatim
  (e.g. `--role-model dev=zai-coding-plan/glm-5.2`); a **proposer** role's
  override must be a `provider:model` id the installed framework can
  construct (e.g. `--role-model architect=openai:gpt-5.2`) and is validated
  offline at submission — an invalid string exits non-zero before any
  workflow starts, naming the role, the string and the accepted form.
  E2 (005): the glm proposers run on z.ai's **coding** endpoint, where a
  `zai:glm-5.2` request is answered by glm-5.3 — name the model you mean;
  the served model follows the endpoint.
- Upgrading across the 005 route cutover: an open run's remaining stages
  resolve roles from the registry at execution time, so they run on the new
  route (`zai:glm-5.3`) while completed stages replay from history — drain
  open runs before upgrading, or accept a mixed-route run (plan D6).
- Harness is a config axis, not a fork: `claude -p` and `opencode run` are
  registry entries (`HARNESSES`), so a third adapter (e.g. `cursor`) drops in
  once it normalises into `HarnessRunResult`. The benchmark sweeps this axis.
- Hard gates that time out notify (log/webhook adapters) on reminder,
  escalation, and expiry timers rather than silently auto-rejecting (FR-303);
  a green run holds for a human rather than being discarded.
- A decorrelated **adversary** lens (`agents/adversary/`) runs only on the
  approving path as a non-DAG, fail-open second opinion — decorrelated by
  model *identity* (`model_id()`), not provider prefix, so two prefixes over
  the same weights don't count as independent. Off by default.
- Every terminal run emits a `RunSummary` (retro stage) and exports
  `events.jsonl` / `report.html` / `summary.json`; `sdlc benchmark score`
  aggregates across runs into the SC-rollup + heatmap/task/error/waste
  matrices, plus an `agreement_matrix` for the adversary lens.
- Memory (Hindsight) defaults to a fake in-process backend; the real client
  (`memory/hindsight_client.py`) talks to a live Hindsight container (see
  Docker Compose above).

## License
Apache License 2.0 — see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Contributing:
[`CONTRIBUTING.md`](CONTRIBUTING.md). Changes: [`CHANGELOG.md`](CHANGELOG.md).
