# AGENTS.md

Instructions for coding agents (Codex, Cursor, Copilot, or any generic
assistant editing this repo). Claude Code should read `CLAUDE.md` instead if
one exists; this file is the tool-agnostic equivalent.

## What this repo is

`ai-sdlc-temporal` is an idea → deployed feature pipeline. A Temporal
workflow (`FactoryWorkflow`) deterministically orchestrates a fixed 15-stage
DAG; Pydantic AI agents *think* — they emit schema-validated artifacts
(requirements, architecture, plans, reviews) and never touch tools directly;
coding harnesses (`claude -p`, `opencode run`) *do the work*, but only inside
sandboxed, per-task git worktrees, and only their diff is admitted back as an
artifact. Humans hold configurable gates (clarify / architecture / plan /
merge / deploy) along the way. See `ARCHITECTURE.md` §1–2 for the full
picture and the two rules that shape everything (models never act outside a
sandbox; memory is I/O).

## Build / install

```bash
pip install -e ".[dev]"
```

Requires Python >= 3.11 and `git` on PATH. Editable installs don't
auto-discover newly added modules — re-run `pip install -e .` after adding a
new file if you hit `ModuleNotFoundError`.

## Test

```bash
pytest
```

The default run is the **fast unit tier only** — `pyproject.toml`
(`[tool.pytest.ini_options]`) excludes several opt-in marker groups by
default. Enable them explicitly when relevant to your change:

| Marker | What it needs | Run with |
|---|---|---|
| `slow` | builds a venv / real pip installs, >10s | `pytest -m slow` |
| `temporal` | spawns an ephemeral Temporal dev-server per test | `pytest -m temporal` |
| `live` | spawns a real harness CLI, spends tokens | `SDLC_LIVE_TESTS=1 pytest -m live` |
| `prompt_eval` | A/B-scores a role prompt via promptfoo, spends tokens | `SDLC_PROMPT_EVAL=1 pytest -m prompt_eval` |
| `docker` | needs a running Docker daemon | `pytest -m docker` |
| `crew` | needs a real coding CLI on PATH, drives one crew round | `pytest -m crew` |

`pytest -m "slow or temporal"` runs everything except the token-spending /
Node-dependent tiers. `pytest -m ""` overrides `addopts` and runs truly
everything. `tests/conftest.py` sets dummy API keys for import-only, so
plain `pytest` needs no real credentials.

## Lint / format / typecheck

```bash
ruff check .
ruff format .
mypy
```

Config lives in `pyproject.toml` under `[tool.ruff]` / `[tool.ruff.lint]` /
`[tool.mypy]`. These are being wired into `.pre-commit-config.yaml` as
pre-commit hooks — check that file for the current enforced set before
assuming a check is mandatory in CI.

## `agents/` vs `AGENTS.md` — do not confuse these

The `agents/` directory at repo root (`agents/registry.yaml` plus one
`agents/<role>/` folder per role — `architect`, `dev`, `qa`, `reviewer`,
`planner`, etc.) is a **product concept**: it's the crew's own versioned
role registry, loaded by the Temporal worker at boot
(`src/sdlc/agents/loader.py`) to configure the pipeline's proposer agents and
harness roles. It is data the running system consumes, not instructions for
you.

**This file, `AGENTS.md`, is the opposite** — conventions for whatever
coding assistant is editing the *repository itself*. Don't edit
`agents/<role>/instructions.md` files expecting them to change how you (the
assistant) behave, and don't treat this file as part of the product's agent
registry.

## Git worktrees are the norm here

The pipeline's own code-stage runs each task in an isolated git worktree +
branch (ADR-14, "integration by running branch" — see `ARCHITECTURE.md`
§3/§13). If you are an agent working in this repo, expect to find yourself
already inside a worktree (e.g. under a path like
`.herdr/worktrees/<repo>/<branch>/`) rather than the primary checkout, and
expect other concurrent worktrees to exist for other tasks/features. Don't
assume you're at the canonical repo root; don't assume you're the only
active worktree.

## How this repo is cut

Cut along the seams of the process — a stage is the unit of agent work, not
technical layers or domain entities. The seam test is the common closure
principle: things that change together live together.

