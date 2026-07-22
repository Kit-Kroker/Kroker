FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode-ai

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
# The registry is an asset, not code: pip install only takes src/, so without
# this COPY the worker cannot boot (it loads the registry at import).
COPY agents ./agents
RUN pip install --no-cache-dir .

ENV TEMPORAL_HOST=temporal:7233
ENV SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees
# Explicit, not left to cwd-discovery: WORKDIR /app would make discovery
# appear to work, so the two mechanisms would mask each other and the first
# `docker run -w /somewhere-else` would fail in production, not in CI.
ENV SDLC_AGENTS_DIR=/app/agents

CMD ["python", "-m", "sdlc.worker"]
