FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV TEMPORAL_HOST=temporal:7233
ENV SDLC_WORKTREES_ROOT=/tmp/sdlc/worktrees

CMD ["python", "-m", "sdlc.worker"]
