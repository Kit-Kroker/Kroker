# Contributing

Kroker is alpha software maintained by one person. Issues and pull requests
are welcome; review happens as time allows, with no response-time promise.

## Before you start

- For anything larger than a small fix, open an issue first and describe
  what you want to change. The roadmap ([`ROADMAP.md`](ROADMAP.md)) and the
  requirements ([`PRD.md`](PRD.md)) decide scope, and a change that cuts
  across them is easier to settle before the code exists.
- **Do not report a vulnerability in a public issue.** Use the private
  channel in [`SECURITY.md`](SECURITY.md).
- Read [`AGENTS.md`](AGENTS.md). It holds the conventions for editing this
  repository, for people and coding agents alike. Before touching a
  subpackage or a stage, read the nearest `AGENTS.md` in that directory:
  the rules that only hold locally live beside the code.

## Setup

```bash
uv sync --frozen --extra dev      # or: pip install -e ".[dev]"
pre-commit install
```

Python 3.13 is the version CI and the image run. `git` must be on `PATH`.
The repository ships a dev container (`.devcontainer/`) built from the same
Dockerfile as the worker image; using it avoids platform differences.

## Checks

```bash
pytest               # fast unit tier; needs no API keys and no Temporal
ruff check .
ruff format .
mypy
```

Plain `pytest` runs the fast tier only. The opt-in tiers (`slow`,
`temporal`, `docker`, and the token-spending `live` / `prompt_eval`) are
described in `AGENTS.md`; run the ones your change can affect. Frontend
checks go through `python scripts/check_ui.py`, never `npm` directly.

The pre-commit hooks run ruff, mypy over `src/`, and the file-size check
(1000 lines per file, no waivers).

## Changes that need extra care

- **Workflow code is replayed.** A change to the command sequence a
  workflow emits breaks open runs and the recorded histories under
  `tests/replay/`. Do not re-record a history to make a test pass; say in
  the pull request why the sequence changed and how in-flight runs are
  handled.
- **Role prompts are gated.** A change to `agents/<role>/instructions.md`
  is scored against its baseline (see the README, "Develop").
- **Docs describe `main`.** `ARCHITECTURE.md` and `ROADMAP.md` state what
  is merged, not what is planned. Update them in the same pull request as
  the behaviour they describe.
- **Tests never contain literal scanner-trigger text.** The merge gate's
  security floor has no exemption for fixtures
  (`src/sdlc/stages/qa/AGENTS.md`).

## Pull requests

- One logical change per pull request, with tests for the behaviour it
  changes.
- Commit subjects follow the pattern already in the history:
  `type(scope): summary`, with `feat`, `fix`, `docs`, `test`, `chore` or
  `refactor` as the type. Say why in the body when the diff does not.
- Add a line to the `Unreleased` section of [`CHANGELOG.md`](CHANGELOG.md)
  for anything a user of the pipeline would notice.

## Licence of contributions

Kroker is licensed under the Apache License 2.0 ([`LICENSE`](LICENSE)). As
section 5 of that licence states, anything you submit for inclusion is
under the same licence, with no additional terms. There is no separate
contributor agreement to sign. Only submit work you have the right to
license this way.
