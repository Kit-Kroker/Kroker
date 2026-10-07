FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

# Pin to the version the harness adapter is pinned to (harness/adapters pin
# 1.18.4); a drifting opencode CLI breaks transcript parsing and causes
# run_code/merge failures mid-benchmark. Bump both together after re-capturing
# a fresh transcript and updating the adapter pin.
RUN npm install -g opencode-ai@1.18.4

# claude_code beside opencode. E-88 step 2 puts the critic on a different
# model FAMILY from the lead (ADR-6) and prefers a harness with a hook
# layer, since a non-lead role is confined by `no-out-of-worktree-write`,
# which is layer: hook and therefore unenforceable on opencode. Pinned for
# the same reason opencode is: a drifting CLI breaks transcript parsing.
# Without this the crew boot check refuses to start the worker at all.
RUN npm install -g @anthropic-ai/claude-code@2.1.218

# activities.open_pull_request shells out to `gh`, and it is the LAST step of a
# feature run -- a worker without it fails after build, lint, security, review
# and every gate have already passed. Pinned for the same reason opencode is:
# `gh pr create`'s flags and its "print the PR url on stdout" contract are what
# the activity parses. Installed from the pinned .deb rather than GitHub's apt
# source, which would re-resolve to a different version on every rebuild.
ARG GH_VERSION=2.97.0
RUN arch="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/gh.deb \
        "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${arch}.deb" \
    && dpkg -i /tmp/gh.deb \
    && rm /tmp/gh.deb

# open_pull_request runs a plain `git push` before it calls gh, so GH_TOKEN has
# to reach git too. Configured as a credential helper rather than by baking a
# token into the image (there is none at build time) or rewriting the remote
# url (which would put the token in `git remote -v` and in every error
# message): gh resolves GH_TOKEN from the environment at push time. Set here
# rather than by `gh auth setup-git`, which needs an authenticated gh to run.
RUN git config --global \
        "credential.https://github.com.helper" "!gh auth git-credential"

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
# The registry is an asset, not code: pip install only takes src/, so without
# this COPY the worker cannot boot (it loads the registry at import).
COPY agents ./agents
# Case fixtures (case.yaml + oracle/) are assets too: grade_oracle resolves
# them from <repo_root>/benchmarks/cases at runtime (oracle.py:_cases_dir),
# not through the installed package. Without this COPY every oracle grade
# silently returns "no oracle dir for case" regardless of the produced code.
COPY benchmarks ./benchmarks
# The crew layout/role/skill tree is an asset too: crew/loader.py's
# crew_dir() walks cwd upward looking for a `crew/` directory at runtime, the
# same discovery pattern as agents/ above. Without this COPY load_crew fails
# every attempt with CrewAssetsMissing before a single crew round can run.
COPY crew ./crew
# notify/routes.py resolves policy/notifications.yaml relative to the repo
# root at runtime, same discovery pattern as the cases dir above. Without
# this COPY every gate notification silently fails to deliver, so a HITL
# gate just sits unnotified until its timeout.
COPY policy ./policy
# Blueprint comparison yaml (blueprints/apqc.yaml, E-48 D8) is a factory asset:
# without this COPY production assessments cannot load the reference taxonomy.
COPY blueprints ./blueprints
# The operator chat surface's prompt and model config (E-86). Copied even
# though the mount is off by default: without it, setting SDLC_CHAT_ENABLED=1
# in a container fails soft to a log line and a silently 404ing /chat.
# SDLC_CHAT_ASSETS below is what makes the path independent of where sdlc
# itself was installed -- agent.py cannot infer the repo root from
# site-packages, the same trap SDLC_CASES_ROOT exists for.
COPY interfaces/chat ./interfaces/chat

# Dependencies come from uv.lock, not from whatever PyPI serves on rebuild:
# the research role imports a private module of a 0.x package, so a drifting
# minor breaks the image itself, not just a dev venv. One sync covers what the
# three ad-hoc pip resolves used to fetch at uncontrolled versions:
# - `logfire` extra: .env's LOGFIRE_TOKEN reaches this container via
#   docker-compose's env_file, so logfire_setup.configure() gates itself on
#   and imports logfire -- without the extra installed here, boot crash-loops
#   on ModuleNotFoundError before the worker ever polls its task queue.
# - `dev` extra is what the image executes, not dev convenience:
#   pytest-asyncio because grade_oracle runs a case's oracle/test_*.py in the
#   worker's own Python and python oracle conftests use it (without it every
#   case collects as errors and scores 0/0, judge='error'); jsonschema because
#   tests/fakes/hindsight_contract.py imports it at module level and the merge
#   gate's whole-suite run aborts on 5 collection errors without it (DS12);
#   ruff as the lint fallback for a worker without PyPI egress at runtime
#   (run_integration_checks' .sdlc-venv install is best-effort; without ruff on
#   PATH lint_clean is unearnable for every Python case).
# --no-editable: the image ships the built wheel; the copied source tree is
# raw material, not the runtime import path.
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-editable --extra dev --extra logfire
ENV PATH="/app/.venv/bin:${PATH}"


# --- production worker image (what docker-compose builds) ---------------------
FROM base AS runtime

ENV TEMPORAL_HOST=temporal:7233
ENV SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees
# Explicit, not left to cwd-discovery: WORKDIR /app would make discovery
# appear to work, so the two mechanisms would mask each other and the first
# `docker run -w /somewhere-else` would fail in production, not in CI.
ENV SDLC_AGENTS_DIR=/app/agents
# Same discovery-ambiguity problem as SDLC_AGENTS_DIR, one seam over:
# oracle.py:_cases_dir()'s fallback (Path(__file__).resolve().parents[3])
# assumes a source checkout where oracle.py lives at <root>/src/sdlc/..., but
# `pip install .` (non-editable) installs into site-packages, so parents[3]
# resolves under the Python install prefix instead of /app. Pin it explicitly
# rather than relying on that fallback ever matching this image's layout.
ENV SDLC_CASES_ROOT=/app/benchmarks/cases
ENV SDLC_CHAT_ASSETS=/app/interfaces/chat
ENV SDLC_BLUEPRINTS_DIR=/app/blueprints
# 012 (FR-014/FR-016): the commit the worker records on every benchmark
# record. A bind-mounted worktree's .git points at a host path git inside
# the container cannot read, so the build argument is the fallback that
# keeps provenance explicit rather than empty; a CI build can pass
# --build-arg KROKER_COMMIT=<sha> for an exact id.
ARG KROKER_COMMIT=unknown
ENV KROKER_COMMIT=${KROKER_COMMIT}

CMD ["python", "-m", "sdlc.worker"]


# --- dev container (the .devcontainer/ target) --------------------------------
# Same environment as the worker image by construction: identical base layers
# (python, pinned opencode/claude-code/gh), identical uv.lock. Differences are
# dev-only: the Temporal CLI for `server start-dev`, and an editable install
# so host edits land without a rebuild.
FROM base AS dev

# Temporal CLI — embedded server for local dev (UI on :8233, gRPC on :7233)
RUN curl -sSf https://temporal.download/cli.sh | sh

# Flip the base stage's non-editable install to editable; same lock, so the
# dependency set is byte-identical to the runtime image. The baked /app tree
# (and this venv) is what a named volume seeded over /app/.venv starts from --
# the devcontainer mounts the real repo over /app and re-syncs in
# postCreateCommand. The suite runs against the mounted tree: tests read
# scripts/, .github/ and the docs tree, which no image COPY set should carry.
RUN uv sync --frozen --extra dev --extra logfire
