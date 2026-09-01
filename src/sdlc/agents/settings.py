"""Model settings shared by every agent build.

Split out of ``roles.py`` so a consumer can obtain the settings WITHOUT
paying for that module's eager side effects: importing ``roles`` loads the
registry, builds every agent, and wraps each in a TemporalAgent -- about 18
seconds. The prompt-gate provider runs inside a promptfoo worker with a
readiness timeout far below that, so it imports from here instead (E-82).

``roles.py`` re-exports ``MODEL_SETTINGS`` from this module, so existing
imports keep working unchanged.
"""

from __future__ import annotations

import os

from pydantic_ai.settings import ModelSettings

# Structured-output agents emit typed tool calls; Pydantic AI's 4096-token
# default truncates the tool-call arguments to {} on larger schemas (or when
# the model spends tokens on reasoning first). Override via
# SDLC_MODEL_MAX_TOKENS.
MODEL_SETTINGS = ModelSettings(max_tokens=int(os.environ.get("SDLC_MODEL_MAX_TOKENS", "64000")))
