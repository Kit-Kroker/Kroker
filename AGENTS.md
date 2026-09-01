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

## Further reading

- [`README.md`](README.md) — roles table, human-in-the-loop CLI, how to run
  locally / via Docker Compose, the agent board API, prompt-eval gate.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — component responsibilities, the
  stage DAG, the crew (`CrewTaskWorkflow`, E-88), ADRs.
- [`ROADMAP.md`](ROADMAP.md) — FR/NFR status, open questions, what's landed
  vs. in flight.
- `docs/foundation.md`, `docs/BENCHMARK.md`, and the self-contained schema
  docs under `docs/*.html` for deeper contract- and benchmark-level detail.
