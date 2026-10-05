# Changelog

Notable changes to Kroker, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html); while the major
version is 0, any release may break compatibility.

## [Unreleased]

### Added

- `python -m sdlc.demo`, a token-free dry run: the real workflow from intake
  to deploy against scripted agents and activities, answering its own
  gates. It needs a reachable Temporal and nothing else — no provider key,
  no CLI login, no repository.
- A `demo` service in `docker-compose.yml`, so a fresh clone runs that with
  one command: `docker compose run --rm demo`.
- A release workflow that publishes the worker image to
  `ghcr.io/kit-kroker/kroker-worker` on every `v*` tag.
- `docker-compose.override.example.yml`, the template for per-machine bind
  mounts.
- A container-first quickstart in the README, with the list of keys and
  logins a run needs.

### Changed

- `.env` is optional in `docker-compose.yml`, so compose loads on a fresh
  clone. A worker started without its keys still exits at boot, naming the
  missing one.
- Python 3.13 is now the minimum (`requires-python = ">=3.13"`), and CI
  runs on it. 3.11 and 3.12 were declared but never the version the image
  ran.
- `docker-compose.yml` names the worker image
  (`ghcr.io/kit-kroker/kroker-worker`) and no longer carries host-specific
  bind mounts. If you relied on them, move them to
  `docker-compose.override.yml`.

### Fixed

- `sdlc.cli doctor` reports on a machine with no provider keys instead of
  dying on a traceback: the CLI no longer builds the agent registry before
  dispatching it.
- `.env.example` asks for `EXA_API_KEY`, which the shipped research role
  requires at worker start, instead of `TAVILY_API_KEY`, which it does not.

## [0.0.1] - 2026-10-05

The first tagged version. Alpha: single operator, your own repositories,
localhost only — see [`SECURITY.md`](SECURITY.md). The history before this
tag is not itemised here; [`ROADMAP.md`](ROADMAP.md) records what is
delivered and what is open, requirement by requirement.

### What this version contains

- An idea → deployed feature pipeline orchestrated by Temporal: clarify,
  architecture, plan, code, review, QA, analysis, merge gate and an
  optional deploy stage, with human gates that are `hard`, `soft` or `off`
  per project.
- Proposer roles on Pydantic AI and coding harnesses (`claude -p`,
  `opencode run`) working in per-task git worktrees, configured from the
  versioned role registry in `agents/`.
- A deterministic merge gate with absolute checks (build, lint, security)
  judged against the run's pinned base.
- Optional research, deep-review, handoff and adversary roles, off by
  default.
- Run budgets, a per-run summary, and the `events.jsonl` / `report.html`
  export.
- The agent board API and the operator dashboard.
- A benchmark harness with stored-run scoring (`sdlc.cli benchmark`).
- `sdlc.cli doctor` for diagnosing a local setup.

### Added

- `LICENSE` (Apache-2.0) and `NOTICE`.
- `SECURITY.md`: the threat model and a private reporting channel.
- `CONTRIBUTING.md` and this changelog.

### Changed

- The distribution is renamed from `ai-sdlc-temporal` to `kroker`. The
  import package is still `sdlc`, and the commands (`python -m sdlc.cli`,
  `python -m sdlc.worker`) are unchanged. Re-run the install
  (`uv sync --frozen --extra dev` or `pip install -e ".[dev]"`) in an
  existing checkout.
- The version is reset from an untagged `0.1.0` to `0.0.1`.
- `docker-compose.yml` publishes Temporal and Hindsight on `127.0.0.1`
  only.

[Unreleased]: https://github.com/Kit-Kroker/Kroker/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/Kit-Kroker/Kroker/releases/tag/v0.0.1