The pipeline uses vertical slices under `src/sdlc/stages/<stage>/`.
Horizontal packages (`harness/`, `board/`, `channels/`, `memory/`,
`observability/`, `artifacts/`) serve generic subdomains and are deliberately
not forced into the stage shape. Non-pipeline domains cut recursively into
phases of their own process (`assessment` → scan / discover / risk / gates).

Two binding rules govern slices:
- **Cross-stage calls are banned**; the orchestrator (`FeatureWorkflow`) is the
  sole coordinator. Importing a *type* another stage produces is not a call.
- **The producer owns its artifacts.** A stage's `models.py` holds what it
  produces; `core/` holds only what no stage produces — configuration and
  envelopes (`PipelineConfig`, `GateDecision`, `RoleConfig`, `IdeaBrief`).

See [`docs/framework.md`](docs/framework.md) for the seam contract and
`docs/superpowers/specs/2026-09-02-b0-module-shape-and-docs-architecture-design.md`
for the architectural rationale.

## File size

One hard ceiling: **1000 physical lines per file**. No soft target, no waiver.
Size is governed by the process seam; the ceiling is a tripwire against
monsters, not a design guide.

`.file-size-baseline.json` records pre-existing oversized files. Baselined
files may shrink, never grow; entries delete themselves automatically once a
file drops under 1000 lines. The ceiling covers authored code and living
documentation (`src/`, `tests/`, `scripts/`, `interfaces/`, `agents/`,
`crew/`, `blueprints/`, `policy/`, `docs/`, root `*.md`). Historical records
(`docs/superpowers/`), verbatim exports (`records/`), vendored data
(`benchmarks/`, fixture schemas), and generated artifacts are exempt.
`scripts/check_file_size.py` is the authority.

## Who may change what

- **The sandbox boundary.** Orchestrator agents working in the primary checkout
  may edit specs, stage contracts, and schemas. Sandboxed coding harnesses
  (`claude -p`, `opencode run` inside a per-task worktree) may modify only
  code and tests, and may never edit `<stage>.md` contracts or root specs.
  Reason: when Kroker runs against Kroker, a harness is editing this repo, and
  a harness that can rewrite the contract it is judged against has no contract.
- **The artifact boundary.** Whoever changes a stage's behaviour must update
  its clauses in the same diff. A clause without code and code without a clause
  are both defects.

## Where each stage lives

> Migration is piecemeal. **This table is the authoritative map** while it is in progress: look a stage up here rather than searching two locations. Updating it is part of moving a stage, not a follow-up.

| Stage | Lives in | Status |
|---|---|---|
| intake | `src/sdlc/stages/intake/` | migrated |
| context (brownfield) | `src/sdlc/workflows/feature.py` | types moved, step pending |
| research | `src/sdlc/stages/research/` | migrated |
| clarify | `src/sdlc/stages/clarify/` | migrated |
| architecture | `src/sdlc/workflows/feature.py` | types moved, step pending |
| plan | `src/sdlc/workflows/feature.py` | types moved, step pending |
| code | `src/sdlc/workflows/feature.py` | types moved, step pending |
| review | `src/sdlc/workflows/feature.py` | types moved, step pending |
| qa | `src/sdlc/stages/qa/` | migrated |
| analyze | `src/sdlc/stages/analyze/` | migrated |
| merge | `src/sdlc/workflows/feature.py` | types moved, step pending |
| deploy | `src/sdlc/workflows/feature.py` | types moved, step pending |
| retro / reflect | `src/sdlc/stages/retro/` | migrated |

Rule: **you touched a stage, you move it.**

## Further reading

- [`README.md`](README.md) — roles table, human-in-the-loop CLI, how to run
  locally / via Docker Compose, the agent board API, prompt-eval gate.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — component responsibilities, the
  stage DAG, the crew (`CrewTaskWorkflow`, E-88), ADRs.
- [`ROADMAP.md`](ROADMAP.md) — FR/NFR status, open questions, what's landed
  vs. in flight; per-epic detail lives in `docs/roadmap/`.
- `docs/reference/foundation.md`, `BENCHMARK.md`, and the generated schema pages
  under `docs/schemas/` for deeper contract- and benchmark-level detail.
