FROM mcr.microsoft.com/devcontainers/python:3.13

# Node.js for opencode CLI (installed via npm)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

# Temporal CLI — embedded server for local dev (UI on :8233, gRPC on :7233)
RUN curl -sSf https://temporal.download/cli.sh | sh

# opencode CLI (z.ai auth via `opencode auth login` inside the container)
RUN npm install -g opencode-ai
