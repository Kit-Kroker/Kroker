# ai-sdlc-temporal

Idea → deployed feature pipeline. Temporal orchestrates; Pydantic AI agents
think (clarify, architect, plan, QA, quality gate, devops); coding harnesses
do (`claude -p`, `opencode run`) inside isolated git worktrees.

## Roles
Governed by the versioned registry in `agents/` (`agents/registry.yaml` +
one `agents/<role>/` folder per role) and validated at worker boot
(`src/sdlc/agents/loader.py`) — 3 harness + 8 required proposer + 4 optional
proposer roles.

| Role | Kind | Runs as |
|---|---|---|
| clarify | Pydantic AI (TemporalAgent) | activity via TemporalAgent |
| architect | Pydantic AI | activity via TemporalAgent |
| planner | Pydantic AI | activity via TemporalAgent |
| dev / test / devops executor | coding harness | long-running heartbeating activity in a git worktree |
| qa analyst | Pydantic AI + test-suite activity | activities |
| quality gate | `DeterministicQualityGate` (pure code) + advisory `MergeVerdict` (Pydantic AI, soft-gate only) | `evaluate_gate` activity + TemporalAgent |
| reviewer | coding harness (different model/harness than dev) | activity |
| analyst | Pydantic AI, clean-context | activity via TemporalAgent |
| research *(optional, `research_enabled`)* | Pydantic AI, fans out (`plan_research` → `research_subquestion` × N → `synthesize_brief`) | activities; provider `fake` (CI) / `tavily` / `exa` (ExaSearch + Harness `run_code`, needs `EXA_API_KEY`) |
| deep_review *(optional, `deep_review_enabled`)* | Pydantic AI, reads the scrubbed harness transcript | activity via TemporalAgent, advisory only |
| handoff *(optional, `handoff_enabled`, FR-805)* | Pydantic AI, extracts task→task claims from the scrubbed session | activity via TemporalAgent, best-effort |
| adversary *(optional, `adversarial_review_enabled`)* | Pydantic AI, decorrelated second opinion (different model identity than dev+reviewer) on the approving path | activity via TemporalAgent, advisory, fail-open |

## Human-in-the-loop
Gates: clarify, architecture, plan, merge, deploy — each `hard` / `soft` /
`off` per project (`PipelineConfig.gates`). Humans interact through signals:

```
python -m sdlc.cli start --title "Add SSO" --mode brownfield --repo git@...
python -m sdlc.cli status  --id feature-add-sso
python -m sdlc.cli answer  --id feature-add-sso --q Q1 --text "Use OIDC"
python -m sdlc.cli approve --id feature-add-sso --gate architecture
python -m sdlc.cli benchmark --case cat-cafe   # run the eval harness (see docs/BENCHMARK.md)
```

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
**Local:**
1. `temporal server start-dev`
2. `pip install -e .` then `python -m sdlc.worker`
3. `python -m sdlc.cli start ...`

**Docker Compose** (`docker-compose.yml`): brings up Temporal, a real
[Hindsight](https://github.com/vectorize-io/hindsight) memory backend, and the
worker together, all reading secrets from `.env` (`env_file:`) — copy
`.env.example` to `.env` first. The worker image installs the `logfire` extra
so `logfire_setup.configure()` doesn't crash-loop on a missing module when
`LOGFIRE_TOKEN` is set. `docker compose up`.

**Agent board API.** Optional, read-mostly service over the board the pipeline
writes as it runs (`$SDLC_BOARD_DB`, default `runs/board.sqlite3`):

```bash
uvicorn interfaces.dashboard.api.main:app --host 127.0.0.1 --port 8500
```

`GET /projects/{p}` for artifacts + task rollup, `/artifacts/{key}` for version
lineage, `/tasks?status=`, `/events` for the change log, `/stats` for board
counters. Agents claim work with `POST /projects/{p}/tasks/{id}/claim` and an
`If-Match: <row_version>` header. **Bind to localhost** — there is no auth yet,
and the `X-Actor` header identifying a writer is self-asserted (ROADMAP OQ-11).

**Deploy (stage 13).** Off by default. Enable per project with
`PipelineConfig.deploy` — `adapter: compose` (reference) or `script`
(`make deploy` / `make rollback` / `make version`). The stage applies a
frozen `DeployPlan`, runs its smoke checks, and auto-rolls-back on any check
that is not `passed`, then opens a `deploy_failed` gate. A check that could
not be evaluated is `errored` and never counts as a pass.

## Develop
- `pip install -e .[dev]` then `python -m pytest` (needs `git` on PATH).
- Importing the workflow/agents currently requires `ANTHROPIC_API_KEY` /
  `OPENAI_API_KEY` / `EXA_API_KEY` set (agents are constructed at import,
  including the shipped research role's `provider: exa` ExaSearch client);
  `tests/conftest.py` sets dummy values for import-only, so `pytest` needs no
  real keys.
- Added a new module and hit `ModuleNotFoundError`? Re-run `pip install -e .`
  (setuptools' editable wheel doesn't auto-discover new files).
- See [`docs/foundation.md`](docs/foundation.md) for the contracts, activities,
  and the deterministic gate, and
  [`docs/architecture-review-2026-07.md`](docs/architecture-review-2026-07.md)
  for the design decisions and implementation status.
- See [`docs/BENCHMARK.md`](docs/BENCHMARK.md) for the benchmark & evaluation design — the four measurement axes (harness / model×role / memory / case), how success criteria SC-1..6 get their numbers, and the E-30…E-37 increments.
- Self-contained schema docs (no build step, open directly in a browser),
  each checked against actual code:
  [`docs/roadmap.html`](docs/roadmap.html) (every FR/NFR/SC/US/ADR + the
  15-stage DAG vs code), [`docs/architecture-schema.html`](docs/architecture-schema.html),
  [`docs/agents-schema.html`](docs/agents-schema.html) (registry lifecycle,
  every role, ADR-6/adversary model-inequality checks),
  [`docs/research-stage-schema.html`](docs/research-stage-schema.html) (the
  research fan-out stage, provider seam, ExaSearch wiring),
  [`docs/benchmark.html`](docs/benchmark.html) /
  [`docs/benchmark-analysis.html`](docs/benchmark-analysis.html).

## Notes
- Payloads through Temporal stay small (claim-check for specs/diffs/logs).
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
