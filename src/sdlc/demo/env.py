"""Placeholder provider keys for the dry run.

The agent registry is built at import and fails closed without its provider
keys (`validate_registry`), so a machine with no keys cannot even import the
workflow. The dry run never calls a provider -- every model request is
answered by a scripted TestModel -- so a stand-in value is enough to get
past construction. Kept free of sdlc imports: it has to run before them.
"""

from __future__ import annotations

import os

# The same set tests/conftest.py sets for import-only collection.
PROVIDER_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "EXA_API_KEY", "ZAI_API_KEY")
PLACEHOLDER = "demo-placeholder"


def use_placeholder_keys() -> list[str]:
    """Fill every unset or empty provider key; return the names filled.

    A key that is already set is left alone: the dry run does not read it
    either way, and overwriting it would break a later real run in the same
    process environment.
    """
    filled = [k for k in PROVIDER_KEYS if not os.environ.get(k)]
    for key in filled:
        os.environ[key] = PLACEHOLDER
    return filled
