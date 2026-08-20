"""Identifier shaping. A leaf: imports nothing from sdlc.

Extracted from cli.py (E-86). `slug` is one regex, but reaching it through
`sdlc.cli` drags in the workflow classes, the agent registry, and therefore
pydantic_ai and temporalio -- which is how sdlc/operator/tools.py, advertised
as framework-free, came to load every TemporalAgent at import time. Anything
that wants a slug now imports it from here instead.
"""
from __future__ import annotations

import re


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
