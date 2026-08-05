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
# Case fixtures (case.yaml + oracle/) are assets too: grade_oracle resolves
# them from <repo_root>/benchmarks/cases at runtime (oracle.py:_cases_dir),
# not through the installed package. Without this COPY every oracle grade
# silently returns "no oracle dir for case" regardless of the produced code.
COPY benchmarks ./benchmarks
# notify/routes.py resolves policy/notifications.yaml relative to the repo
# root at runtime, same discovery pattern as the cases dir above. Without
# this COPY every gate notification silently fails to deliver, so a HITL
# gate just sits unnotified until its timeout.
COPY policy ./policy
RUN pip install --no-cache-dir .

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

CMD ["python", "-m", "sdlc.worker"]
